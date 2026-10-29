#define _POSIX_C_SOURCE 200809L
#include "ir_pc.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <time.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define fileno _fileno
#define fstat _fstat64
#define stat _stat64
#define SEEKFILE _fseeki64
#else
#include <unistd.h>
#define SEEKFILE fseeko
#endif

void irs_pc_init(irs_pc *p,uint64_t budget){unsigned i;memset(p,0,sizeof *p);p->budget=budget;p->fail_after=-1;for(i=0;i<IRS_RES_COUNT;i++)p->category_limits[i]=budget;}
uint32_t irs_read_exact(const irs_reader *r,uint64_t o,void *dst,uint64_t n){
    size_t got=0;uint32_t status;
    if(!r||!r->read_at||o>r->size||n>r->size-o||n>SIZE_MAX||(!dst&&n))return IR_INVALID_ARGUMENT;
    status=r->read_at(r->user,o,dst,(size_t)n,&got);return status?status:got==n?IR_OK:IRS_IO_ERROR;
}
uint32_t irs_pc_alloc(irs_pc *p,uint64_t n,uint32_t alignment,irs_block *out){
    return irs_pc_alloc_kind(p,n,alignment,IRS_RES_ARENA,out);
}
uint32_t irs_pc_alloc_kind(irs_pc *p,uint64_t n,uint32_t alignment,uint32_t category,irs_block *out){
    uint64_t charge;void *raw;uintptr_t address;
    if(!p||!out||category>=IRS_RES_COUNT||alignment<4||alignment>4096||(alignment&(alignment-1)))return IR_INVALID_ARGUMENT;
    if(out->raw||out->data||out->owner||out->charge||out->size)return IR_INVALID_ARGUMENT;
    if(n>SIZE_MAX||n>UINT64_MAX-(alignment-1))return IR_RESOURCE_LIMIT;
    charge=n?n+alignment-1:0;
    if(charge>SIZE_MAX||p->used>p->budget||charge>p->budget-p->used||p->category_used[category]>p->category_limits[category]||charge>p->category_limits[category]-p->category_used[category]||p->fail_after==0){p->rejected_allocations++;return IR_RESOURCE_LIMIT;}
    memset(out,0,sizeof *out);if(!n)return IR_OK;
    raw=calloc(1,(size_t)charge);if(!raw){p->rejected_allocations++;return IR_RESOURCE_LIMIT;}
    address=(uintptr_t)raw;if(irs_check_span(address,charge,sizeof(uintptr_t)*CHAR_BIT)!=IR_OK){free(raw);return IR_RESOURCE_LIMIT;}
    address=(address+alignment-1)&~(uintptr_t)(alignment-1);
    out->raw=raw;out->data=(void*)address;out->owner=p;out->charge=charge;out->size=n;out->category=category;
    p->used+=charge;p->allocations++;p->category_used[category]+=charge;
    if(p->used>p->peak_used)p->peak_used=p->used;
    if(p->allocations>p->peak_allocations)p->peak_allocations=p->allocations;
    if(p->category_used[category]>p->category_peak[category])p->category_peak[category]=p->category_used[category];
    if(p->fail_after>0)p->fail_after--;
    return IR_OK;
}
uint32_t irs_pc_reclassify(irs_pc *p,irs_block *b,uint32_t category){
    if(!p||!b||b->owner!=p||!b->raw||category>=IRS_RES_COUNT||b->category>=IRS_RES_COUNT||b->charge>p->category_used[b->category])return IR_INVALID_ARGUMENT;
    if(category==b->category)return IR_OK;
    if(p->category_used[category]>p->category_limits[category]||b->charge>p->category_limits[category]-p->category_used[category]){p->rejected_allocations++;return IR_RESOURCE_LIMIT;}
    p->category_used[b->category]-=b->charge;p->category_used[category]+=b->charge;b->category=category;
    if(p->category_used[category]>p->category_peak[category])p->category_peak[category]=p->category_used[category];
    return IR_OK;
}
uint32_t irs_pc_check_transient(irs_pc *p,uint32_t category,uint64_t n){
    if(!p||category>=IRS_RES_COUNT)return IR_INVALID_ARGUMENT;
    if(p->used>p->budget||n>p->budget-p->used||p->category_used[category]>p->category_limits[category]||n>p->category_limits[category]-p->category_used[category]){p->rejected_allocations++;return IR_RESOURCE_LIMIT;}
    if(p->used+n>p->peak_used)p->peak_used=p->used+n;
    if(p->category_used[category]+n>p->category_peak[category])p->category_peak[category]=p->category_used[category]+n;
    return IR_OK;
}
uint32_t irs_pc_free(irs_pc *p,irs_block *b){
    if(!p||!b)return IR_INVALID_ARGUMENT;
    if(!b->raw)return IR_OK;
    if(b->owner!=p||b->charge>p->used||!p->allocations||b->category>=IRS_RES_COUNT||b->charge>p->category_used[b->category])return IR_INVALID_ARGUMENT;
    free(b->raw);p->used-=b->charge;p->category_used[b->category]-=b->charge;p->allocations--;memset(b,0,sizeof *b);return IR_OK;
}
static uint32_t file_read(void *user,uint64_t o,void *dst,size_t n,size_t *got){
    FILE *f=user;if(o>INT64_MAX||SEEKFILE(f,(int64_t)o,SEEK_SET)!=0)return IRS_IO_ERROR;
    *got=fread(dst,1,n,f);return ferror(f)?IRS_IO_ERROR:IR_OK;
}
uint32_t irs_pc_read(irs_pc *pc,const char *path,uint64_t limit,irs_block *out){
    FILE *f;struct stat before,after;irs_reader reader;uint32_t result;
    if(!pc||!path||!out)return IR_INVALID_ARGUMENT;
    if(out->raw||out->data||out->owner||out->charge||out->size)return IR_INVALID_ARGUMENT;
    f=fopen(path,"rb");if(!f)return IRS_IO_ERROR;
    if(fstat(fileno(f),&before)!=0||before.st_size<0||
#ifdef _WIN32
       !(before.st_mode&_S_IFREG)
#else
       !S_ISREG(before.st_mode)
#endif
    ){fclose(f);return IRS_IO_ERROR;}
    reader.user=f;reader.size=(uint64_t)before.st_size;reader.read_at=file_read;
    if(reader.size>limit){fclose(f);return IR_RESOURCE_LIMIT;}
    result=irs_pc_alloc_kind(pc,reader.size,64,IRS_RES_SOURCE,out);
    if(result==IR_OK)result=irs_read_exact(&reader,0,out->data,reader.size);
    if(fstat(fileno(f),&after)!=0||after.st_size!=before.st_size)result=IRS_IO_ERROR;
    if(fclose(f)!=0)result=IRS_IO_ERROR;
    if(result!=IR_OK)irs_pc_free(pc,out);
    return result;
}
static uint32_t pc_sync(void *user,int direction){irs_pc *p=user;return p->sync_fail==direction?IRS_SYNC_ERROR:IR_OK;}
static uint32_t pc_recover(void *user){irs_pc *p=user;return p->sync_fail?IRS_SYNC_ERROR:IR_OK;}
static int pc_time(void *user,uint64_t *ns){
    irs_pc *p=user;if(p->clock_unavailable)return 0;
#ifdef _WIN32
    {LARGE_INTEGER now,freq;if(!QueryPerformanceFrequency(&freq)||!QueryPerformanceCounter(&now)||freq.QuadPart<=0||now.QuadPart<0)return 0;
    *ns=(uint64_t)(now.QuadPart/freq.QuadPart)*UINT64_C(1000000000)+(uint64_t)(now.QuadPart%freq.QuadPart)*UINT64_C(1000000000)/(uint64_t)freq.QuadPart;}
#else
    {struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0||now.tv_sec<0||(uint64_t)now.tv_sec>UINT64_MAX/UINT64_C(1000000000))return 0;
    *ns=(uint64_t)now.tv_sec*UINT64_C(1000000000)+(uint64_t)now.tv_nsec;}
#endif
    return 1;
}
static void pc_trace(void *user,const char *event,uint32_t status,uint32_t completed,uint64_t ns,int valid){
    irs_pc *p=user;if(!p->trace)return;
    if(!valid)p->observation_errors++;
    if(fprintf(p->trace,"%s{\"kind\":\"%s\",\"status\":%u,\"completed_steps\":%u,\"host_ns\":%llu,\"timing_valid\":%s}",p->events?",":"",event,status,completed,(unsigned long long)ns,valid?"true":"false")<0)p->trace_failed=1;
    p->events++;
}
irs_platform irs_pc_platform(irs_pc *p){irs_platform result={1,p,pc_sync,pc_recover,pc_time,pc_trace};return result;}
