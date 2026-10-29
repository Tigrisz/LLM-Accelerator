/* T3 caller-owned metadata, limits, alias rejection and lifecycle checks. */
#define main legacy_static_test_main
#include "test_static.c"
#undef main
#include <stdlib.h>

static void metadata_contract(void){
    irs_context ctx={0},other={0};irs_info info;ir_tensor ts[3],ts2[3];ir_call calls[1],calls2[1];
    irs_tensor_state state[3],state2[3];irs_lifetime life[3];
    _Alignas(64) unsigned char a[192],a2[192],scratch[64],scratch2[64];
    int32_t x[2]={2,-3},y[2]={4,5};const void *out;uint64_t n;unsigned char saved[sizeof ctx];
    irs_platform platform={1,NULL,sync_cb,recover_cb,NULL,NULL};
    make();assert(irs_runtime_abi_version()==2&&irs_context_size()<1024);
    assert(irs_inspect_workspace_bytes(3)==12&&irs_tensor_state_bytes(3)==3);
    assert(irs_inspect_workspace_bytes(4096)==16384&&irs_tensor_state_bytes(4096)==4096);
    assert(irs_inspect_workspace_bytes(0)==0&&irs_inspect_workspace_bytes(4097)==0);
    assert(irs_read_info(image,sizeof image,32,&info)==IR_OK&&info.tensors==3);
    memset(&info,0xa5,sizeof info);
    assert(irs_inspect_v2(image,sizeof image,32,&info,life,sizeof life-1)==IR_RESOURCE_LIMIT);
    assert(info.tensors==UINT32_C(0xa5a5a5a5));
    assert(irs_inspect_v2(image,sizeof image,32,&info,image,sizeof image)!=IR_OK);
    assert(irs_inspect_v2(image,sizeof image,32,(irs_info*)life,life,sizeof life)!=IR_OK);
    assert(irs_inspect_v2(image,sizeof image,32,&info,(unsigned char*)life+1,sizeof life)!=IR_OK);
    assert(irs_inspect_v2(image,sizeof image,32,&info,life,sizeof life)==IR_OK);
    memset(a,0,sizeof a);memset(a2,0,sizeof a2);memset(scratch,0,sizeof scratch);
#define BIND(c,ar,ws,t,cl,st,cap,iw,bytes) irs_bind_v2(c,image,sizeof image,NULL,0,ar,192,ws,64,t,3,cl,1,NULL,st,cap,iw,bytes,&platform,NULL)
    memcpy(saved,&ctx,sizeof ctx);memset(state,0xa5,sizeof state);
    assert(BIND(&ctx,a,scratch,ts,calls,state,2,life,sizeof life)==IR_RESOURCE_LIMIT);
    assert(memcmp(saved,&ctx,sizeof ctx)==0&&state[0]==0xa5);
    assert(BIND(&ctx,a,scratch,ts,calls,state,3,a,sizeof life)!=IR_OK);
    assert(BIND(&ctx,a,scratch,ts,calls,(irs_tensor_state*)image,3,life,sizeof life)!=IR_OK);
    assert(BIND(&ctx,a,scratch,ts,calls,state,3,&ctx,sizeof ctx)!=IR_OK);
    assert(memcmp(saved,&ctx,sizeof ctx)==0&&state[0]==0xa5);
    assert(BIND(&ctx,a,scratch,ts,calls,state,3,life,sizeof life)==IR_OK);
    assert(irs_close(&ctx)==IR_OK);
    /* Unused arena tail remains part of its declared exclusive span. */
    {_Alignas(64) unsigned char joint[256];
     assert(irs_bind_v2(&ctx,image,sizeof image,NULL,0,joint,192,joint+192,64,ts,3,calls,1,NULL,state,3,life,sizeof life,&platform,NULL)==IR_OK);
     assert(irs_close(&ctx)==IR_OK);
     assert(irs_bind_v2(&ctx,image,sizeof image,NULL,0,joint,256,joint+192,64,ts,3,calls,1,NULL,state,3,life,sizeof life,&platform,NULL)==IR_INVALID_ARGUMENT);}
    assert(BIND(&ctx,a,scratch,ts,calls,state,3,life,sizeof life)==IR_OK);
    /* Inspection memory may be immediately overwritten/reused. */
    memset(life,0xff,sizeof life);
    assert(BIND(&other,a2,scratch2,ts2,calls2,state2,3,life,sizeof life)==IR_OK);
    memset(life,0xaa,sizeof life);
    assert(irs_tensor_role(&ctx,0)==1&&irs_tensor_role(&ctx,2)==3&&irs_tensor_role(&ctx,3)==UINT32_MAX);
    assert(irs_input(&ctx,0,x,sizeof x)==IR_OK&&irs_input(&other,1,y,sizeof y)==IR_OK);
    assert(irs_run(&ctx)==IR_INVALID_ARGUMENT&&irs_run(&other)==IR_INVALID_ARGUMENT);
    assert(irs_input(&ctx,1,y,sizeof y)==IR_OK&&irs_run(&ctx)==IR_OK);
    assert(irs_output(&ctx,2,&out,&n)==IR_OK&&n==8&&((const int32_t*)out)[0]==6);
    assert(irs_run(&ctx)==IR_INVALID_ARGUMENT); /* supplied bits consumed */
    assert(irs_input(&ctx,0,x,sizeof x)==IR_OK&&irs_input(&ctx,1,y,sizeof y)==IR_OK);
    sync_fail=2;assert(irs_run(&ctx)==IRS_SYNC_ERROR&&irs_close(&ctx)==IRS_INVALID_STATE);
    assert(irs_recover(&ctx)!=IR_OK);sync_fail=0;
    assert(irs_recover(&ctx)==IR_OK&&irs_close(&ctx)==IR_OK);
    assert(irs_input(&other,0,x,sizeof x)==IR_OK&&irs_run(&other)==IR_OK&&irs_close(&other)==IR_OK);
#undef BIND
}

static void put32(unsigned char *b,size_t p,uint32_t v){unsigned i;for(i=0;i<4;i++)b[p+i]=(unsigned char)(v>>(8*i));}
static void put64(unsigned char *b,size_t p,uint64_t v){unsigned i;for(i=0;i<8;i++)b[p+i]=(unsigned char)(v>>(8*i));}
static void capacity_contract(void){
    const uint32_t nt=4096,nn=1024;size_t bytes=64+(size_t)nt*96+(size_t)nn*24;uint32_t i;
    unsigned char *b=calloc(1,bytes);irs_lifetime *life=malloc(irs_inspect_workspace_bytes(nt));irs_info info;
    assert(b&&life);memcpy(b,"IRS4BIN1",8);put32(b,8,1);put32(b,12,0x01020304);put32(b,16,nt);put32(b,20,nn);put32(b,24,4);
    put64(b,40,(uint64_t)nt*4);put64(b,48,4);
    for(i=0;i<nt;i++){size_t p=64+(size_t)i*96;put32(b,p,2);put32(b,p+4,1);put32(b,p+8,i<3*nn?1:3);put32(b,p+12,1);put64(b,p+16,(uint64_t)i*4);put64(b,p+24,4);put64(b,p+32,1);put64(b,p+64,1);
        if(i<nn){/* weights for linear are rank2 [1,1]. */put32(b,p+4,2);put64(b,p+40,1);put64(b,p+72,1);}}
    for(i=0;i<nn;i++){size_t p=64+(size_t)nt*96+(size_t)i*24;put32(b,p,1);put32(b,p+4,i);put32(b,p+8,nn+i);put32(b,p+12,2*nn+i);put32(b,p+16,3*nn+i);}
    put32(b,56,irs_image_crc(b,bytes));assert(irs_inspect_v2(b,bytes,32,&info,life,irs_inspect_workspace_bytes(nt))==IR_OK);
    {irs_context ctx={0};ir_tensor *ts=calloc(nt,sizeof *ts);ir_call *calls=calloc(nn,sizeof *calls);irs_tensor_state *states=malloc(nt);
     int32_t *act=calloc(nt,sizeof *act),work=0;const void *out;uint64_t out_size;assert(ts&&calls&&states&&act);
     assert(irs_bind_v2(&ctx,b,bytes,NULL,0,act,(uint64_t)nt*4,&work,4,ts,nt,calls,nn,NULL,states,nt,life,irs_inspect_workspace_bytes(nt),NULL,NULL)==IR_OK);
     free(life);life=NULL; /* run must not dereference the freed inspect storage */
     for(i=0;i<3*nn;i++){int32_t v=i<nn?2:i<2*nn?3:4;assert(irs_input(&ctx,i,&v,4)==IR_OK);}
     assert(irs_run(&ctx)==IR_OK&&irs_completed(&ctx)==nn);
     assert(irs_output(&ctx,nt-1,&out,&out_size)==IR_OK&&out_size==4&&*(const int32_t*)out==10);
     assert(irs_close(&ctx)==IR_OK);free(ts);free(calls);free(states);free(act);}
    put32(b,16,4097);put32(b,56,irs_image_crc(b,bytes));assert(irs_read_info(b,bytes,32,&info)==IR_RESOURCE_LIMIT);
    put32(b,16,nt);put32(b,20,1025);put32(b,56,irs_image_crc(b,bytes));assert(irs_read_info(b,bytes,32,&info)==IR_RESOURCE_LIMIT);
    free(life);free(b);
}
int main(void){metadata_contract();capacity_contract();printf("{\"runtime_abi\":%u,\"context_bytes\":%zu,\"tensor_bytes\":%zu,\"call_bytes\":%zu,\"state_3\":%zu,\"inspect_3\":%zu,\"max_tensors\":%u,\"max_nodes\":%u,\"passed\":true}\n",irs_runtime_abi_version(),sizeof(irs_context),sizeof(ir_tensor),sizeof(ir_call),irs_tensor_state_bytes(3),irs_inspect_workspace_bytes(3),IRS_MAX_TENSORS,IR_MAX_CHAIN);return 0;}
