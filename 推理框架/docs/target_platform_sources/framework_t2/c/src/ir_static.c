#include "ir_static.h"
#include <limits.h>
#include <math.h>
#include <string.h>

static uint32_t rd32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t rd64(const unsigned char *p){return rd32(p)|(uint64_t)rd32(p+4)<<32;}
static uint32_t crc_byte(uint32_t c,unsigned char b){unsigned j;c^=b;for(j=0;j<8;j++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);return c;}
uint32_t irs_crc32(const void *data,size_t size){const unsigned char *p=data;uint32_t c=UINT32_MAX;size_t i;for(i=0;i<size;i++)c=crc_byte(c,p[i]);return ~c;}
uint32_t irs_image_crc(const void *data,size_t size){const unsigned char *p=data;uint32_t c=UINT32_MAX;size_t i;for(i=0;i<size;i++)if(i<56||i>=64)c=crc_byte(c,p[i]);return ~c;}
uint32_t irs_check_span(uint64_t a,uint64_t n,unsigned bits){
    uint64_t m;if(bits!=32&&bits!=64)return IR_INVALID_ARGUMENT;m=bits==32?UINT32_MAX:UINT64_MAX;
    return a>m||n>m||(n&&n-1>m-a)?IR_RESOURCE_LIMIT:IR_OK;
}
static int range(uint64_t o,uint64_t n,uint64_t cap){return o<=cap&&n<=cap-o;}
static const unsigned char *tensor(const unsigned char *p,uint32_t i){return p+64+(size_t)i*96;}
static const unsigned char *node(const unsigned char *p,const irs_info *in,uint32_t i){return p+64+(size_t)in->tensors*96+(size_t)i*24;}
static int overlap(uint64_t a,uint64_t n,uint64_t b,uint64_t m){return n&&m&&(a<=b?b-a<n:a-b<m);}

uint32_t irs_inspect(const void *image,size_t size,unsigned bits,irs_info *out){
    const unsigned char *p=image;irs_info in;uint32_t i,j,k,inputs=0,outputs=0;int first[IRS_MAX_TENSORS],last[IRS_MAX_TENSORS];
    if(!p||!out||size<64)return IR_INVALID_ARGUMENT;
    if(memcmp(p,"IRS4BIN1",8)||rd32(p+8)!=1||rd32(p+12)!=0x01020304||rd32(p+28))return IR_UNSUPPORTED;
    in.tensors=rd32(p+16);in.nodes=rd32(p+20);in.alignment=rd32(p+24);
    in.weights=rd64(p+32);in.activations=rd64(p+40);in.workspace=rd64(p+48);
    if(!in.tensors||in.tensors>IRS_MAX_TENSORS||!in.nodes||in.nodes>IR_MAX_CHAIN||in.alignment<4||in.alignment>4096||(in.alignment&(in.alignment-1)))return IR_RESOURCE_LIMIT;
    if(size!=64+(size_t)in.tensors*96+(size_t)in.nodes*24||rd32(p+56)!=irs_image_crc(p,size))return IR_INVALID_ARGUMENT;
    if(irs_check_span(0,in.weights,bits)||irs_check_span(0,in.activations,bits)||irs_check_span(0,in.workspace,bits))return IR_RESOURCE_LIMIT;
    for(i=0;i<in.tensors;i++){
        const unsigned char *t=tensor(p,i);uint32_t rank=rd32(t+4),role=rd32(t+8),arena=rd32(t+12);uint64_t n=1;
        if((rd32(t)!=IR_FLOAT32&&rd32(t)!=IR_INT32)||rank<1||rank>4||role>3||arena!=(role==0?0u:1u))return IR_INVALID_ARGUMENT;
        for(j=0;j<4;j++){uint64_t d=rd64(t+32+8*j),s=rd64(t+64+8*j);
            if(j>=rank){if(d||s)return IR_INVALID_SHAPE;}
            else {if(!d||d>s||s>IR_MAX_ELEMENTS/n)return IR_INVALID_SHAPE;n*=s;}}
        if(rd64(t+24)!=n*4||rd64(t+16)%in.alignment||!range(rd64(t+16),n*4,arena?in.activations:in.weights))return IR_INVALID_ARGUMENT;
        first[i]=role<=1?-1:-2;last[i]=-2;if(role==1)inputs++;if(role==3)outputs++;
    }
    if(!inputs||!outputs)return IR_INVALID_ARGUMENT;
    for(i=0;i<in.nodes;i++){
        const unsigned char *n=node(p,&in,i);uint32_t op=rd32(n),o=rd32(n+16);
        if(op<1||op>3||o>=in.tensors||first[o]!=-2||rd32(n+20))return IR_INVALID_ARGUMENT;
        for(j=0;j<3;j++){uint32_t x=rd32(n+4+j*4);
            if(x==UINT32_MAX){if(j==0||(j==1&&op!=IR_RELU))return IR_INVALID_ARGUMENT;continue;}
            if(x>=in.tensors||first[x]==-2||(op==IR_RELU&&j>0)||(op==IR_ADD&&j==2))return IR_INVALID_ARGUMENT;
            last[x]=(int)i;
        }
        first[o]=(int)i;
    }
    for(i=0;i<in.tensors;i++){
        uint32_t role=rd32(tensor(p,i)+8);
        if(first[i]==-2)return IR_INVALID_ARGUMENT;
        if(role==3)last[i]=(int)in.nodes;
        if(last[i]==-2)return IR_INVALID_ARGUMENT;
        if(role==0)last[i]=(int)in.nodes;
    }
    for(i=0;i<in.tensors;i++)for(k=i+1;k<in.tensors;k++){
        const unsigned char *a=tensor(p,i),*b=tensor(p,k);
        if(rd32(a+12)==rd32(b+12)&&overlap(rd64(a+16),rd64(a+24),rd64(b+16),rd64(b+24))&&first[i]<=last[k]&&first[k]<=last[i])return IR_INVALID_ARGUMENT;
    }
    *out=in;return IR_OK;
}
static uint32_t default_query(void *u,const ir_call *c,uint32_t n){uint32_t i,s;(void)u;for(i=0;i<n;i++)if((s=ir_query(c+i))!=IR_OK)return s;return IR_OK;}
static uint32_t default_execute(void *u,const ir_call *c,uint32_t n,uint32_t *done,ir_node_profile *profiles,int *quiet){(void)u;*quiet=1;return profiles?ir_execute_chain_profiled(c,n,done,profiles,n):ir_execute_chain(c,n,done);}
static uint32_t default_recover(void *u){(void)u;return IR_OK;}
static int span(const void *p,uint64_t n){return (!n||p)&&n<=SIZE_MAX&&irs_check_span((uint64_t)(uintptr_t)p,n,sizeof(uintptr_t)*CHAR_BIT)==IR_OK;}
static uint32_t storage_valid(const ir_tensor *t,const void *data){
    uint64_t i,total=t->byte_length/4;
    for(i=0;i<total;i++){
        uint64_t index=i;uint32_t axis;int padding=0;const unsigned char *at=(const unsigned char*)data+(size_t)i*4;
        for(axis=t->rank;axis>0;axis--){if(index%t->storage_shape[axis-1]>=t->shape[axis-1])padding=1;index/=t->storage_shape[axis-1];}
        if(t->dtype==IR_FLOAT32){float v;memcpy(&v,at,4);if(!isfinite(v))return IR_NONFINITE;if(padding&&v!=0)return IR_INVALID_ARGUMENT;}
        else if(padding){int32_t v;memcpy(&v,at,4);if(v!=0)return IR_INVALID_ARGUMENT;}
    }
    return IR_OK;
}
static void event(irs_context *c,const char *name,uint32_t status){uint64_t ns=0;int valid=c->platform.now_ns&&c->platform.now_ns(c->platform.user,&ns)==1;
    if(valid&&c->have_time&&ns<c->last_ns)valid=0;
    if(valid){c->last_ns=ns;c->have_time=1;}
    if(c->platform.trace)c->platform.trace(c->platform.user,name,status,c->completed,ns,valid);
}
size_t irs_context_size(void){return sizeof(irs_context);}
size_t irs_inspect_scratch_bytes(void){return 2*IRS_MAX_TENSORS*sizeof(int);}
uint32_t irs_completed(const irs_context *c){return c?c->completed:0;}
uint32_t irs_bind(irs_context *c,const void *image,size_t size,void *w,uint64_t wn,void *a,uint64_t an,void *s,uint64_t sn,
    ir_tensor *ts,uint32_t tc,ir_call *calls,uint32_t nc,ir_node_profile *profiles,const irs_platform *platform,const irs_backend *backend){
    irs_info in;uint32_t result,i,j;const unsigned char *p=image;
    const void *ptrs[10];uint64_t lens[10];unsigned count=8,x,y;
    if(!c||!ts||!calls)return IR_INVALID_ARGUMENT;
    if(c->state)return IRS_INVALID_STATE;
    result=irs_inspect(image,size,sizeof(uintptr_t)*CHAR_BIT,&in);if(result)return result;
    if(tc<in.tensors||nc<in.nodes||wn<in.weights||an<in.activations||sn<in.workspace)return IR_RESOURCE_LIMIT;
    if((in.weights&&(uintptr_t)w%in.alignment)||(in.activations&&(uintptr_t)a%in.alignment)||(in.workspace&&(uintptr_t)s%in.alignment))return IR_INVALID_ARGUMENT;
    ptrs[0]=c;lens[0]=sizeof *c;ptrs[1]=image;lens[1]=size;ptrs[2]=w;lens[2]=wn;ptrs[3]=a;lens[3]=an;ptrs[4]=s;lens[4]=sn;
    ptrs[5]=ts;lens[5]=in.tensors*sizeof *ts;ptrs[6]=calls;lens[6]=in.nodes*sizeof *calls;ptrs[7]=profiles;lens[7]=profiles?in.nodes*sizeof *profiles:0;
    if(platform){ptrs[count]=platform;lens[count++]=sizeof *platform;if(platform->api_version!=1||!platform->sync||!platform->recover)return IR_UNSUPPORTED;}
    if(backend){ptrs[count]=backend;lens[count++]=sizeof *backend;if(backend->api_version!=1||!backend->query||!backend->execute||!backend->recover)return IR_UNSUPPORTED;}
    for(x=0;x<count;x++){if(!span(ptrs[x],lens[x]))return IR_RESOURCE_LIMIT;for(y=0;y<x;y++)if(overlap((uintptr_t)ptrs[x],lens[x],(uintptr_t)ptrs[y],lens[y]))return IR_INVALID_ARGUMENT;}
    if(irs_crc32(w,(size_t)in.weights)!=rd32(p+60))return IR_INVALID_ARGUMENT;
    memset(c,0,sizeof *c);c->info=in;c->tensors=ts;c->calls=calls;c->profiles=profiles;
    if(platform)c->platform=*platform;
    if(backend)c->backend=*backend;else {c->backend.api_version=1;c->backend.query=default_query;c->backend.execute=default_execute;c->backend.recover=default_recover;}
    for(i=0;i<in.tensors;i++){
        const unsigned char *t=tensor(p,i);ir_tensor *out=ts+i;memset(out,0,sizeof *out);out->dtype=rd32(t);out->rank=rd32(t+4);out->layout=IR_ROW_MAJOR;
        out->data=(unsigned char*)(rd32(t+12)?a:w)+(size_t)rd64(t+16);out->byte_length=rd64(t+24);c->roles[i]=rd32(t+8);
        for(j=0;j<4;j++){out->shape[j]=rd64(t+32+8*j);out->storage_shape[j]=rd64(t+64+8*j);}
    }
    for(i=0;i<in.nodes;i++){
        const unsigned char *n=node(p,&in,i);ir_call *call=calls+i;memset(call,0,sizeof *call);call->op=rd32(n);call->a=ts+rd32(n+4);
        call->b=rd32(n+8)==UINT32_MAX?NULL:ts+rd32(n+8);call->bias=rd32(n+12)==UINT32_MAX?NULL:ts+rd32(n+12);call->output=ts+rd32(n+16);call->workspace=s;call->workspace_bytes=in.workspace;
    }
    for(i=0;i<in.tensors;i++)if(c->roles[i]==0){result=storage_valid(ts+i,ts[i].data);if(result)return result;}
    result=c->backend.query(c->backend.user,calls,in.nodes);if(result)return result;
    c->state=1;event(c,"bind",IR_OK);return IR_OK;
}
uint32_t irs_input(irs_context *c,uint32_t i,const void *data,uint64_t n){
    if(!c||c->state!=1)return IRS_INVALID_STATE;
    if(i>=c->info.tensors||c->roles[i]!=1||n!=c->tensors[i].byte_length||!span(data,n))return IR_INVALID_ARGUMENT;
    {uint32_t result=storage_valid(c->tensors+i,data);if(result)return result;}
    memmove(c->tensors[i].data,data,(size_t)n);c->supplied[i]=1;c->valid_output=0;return IR_OK;
}
uint32_t irs_output(irs_context *c,uint32_t i,const void **data,uint64_t *n){
    if(!c||c->state!=1||!c->valid_output)return IRS_INVALID_STATE;
    if(i>=c->info.tensors||c->roles[i]!=3||!data||!n)return IR_INVALID_ARGUMENT;
    *data=c->tensors[i].data;*n=c->tensors[i].byte_length;return IR_OK;
}
uint32_t irs_run(irs_context *c){
    uint32_t i,result;int quiet=0;
    if(!c||c->state!=1)return IRS_INVALID_STATE;
    c->valid_output=0;c->completed=0;c->last_status=IR_INVALID_ARGUMENT;
    for(i=0;i<c->info.tensors;i++)if(c->roles[i]==1&&!c->supplied[i])return IR_INVALID_ARGUMENT;
    memset(c->supplied,0,sizeof c->supplied);
    c->state=2;if(c->profiles)memset(c->profiles,0,c->info.nodes*sizeof *c->profiles);event(c,"run.begin",IR_OK);
    if(c->platform.sync&&c->platform.sync(c->platform.user,1)!=IR_OK){c->sync_unknown=1;goto unknown;}
    event(c,"sync.to_backend",IR_OK);
    result=c->backend.execute(c->backend.user,c->calls,c->info.nodes,&c->completed,c->profiles,&quiet);
    if(!quiet||c->completed>c->info.nodes||result>IR_NUMERIC_OVERFLOW||(result==IR_OK&&c->completed!=c->info.nodes)){c->backend_unknown=1;goto unknown;}
    event(c,"backend.chain",result);
    if(c->platform.sync&&c->platform.sync(c->platform.user,2)!=IR_OK){c->sync_unknown=1;goto unknown;}
    event(c,"sync.to_cpu",IR_OK);c->last_status=result;c->valid_output=result==IR_OK;c->state=1;event(c,"run.end",result);return result;
unknown:
    c->state=3;c->last_status=IRS_SYNC_ERROR;event(c,"run.end",IRS_SYNC_ERROR);return IRS_SYNC_ERROR;
}
uint32_t irs_recover(irs_context *c){
    if(!c||c->state!=3)return IRS_INVALID_STATE;
    if(c->backend_unknown&&c->backend.recover(c->backend.user)!=IR_OK)return IRS_INVALID_STATE;
    if(c->sync_unknown&&(!c->platform.recover||c->platform.recover(c->platform.user)!=IR_OK))return IRS_INVALID_STATE;
    c->backend_unknown=c->sync_unknown=0;c->state=1;return IR_OK;
}
uint32_t irs_close(irs_context *c){if(!c||c->state==2||c->state==3)return IRS_INVALID_STATE;c->state=0;c->valid_output=0;return IR_OK;}
