#include "ir_pc.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint32_t short_read(void *u,uint64_t o,void *d,size_t n,size_t *got){(void)u;(void)o;(void)d;*got=n?n-1:0;return IR_OK;}
int main(void){
    irs_pc pc,other;irs_block b={0};char dst[8];irs_reader reader={NULL,8,short_read};irs_platform p;
    irs_pc_init(&pc,1024);assert(irs_read_exact(&reader,0,dst,8)==IRS_IO_ERROR);
    assert(irs_read_exact(&reader,7,dst,2)==IR_INVALID_ARGUMENT);
    pc.fail_after=0;assert(irs_pc_alloc(&pc,8,64,&b)==IR_RESOURCE_LIMIT&&pc.used==0);pc.fail_after=-1;
    assert(irs_pc_alloc(&pc,UINT64_MAX,64,&b)==IR_RESOURCE_LIMIT);
    assert(irs_pc_alloc(&pc,8,3,&b)==IR_INVALID_ARGUMENT);
    assert(irs_pc_alloc(&pc,8,64,&b)==IR_OK&&(uintptr_t)b.data%64==0&&pc.used==71);
    irs_pc_init(&other,1024);irs_pc_free(&other,&b);assert(pc.used==71&&other.used==0&&b.raw!=NULL);
    {void *original=b.raw;assert(irs_pc_alloc(&pc,8,64,&b)==IR_INVALID_ARGUMENT);assert(b.raw==original&&pc.allocations==1&&pc.used==71);
     pc.fail_after=0;assert(irs_pc_read(&pc,__FILE__,1048576,&b)==IR_INVALID_ARGUMENT);assert(b.raw==original&&pc.allocations==1&&pc.used==71);pc.fail_after=-1;}
    irs_pc_free(&pc,&b);irs_pc_free(&pc,&b);assert(pc.used==0&&pc.allocations==0);
    p=irs_pc_platform(&pc);pc.clock_unavailable=1;{uint64_t ns;assert(p.now_ns(p.user,&ns)==0);}
    pc.sync_fail=2;assert(p.sync(p.user,2)==IRS_SYNC_ERROR);pc.sync_fail=0;assert(p.recover(p.user)==IR_OK);
    puts("pc platform checks passed");return 0;
}
