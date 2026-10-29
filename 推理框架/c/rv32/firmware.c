/* T4 bare-metal integration harness: no heap, OS, file reader or DMA. */
#include "ir_static.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include "chain_blob.h"
#ifndef T4_BAD_EXPECTED
#define T4_BAD_EXPECTED 0
#endif
_Static_assert(sizeof(void*)==4&&sizeof(size_t)==4&&sizeof(int)==4,"RV32 ILP32 required");
_Static_assert(IRS_RUNTIME_ABI_VERSION==2,"native ABI2 required");
static irs_context ctx;
static ir_tensor tensors[T4_TENSORS];
static ir_call calls[T4_NODES];
static irs_tensor_state states[T4_TENSORS];
static irs_lifetime inspect[T4_TENSORS];
_Alignas(T4_ALIGNMENT) static unsigned char activations[T4_ACT_BYTES];
_Alignas(T4_ALIGNMENT) static unsigned char workspace[T4_WORK_BYTES];
static unsigned sync_publish,sync_acquire;

static void puts_mmio(const char *s){while(*s)*(volatile uint32_t*)UINT32_C(0x10000000)=(unsigned char)*s++;}
static void hexkey(const char *key,uint32_t value){int i;puts_mmio(key);puts_mmio("=");for(i=28;i>=0;i-=4){unsigned n=(value>>(unsigned)i)&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=(uint32_t)(n<10?'0'+n:'a'+n-10);}puts_mmio("\n");}
static uint32_t sync_cpu(void *user,int direction){(void)user;if(direction==1)sync_publish++;else if(direction==2)sync_acquire++;else return IRS_SYNC_ERROR;__asm__ volatile("fence iorw,iorw" ::: "memory");return IR_OK;}
static uint32_t recover_cpu(void *user){(void)user;return IR_OK;} /* synchronous same-hart CPU/TCM, no background master */
/* clock() profiles are unavailable; never fabricate valid ticks. */
clock_t clock(void){return (clock_t)-1;}
#define CHECK(c,code) do{if(!(c)){hexkey("FAIL_AT",(code));return (code);}}while(0)

static uint32_t exercise(void){
    irs_info info;irs_platform platform={1,NULL,sync_cpu,recover_cpu,NULL,NULL};uint32_t code,pass,last_completed=0;
    const void *out;uint64_t length;uint32_t negative_checks=0;
    CHECK(irs_read_info(t4_image,sizeof t4_image,32,&info)==IR_OK,1);
    CHECK(info.tensors==T4_TENSORS&&info.nodes==4,2);
    CHECK(irs_context_size()==sizeof ctx&&ir_tensor_struct_size()==sizeof(ir_tensor)&&ir_call_struct_size()==sizeof(ir_call)&&ir_abi_version()==1,14);
    CHECK(irs_read_info(t4_image,sizeof t4_image-1,32,&info)!=IR_OK,3);negative_checks++;
    CHECK(irs_inspect_v2(t4_image,sizeof t4_image,32,&info,inspect,sizeof inspect-1)==IR_RESOURCE_LIMIT,4);negative_checks++;
    CHECK(irs_bind_v2(&ctx,t4_image,sizeof t4_image,(void*)t4_weights,sizeof t4_weights,activations,sizeof activations,workspace,sizeof workspace,
        tensors,T4_TENSORS,calls,T4_NODES,NULL,states,T4_TENSORS-1,inspect,sizeof inspect,&platform,NULL)==IR_RESOURCE_LIMIT,5);negative_checks++;
    hexkey("INSPECT_STATUS",irs_inspect_v2(t4_image,sizeof t4_image,32,&info,inspect,sizeof inspect));
    hexkey("WEIGHT_CRC",irs_crc32(t4_weights,sizeof t4_weights));
    code=irs_bind_v2(&ctx,t4_image,sizeof t4_image,(void*)t4_weights,sizeof t4_weights,activations,sizeof activations,workspace,sizeof workspace,
        tensors,T4_TENSORS,calls,T4_NODES,NULL,states,T4_TENSORS,inspect,sizeof inspect,&platform,NULL);
    hexkey("BIND_STATUS",code);hexkey("BOUND_NODES",ctx.info.nodes);CHECK(code==IR_OK,6);
    memset(inspect,0xa5,sizeof inspect); /* no retention of temporary inspection memory */
    hexkey("NEGATIVE_CHECKS",negative_checks);
    hexkey("RUNTIME_ABI",irs_runtime_abi_version());hexkey("POINTER_BYTES",sizeof(void*));
    hexkey("CONTEXT_BYTES",sizeof(irs_context));hexkey("TENSOR_BYTES",sizeof(ir_tensor));hexkey("CALL_BYTES",sizeof(ir_call));
    hexkey("PROFILE_BYTES",sizeof(ir_node_profile));hexkey("STATE_BYTES",sizeof states);hexkey("INSPECT_BYTES",sizeof inspect);
    hexkey("CONTEXT_ALIGN",_Alignof(irs_context));hexkey("TENSOR_ALIGN",_Alignof(ir_tensor));hexkey("CALL_ALIGN",_Alignof(ir_call));
    hexkey("PROFILE_AVAILABLE",0);hexkey("TIME_NS_AVAILABLE",0);
    for(pass=0;pass<2;pass++){
        const int32_t *feed=pass?t4_zero_input:t4_normal_input;
        CHECK(irs_input(&ctx,T4_INPUT_INDEX,feed,3*sizeof(int32_t))==IR_OK,7);
        code=irs_run(&ctx);last_completed=irs_completed(&ctx);CHECK(code==IR_OK&&last_completed==4,8);
        CHECK(irs_output(&ctx,T4_OUTPUT_INDEX,&out,&length)==IR_OK&&length==2*sizeof(int32_t),9);
        {const int32_t *values=out;const int32_t *expected=pass?t4_zero_expected:t4_normal_expected;
         hexkey(pass?"ZERO_0":"VALUE_0",(uint32_t)values[0]);hexkey(pass?"ZERO_1":"VALUE_1",(uint32_t)values[1]);
         CHECK(values[0]==expected[0]+(!pass&&T4_BAD_EXPECTED?1:0)&&values[1]==expected[1],10);}
        CHECK(irs_run(&ctx)==IR_INVALID_ARGUMENT,11); /* must supply new inputs */
    }
    hexkey("COMPLETED",last_completed);hexkey("SYNC_PUBLISH",sync_publish);hexkey("SYNC_ACQUIRE",sync_acquire);
    CHECK(sync_publish==2&&sync_acquire==2,12);
    CHECK(irs_close(&ctx)==IR_OK,13);return 0;
}
int main(void){uint32_t code=exercise();hexkey("TARGET_STATUS",code);return (int)code;}
