/* Original chain, third-node fault injection; no whole-graph rollback claim. */
#include "ir_static.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include "sample_blob.h"
_Static_assert(sizeof(void*)==4&&IRS_RUNTIME_ABI_VERSION==2,"RV32 ABI2 required");
_Static_assert(T5_NODES==4&&T5_TENSORS==9&&T5_INPUT_COUNT==1,"Original four-node chain required");
static irs_context ctx;static ir_tensor tensors[T5_TENSORS];static ir_call calls[T5_NODES];
static irs_tensor_state states[T5_TENSORS];static irs_lifetime inspect[T5_TENSORS];
_Alignas(T5_ALIGNMENT) static unsigned char weights[T5_WEIGHT_BYTES],activations[T5_ACT_BYTES],workspace[T5_WORK_BYTES];
static void text(const char *p){while(*p)*(volatile uint32_t*)UINT32_C(0x10000000)=(unsigned char)*p++;}
static void key(const char *s,uint32_t n){int i;text(s);text("=");for(i=28;i>=0;i-=4){unsigned v=(n>>(unsigned)i)&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=v<10?'0'+v:'a'+v-10;}text("\n");}
static void bytes(const char *s,const void *data,uint64_t n){const unsigned char *p=data;uint64_t i;text(s);text("=");for(i=0;i<n;i++){unsigned a=p[i]>>4,b=p[i]&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=a<10?'0'+a:'a'+a-10;*(volatile uint32_t*)UINT32_C(0x10000000)=b<10?'0'+b:'a'+b-10;}text("\n");}
static uint32_t sync_cpu(void *u,int d){(void)u;if(d!=1&&d!=2)return IRS_SYNC_ERROR;__asm__ volatile("fence iorw,iorw" ::: "memory");return IR_OK;}
static uint32_t recover_cpu(void *u){(void)u;return IR_OK;}
static const irs_platform platform={1,NULL,sync_cpu,recover_cpu,NULL,NULL};
clock_t clock(void){return (clock_t)-1;}
#define CHECK(x,c) do{if(!(x)){key("FAIL_AT",c);return c;}}while(0)
static uint32_t feed(int zero){return irs_input(&ctx,t5_inputs[0].index,zero?t5_inputs[0].zero:t5_inputs[0].normal,t5_inputs[0].size);}
static uint32_t exercise(void){
    uint32_t saved,bad=T7_IS_FP32?UINT32_C(0x7fc00001):UINT32_C(0x7fffffff),r;const void *out=NULL;uint64_t n=0;
    key("T5_RUNTIME_ABI",irs_runtime_abi_version());key("T5_POINTER_BYTES",sizeof(void*));memcpy(weights,t5_weights,T5_WEIGHT_BYTES);
    CHECK(irs_bind_v2(&ctx,t5_image,sizeof t5_image,weights,sizeof weights,activations,sizeof activations,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS,inspect,sizeof inspect,&platform,NULL)==IR_OK,1);
    CHECK(feed(0)==IR_OK,2);memcpy(&saved,tensors[T7_DELTA_INDEX].data,4);memcpy(tensors[T7_DELTA_INDEX].data,&bad,4);
    r=irs_run(&ctx);key("T7_FAILURE",r);key("T7_COMPLETED",irs_completed(&ctx));
    CHECK(r==(T7_IS_FP32?IR_NONFINITE:IR_NUMERIC_OVERFLOW)&&irs_completed(&ctx)==2,3);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&out,&n)==IRS_INVALID_STATE,4);key("T7_OUTPUT_INVALID",1);
    /* Earlier nodes have committed and may reuse y's physical slot. Restore the injected data. */
    memcpy(tensors[T7_DELTA_INDEX].data,&saved,4);CHECK(feed(0)==IR_OK&&irs_run(&ctx)==IR_OK,5);key("T7_RECOVERED_NODES",irs_completed(&ctx));
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&out,&n)==IR_OK&&n==T5_OUTPUT_BYTES,6);bytes("RECOVER_OUTPUT",out,n);
    CHECK(feed(1)==IR_OK&&irs_run(&ctx)==IR_OK,7);key("T7_ZERO_NODES",irs_completed(&ctx));
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&out,&n)==IR_OK&&n==T5_OUTPUT_BYTES,8);bytes("ZERO_OUTPUT",out,n);
    CHECK(irs_close(&ctx)==IR_OK,9);key("T7_CLOSED",1);return 0;
}
int main(void){uint32_t r=exercise();key("T5_STATUS",r);return (int)r;}
