#include "ir_static.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static unsigned char image[64+3*96+24];
static void u32(size_t p,uint32_t v){unsigned i;for(i=0;i<4;i++)image[p+i]=(unsigned char)(v>>(8*i));}
static void u64(size_t p,uint64_t v){unsigned i;for(i=0;i<8;i++)image[p+i]=(unsigned char)(v>>(8*i));}
static void seal(void){u32(56,irs_image_crc(image,sizeof image));}
static void make(void){
    unsigned i;memset(image,0,sizeof image);memcpy(image,"IRS4BIN1",8);
    u32(8,1);u32(12,0x01020304);u32(16,3);u32(20,1);u32(24,64);u64(40,192);u64(48,64);
    for(i=0;i<3;i++){size_t p=64+i*96;u32(p,2);u32(p+4,1);u32(p+8,i==2?3:1);u32(p+12,1);u64(p+16,i*64);u64(p+24,8);u64(p+32,2);u64(p+64,2);}
    u32(352,2);u32(356,0);u32(360,1);u32(364,UINT32_MAX);u32(368,2);seal();
}
static int sync_fail;
static uint32_t sync_cb(void *u,int direction){(void)u;return sync_fail==direction?IRS_SYNC_ERROR:IR_OK;}
static uint32_t recover_cb(void *u){(void)u;return sync_fail?IRS_SYNC_ERROR:IR_OK;}
static int backend_unknown;
static uint32_t query_cb(void *u,const ir_call *c,uint32_t n){(void)u;(void)c;(void)n;return IR_OK;}
static uint32_t execute_cb(void *u,const ir_call *c,uint32_t n,uint32_t *done,ir_node_profile *p,int *quiet){(void)u;(void)c;(void)n;(void)p;*done=0;*quiet=0;return IR_OK;}
static uint32_t backend_recover(void *u){(void)u;return backend_unknown?IRS_INVALID_STATE:IR_OK;}
int main(void){
    irs_info info;irs_context ctx={0};irs_tensor_state state[3];irs_lifetime inspect[3];ir_tensor ts[3];ir_call calls[1];ir_node_profile profiles[1];
    _Alignas(64) unsigned char a[192],w[64],s[64];int32_t x[2]={2,-3},y[2]={4,5};const void *out;uint64_t size;
    irs_platform platform={1,NULL,sync_cb,recover_cb,NULL,NULL};
    make();assert(irs_inspect_v2(image,sizeof image,64,&info,inspect,sizeof inspect)==IR_OK);
    assert(irs_inspect_v2(image,sizeof image-1,64,&info,inspect,sizeof inspect)!=IR_OK);
    image[100]^=1;assert(irs_inspect_v2(image,sizeof image,64,&info,inspect,sizeof inspect)!=IR_OK);make();
    assert(irs_check_span(UINT64_C(0xffffffff),1,32)==IR_OK);
    assert(irs_check_span(UINT64_C(0x100000000),1,32)!=IR_OK);
    assert(irs_check_span(0,UINT64_C(0x100000000),32)!=IR_OK);
    assert(irs_check_span(UINT64_MAX,2,64)!=IR_OK);
    memset(a,0,sizeof a);memset(w,0,sizeof w);memset(s,0,sizeof s);
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)==IR_OK);
    assert(irs_output(&ctx,2,&out,&size)==IRS_INVALID_STATE);
    assert(irs_input(&ctx,0,x,sizeof x)==IR_OK);assert(irs_input(&ctx,1,y,sizeof y)==IR_OK);
    assert(irs_run(&ctx)==IR_OK&&ctx.completed==1);
    assert(irs_output(&ctx,2,&out,&size)==IR_OK&&size==8);assert(((const int32_t*)out)[0]==6&&((const int32_t*)out)[1]==2);
    assert(irs_run(&ctx)==IR_INVALID_ARGUMENT);assert(irs_input(&ctx,0,x,sizeof x)==IR_OK);assert(irs_input(&ctx,1,y,sizeof y)==IR_OK);
    sync_fail=2;assert(irs_run(&ctx)==IRS_SYNC_ERROR&&ctx.completed==1);
    assert(irs_output(&ctx,2,&out,&size)==IRS_INVALID_STATE);assert(irs_close(&ctx)==IRS_INVALID_STATE);
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)==IRS_INVALID_STATE);
    assert(irs_recover(&ctx)!=IR_OK);sync_fail=0;assert(irs_recover(&ctx)==IR_OK);
    assert(irs_input(&ctx,0,x,sizeof x)==IR_OK);assert(irs_input(&ctx,1,y,sizeof y)==IR_OK);
    assert(irs_run(&ctx)==IR_OK);assert(irs_close(&ctx)==IR_OK);assert(irs_close(&ctx)==IR_OK);
    {irs_backend backend={1,NULL,query_cb,execute_cb,backend_recover};
     assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,&backend)==IR_OK);
     assert(irs_input(&ctx,0,x,sizeof x)==IR_OK);assert(irs_input(&ctx,1,y,sizeof y)==IR_OK);
     backend_unknown=1;assert(irs_run(&ctx)==IRS_SYNC_ERROR&&ctx.completed==0);assert(irs_close(&ctx)==IRS_INVALID_STATE);
     assert(irs_recover(&ctx)==IRS_INVALID_STATE);backend_unknown=0;assert(irs_recover(&ctx)==IR_OK);assert(irs_close(&ctx)==IR_OK);}
    make();u64(64+2*96+16,0);seal();
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)!=IR_OK);
    make();u32(356,2);seal();assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)!=IR_OK);
    make();assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,2,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)!=IR_OK);
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,a,64,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)!=IR_OK);
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a+1,sizeof a-1,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)!=IR_OK);
    make();u64(64+24,12);u64(64+64,3);seal();
    assert(irs_bind_v2(&ctx,image,sizeof image,w,0,a,sizeof a,s,sizeof s,ts,3,calls,1,profiles,state,3,inspect,sizeof inspect,&platform,NULL)==IR_OK);
    {int32_t padded[3]={2,-3,1};assert(irs_input(&ctx,0,padded,sizeof padded)==IR_INVALID_ARGUMENT);padded[2]=0;assert(irs_input(&ctx,0,padded,sizeof padded)==IR_OK);}
    assert(irs_close(&ctx)==IR_OK);
    puts("static native checks passed");return 0;
}
