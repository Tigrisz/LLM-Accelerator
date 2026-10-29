/* T5: identical sample shape/storage/data, actual outputs only (no golden). */
#include "ir_static.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include "sample_blob.h"
_Static_assert(sizeof(void*)==4&&sizeof(size_t)==4,"ILP32 required");
_Static_assert(IRS_RUNTIME_ABI_VERSION==2,"native ABI2 required");
static irs_context ctx;
static ir_tensor tensors[T5_TENSORS];static ir_call calls[T5_NODES];
static irs_tensor_state states[T5_TENSORS];static irs_lifetime inspect[T5_TENSORS];
_Alignas(T5_ALIGNMENT) static unsigned char activations[T5_ACT_BYTES];
_Alignas(T5_ALIGNMENT) static unsigned char workspace[T5_WORK_BYTES];
#if !T5_OVERFLOW_PROBE
static unsigned char damaged[sizeof t5_image];
static unsigned checks;
#endif
static unsigned fail_sync,publishes,acquires;
static void text(const char *p){while(*p)*(volatile uint32_t*)UINT32_C(0x10000000)=(unsigned char)*p++;}
static void hexkey(const char *key,uint32_t value){int i;text(key);text("=");for(i=28;i>=0;i-=4){unsigned n=(value>>(unsigned)i)&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=(uint32_t)(n<10?'0'+n:'a'+n-10);}text("\n");}
static void output(const char *key,const void *data,uint64_t size){const unsigned char *p=data;uint64_t i;text(key);text("=");for(i=0;i<size;i++){unsigned a=p[i]>>4,b=p[i]&15u;*(volatile uint32_t*)UINT32_C(0x10000000)=(uint32_t)(a<10?'0'+a:'a'+a-10);*(volatile uint32_t*)UINT32_C(0x10000000)=(uint32_t)(b<10?'0'+b:'a'+b-10);}text("\n");}
static uint32_t sync_cpu(void *user,int direction){(void)user;if(direction==1)publishes++;else if(direction==2)acquires++;else return IRS_SYNC_ERROR;__asm__ volatile("fence iorw,iorw" ::: "memory");return fail_sync==(unsigned)direction?IRS_SYNC_ERROR:IR_OK;}
static uint32_t recover_cpu(void *user){(void)user;return fail_sync?IRS_SYNC_ERROR:IR_OK;}
clock_t clock(void){return (clock_t)-1;}
static const irs_platform platform={1,NULL,sync_cpu,recover_cpu,NULL,NULL};
static uint32_t bind(void){return irs_bind_v2(&ctx,t5_image,sizeof t5_image,(void*)t5_weights,T5_WEIGHT_BYTES,activations,sizeof activations,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS,inspect,sizeof inspect,&platform,NULL);}
static uint32_t feed(int zero){uint32_t i,r;for(i=0;i<T5_INPUT_COUNT;i++){r=irs_input(&ctx,t5_inputs[i].index,zero?t5_inputs[i].zero:t5_inputs[i].normal,t5_inputs[i].size);if(r)return r;}return IR_OK;}
#define CHECK(value,code) do{if(!(value)){hexkey("FAIL_AT",code);return code;}}while(0)
static uint32_t exercise(void){
    irs_info info;const void *data=NULL;uint64_t size=0;uint32_t r,i;
    hexkey("T5_RUNTIME_ABI",irs_runtime_abi_version());hexkey("T5_POINTER_BYTES",sizeof(void*));
    CHECK(irs_read_info(t5_image,sizeof t5_image,32,&info)==IR_OK,1);
    CHECK(irs_context_size()==sizeof ctx&&ir_tensor_struct_size()==sizeof(ir_tensor)&&ir_call_struct_size()==sizeof(ir_call),2);
#if T5_OVERFLOW_PROBE
    CHECK(bind()==IR_OK&&feed(0)==IR_OK,3);
    memset(tensors[T5_OUTPUT_INDEX].data,0x5a,T5_OUTPUT_BYTES);
    r=irs_run(&ctx);hexkey("T5_OVERFLOW_STATUS",r);hexkey("T5_OVERFLOW_NODES",irs_completed(&ctx));
    CHECK(r==IR_NUMERIC_OVERFLOW&&irs_completed(&ctx)==0,4);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IRS_INVALID_STATE,5);
    for(i=0;i<T5_OUTPUT_BYTES;i++)CHECK(((unsigned char*)tensors[T5_OUTPUT_INDEX].data)[i]==0x5a,6);
    hexkey("T5_ATOMIC",1);CHECK(feed(1)==IR_OK&&irs_run(&ctx)==IR_OK,7);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IR_OK&&size==T5_OUTPUT_BYTES,8);
    output("RECOVER_OUTPUT",data,size);hexkey("T5_REPAIRED",1);CHECK(irs_close(&ctx)==IR_OK,9);
#else
    CHECK(irs_read_info(t5_image,sizeof t5_image-1,32,&info)!=IR_OK,3);checks|=1u;
    memcpy(damaged,t5_image,sizeof damaged);damaged[64]^=1u;
    CHECK(irs_read_info(damaged,sizeof damaged,32,&info)!=IR_OK,4);checks|=2u;
    CHECK(irs_inspect_v2(t5_image,sizeof t5_image,32,&info,inspect,sizeof inspect-1)==IR_RESOURCE_LIMIT,5);checks|=4u;
    CHECK(irs_bind_v2(&ctx,t5_image,sizeof t5_image,(void*)t5_weights,T5_WEIGHT_BYTES,activations,sizeof activations,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS-1,inspect,sizeof inspect,&platform,NULL)==IR_RESOURCE_LIMIT,6);checks|=8u;
    CHECK(irs_bind_v2(&ctx,t5_image,sizeof t5_image,(void*)t5_weights,T5_WEIGHT_BYTES,activations,sizeof activations-1,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS,inspect,sizeof inspect,&platform,NULL)!=IR_OK,7);
    CHECK(irs_bind_v2(&ctx,t5_image,sizeof t5_image,(void*)t5_weights,T5_WEIGHT_BYTES,activations+1,sizeof activations-1,workspace,sizeof workspace,tensors,T5_TENSORS,calls,T5_NODES,NULL,states,T5_TENSORS,inspect,sizeof inspect,&platform,NULL)!=IR_OK,8);checks|=16u;
    CHECK(irs_check_span(UINT64_C(0xffffffff),1,32)==IR_OK&&irs_check_span(UINT64_C(0xffffffff),2,32)!=IR_OK,9);checks|=32u;
    CHECK(bind()==IR_OK,10);memset(inspect,0xa5,sizeof inspect);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IRS_INVALID_STATE,11);checks|=64u;
    CHECK(irs_run(&ctx)==IR_INVALID_ARGUMENT,12);checks|=128u;
    CHECK(irs_input(&ctx,t5_inputs[0].index,t5_inputs[0].normal,t5_inputs[0].size-1)==IR_INVALID_ARGUMENT,13);checks|=256u;
    for(i=0;i<3;i++){
        CHECK(feed(i==1)==IR_OK,14);r=irs_run(&ctx);CHECK(r==IR_OK&&irs_completed(&ctx)==T5_NODES,15);
        hexkey(i==0?"RUN_0_NODES":i==1?"RUN_1_NODES":"RUN_2_NODES",irs_completed(&ctx));
        CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IR_OK&&size==T5_OUTPUT_BYTES,16);
        output(i==0?"RUN_0_OUTPUT":i==1?"RUN_1_OUTPUT":"RUN_2_OUTPUT",data,size);
        CHECK(irs_run(&ctx)==IR_INVALID_ARGUMENT,17);checks|=512u;
        CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IRS_INVALID_STATE,18);checks|=1024u;
    }
    CHECK(feed(0)==IR_OK,19);fail_sync=2;
    CHECK(irs_run(&ctx)==IRS_SYNC_ERROR&&irs_completed(&ctx)==T5_NODES,20);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IRS_INVALID_STATE&&irs_close(&ctx)==IRS_INVALID_STATE,21);
    CHECK(irs_recover(&ctx)!=IR_OK,22);fail_sync=0;CHECK(irs_recover(&ctx)==IR_OK,23);checks|=2048u;
    CHECK(feed(0)==IR_OK&&irs_run(&ctx)==IR_OK,24);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IR_OK&&size==T5_OUTPUT_BYTES,25);output("RECOVER_OUTPUT",data,size);
    CHECK(irs_close(&ctx)==IR_OK&&bind()==IR_OK&&feed(0)==IR_OK&&irs_run(&ctx)==IR_OK,26);
    CHECK(irs_output(&ctx,T5_OUTPUT_INDEX,&data,&size)==IR_OK&&size==T5_OUTPUT_BYTES,27);output("REBIND_OUTPUT",data,size);
    CHECK(irs_close(&ctx)==IR_OK,28);checks|=4096u;
    hexkey("T5_SYNC_PUBLISH",publishes);hexkey("T5_SYNC_ACQUIRE",acquires);hexkey("T5_CHECKS_MASK",checks);
#endif
    return 0;
}
int main(void){uint32_t r=exercise();hexkey("T5_STATUS",r);return (int)r;}
