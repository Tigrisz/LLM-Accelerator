/* T6 extra probe: no frozen fixture is changed; no Python at target runtime. */
#include "ir_static.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include <float.h>
#include "sample_blob.h"
_Static_assert(sizeof(void*)==4&&sizeof(size_t)==4,"ILP32 required");
_Static_assert(sizeof(float)==4&&FLT_MANT_DIG==24&&sizeof(double)==8&&DBL_MANT_DIG==53,"binary32/64 required");
_Static_assert(T5_INPUT_COUNT==2&&T5_OUTPUT_BYTES==8,"two-element add probe required");
static irs_context ctx;
static ir_tensor tensors[T5_TENSORS];static ir_call calls[T5_NODES];
static irs_tensor_state states[T5_TENSORS];static irs_lifetime inspect[T5_TENSORS];
_Alignas(T5_ALIGNMENT) static unsigned char activations[T5_ACT_BYTES];
_Alignas(T5_ALIGNMENT) static unsigned char workspace[T5_WORK_BYTES];
static void text(const char *p){while(*p)*(volatile uint32_t*)UINT32_C(0x10000000)=(unsigned char)*p++;}
static void key(const char *name,uint32_t n){int i;text(name);text("=");for(i=28;i>=0;i-=4){unsigned v=(n>>(unsigned)i)&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=v<10?'0'+v:'a'+v-10;}text("\n");}
static void bytes(const void *data,size_t n){const unsigned char *p=data;size_t i;text("RECOVER_OUTPUT=");for(i=0;i<n;i++){unsigned a=p[i]>>4,b=p[i]&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=a<10?'0'+a:'a'+a-10;*(volatile uint32_t*)UINT32_C(0x10000000)=b<10?'0'+b:'a'+b-10;}text("\n");}
static uint32_t sync_cpu(void *u,int d){(void)u;if(d!=1&&d!=2)return IRS_SYNC_ERROR;__asm__ volatile("fence iorw,iorw" ::: "memory");return IR_OK;}
clock_t clock(void){return (clock_t)-1;}
static uint32_t recover_cpu(void *u){(void)u;return IR_OK;}
static const irs_platform platform={1,NULL,sync_cpu,recover_cpu,NULL,NULL};
static uint32_t feed(int zero){uint32_t i,r;for(i=0;i<T5_INPUT_COUNT;i++){r=irs_input(&ctx,t5_inputs[i].index,zero?t5_inputs[i].zero:t5_inputs[i].normal,t5_inputs[i].size);if(r)return r;}return IR_OK;}
#define CHECK(expr,code) do{if(!(expr)){key("FAIL_AT",code);return code;}}while(0)
static uint32_t exercise(void){
    const void *out=NULL;uint64_t length=0;uint32_t i,r;
    uint32_t bad[2];const uint32_t invalid[]={UINT32_C(0x7fc00001),UINT32_C(0x7f800000),UINT32_C(0xff800000)};
    key("T5_RUNTIME_ABI",irs_runtime_abi_version());key("T5_POINTER_BYTES",sizeof(void*));
    CHECK(irs_bind_v2(&ctx,t5_image,sizeof t5_image,(void*)t5_weights,T5_WEIGHT_BYTES,activations,sizeof activations,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS,inspect,sizeof inspect,&platform,NULL)==IR_OK,1);
    CHECK(feed(0)==IR_OK,2);
    for(i=0;i<3;i++){
        memcpy(bad,t5_inputs[0].normal,sizeof bad);bad[0]=invalid[i];
        r=irs_input(&ctx,t5_inputs[0].index,bad,sizeof bad);key(i==0?"T6_NAN":i==1?"T6_POS_INF":"T6_NEG_INF",r);
        CHECK(r==IR_NONFINITE&&memcmp(tensors[t5_inputs[0].index].data,t5_inputs[0].normal,sizeof bad)==0,3);
    }
    key("T6_INPUT_ATOMIC",1);
    memset(tensors[T5_OUTPUT_INDEX].data,0x5a,T5_OUTPUT_BYTES);
    /* Caller-owned input corruption after irs_input: numeric core must also reject. */
    memcpy(tensors[t5_inputs[0].index].data,invalid,4);
    r=irs_run(&ctx);key("T6_NONFINITE_EXEC",r);CHECK(r==IR_NONFINITE&&irs_completed(&ctx)==0,4);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&out,&length)==IRS_INVALID_STATE,5);
    for(i=0;i<T5_OUTPUT_BYTES;i++)CHECK(((unsigned char*)tensors[T5_OUTPUT_INDEX].data)[i]==0x5a,6);
    CHECK(feed(0)==IR_OK,7);r=irs_run(&ctx);key("T6_OVERFLOW",r);key("T6_COMPLETED",irs_completed(&ctx));
    CHECK(r==IR_NUMERIC_OVERFLOW&&irs_completed(&ctx)==0&&irs_output(&ctx,T5_OUTPUT_INDEX,&out,&length)==IRS_INVALID_STATE,8);
    for(i=0;i<T5_OUTPUT_BYTES;i++)CHECK(((unsigned char*)tensors[T5_OUTPUT_INDEX].data)[i]==0x5a,9);
    key("T6_OUTPUT_ATOMIC",1);
    CHECK(feed(1)==IR_OK&&irs_run(&ctx)==IR_OK&&irs_completed(&ctx)==T5_NODES,10);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&out,&length)==IR_OK&&length==T5_OUTPUT_BYTES,11);
    bytes(out,(size_t)length);key("T6_RECOVERED",1);CHECK(irs_close(&ctx)==IR_OK,12);return 0;
}
int main(void){uint32_t r=exercise();key("T5_STATUS",r);return (int)r;}
