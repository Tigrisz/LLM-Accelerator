/* Standalone C11 runner. No Python, JSON parser or dynamic model discovery. */
#include "ir_pc.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>

int main(int argc,char **argv){
    irs_pc pc;irs_info info={0};irs_platform platform;irs_context *ctx=NULL;
    irs_block image={0},weights={0},inputs={0},act={0},scratch={0},meta={0},tensors={0},calls={0},profiles={0},states={0},inspect={0};
    irs_block *blocks[]={&profiles,&inspect,&states,&calls,&tensors,&meta,&scratch,&act,&inputs,&weights,&image};
    FILE *output=NULL;uint32_t status=IR_INVALID_ARGUMENT,i,profile_status=IR_OK;uint64_t offset=0,output_size=0;int close_ok=1,trace_complete=0,profile_available=0;
    if(argc!=6){fprintf(stderr,"usage: ir_static_host execution.bin weights.bin inputs.bin outputs.bin trace.json\n");return 2;}
    irs_pc_init(&pc,UINT64_C(67108864));platform=irs_pc_platform(&pc);
    /* Refuse overwrites, including trace/output aliases to inputs. */
    pc.trace=fopen(argv[5],"wx");if(!pc.trace){fprintf(stderr,"trace create failed\n");return 2;}
    if(fprintf(pc.trace,"{\"format\":\"inference-c-static-trace\",\"version\":1,\"clock\":\"host_monotonic_ns\",\"backend\":\"pc_c_static\",\"events\":[")<0)pc.trace_failed=1;
#define CHECK(expr) do {status=(expr);if(status!=IR_OK)goto cleanup;} while(0)
#define ALLOC(block,n,align) CHECK(irs_pc_alloc(&pc,(n),(align),&(block)))
#define ALLOC_KIND(block,n,align,kind) CHECK(irs_pc_alloc_kind(&pc,(n),(align),(kind),&(block)))
    CHECK(irs_pc_read(&pc,argv[1],UINT64_C(1048576),&image));
    CHECK(irs_read_info(image.data,(size_t)image.size,sizeof(uintptr_t)*CHAR_BIT,&info));
    ALLOC_KIND(inspect,irs_inspect_workspace_bytes(info.tensors),_Alignof(irs_lifetime)<4?4:_Alignof(irs_lifetime),IRS_RES_METADATA);
    CHECK(irs_inspect_v2(image.data,(size_t)image.size,sizeof(uintptr_t)*CHAR_BIT,&info,inspect.data,(size_t)inspect.size));
    CHECK(irs_pc_read(&pc,argv[2],info.weights,&weights));if(weights.size!=info.weights){status=IRS_IO_ERROR;goto cleanup;}
    if(weights.size)CHECK(irs_pc_reclassify(&pc,&weights,IRS_RES_ARENA));
    CHECK(irs_pc_read(&pc,argv[3],UINT64_C(67108864),&inputs));
    if(inputs.size)CHECK(irs_pc_reclassify(&pc,&inputs,IRS_RES_TASK));
    ALLOC(act,info.activations,info.alignment);ALLOC(scratch,info.workspace,info.alignment);
    /* File buffer is 64-aligned; weights arena must honor exported alignment. */
    if(weights.size&&(uintptr_t)weights.data%info.alignment){irs_block replacement={0};ALLOC(replacement,weights.size,info.alignment);memcpy(replacement.data,weights.data,(size_t)weights.size);irs_pc_free(&pc,&weights);weights=replacement;}
    ALLOC_KIND(meta,sizeof *ctx,64,IRS_RES_METADATA);ctx=meta.data;ALLOC_KIND(tensors,info.tensors*sizeof(ir_tensor),64,IRS_RES_METADATA);
    ALLOC_KIND(calls,info.nodes*sizeof(ir_call),64,IRS_RES_METADATA);ALLOC_KIND(states,irs_tensor_state_bytes(info.tensors),4,IRS_RES_METADATA);
    profile_status=irs_pc_alloc_kind(&pc,info.nodes*sizeof(ir_node_profile),64,IRS_RES_PROFILE,&profiles);
    if(profile_status==IR_RESOURCE_LIMIT)pc.observation_errors++;
    else if(profile_status!=IR_OK){status=profile_status;goto cleanup;}
    profile_available=profiles.data!=NULL;
    CHECK(irs_bind_v2(ctx,image.data,(size_t)image.size,weights.data,weights.size,act.data,act.size,scratch.data,scratch.size,
                   tensors.data,info.tensors,calls.data,info.nodes,profiles.data,states.data,info.tensors,inspect.data,(size_t)inspect.size,&platform,NULL));
    CHECK(irs_pc_free(&pc,&inspect)); /* binding retains state, not inspection storage */
    for(i=0;i<info.tensors;i++)if(irs_tensor_role(ctx,i)==1){uint64_t n=ctx->tensors[i].byte_length;
        if(offset>inputs.size||n>inputs.size-offset){status=IRS_IO_ERROR;goto cleanup;}
        CHECK(irs_input(ctx,i,(unsigned char*)inputs.data+(size_t)offset,n));offset+=n;}
    if(offset!=inputs.size){status=IRS_IO_ERROR;goto cleanup;}
    CHECK(irs_run(ctx));
    output=fopen(argv[4],"wx");if(!output){status=IRS_IO_ERROR;goto cleanup;}
    for(i=0;i<info.tensors;i++)if(irs_tensor_role(ctx,i)==3){const void *data;uint64_t n;
        CHECK(irs_output(ctx,i,&data,&n));if(fwrite(data,1,(size_t)n,output)!=n){status=IRS_IO_ERROR;goto cleanup;}output_size+=n;}
cleanup:
    if(output&&fclose(output)!=0)status=IRS_IO_ERROR;
    /* Only remove a file successfully created by this invocation. Existing
     * paths and failed exclusive opens never transfer ownership to us. */
    if(output&&status!=IR_OK&&remove(argv[4])!=0)fprintf(stderr,"partial output cleanup failed\n");
    if(fprintf(pc.trace,"],\"node_count\":%u,\"profile_available\":%s,\"profile_status\":%u,\"c_clock\":\"c_process_cpu\",\"ticks_per_second\":%llu,\"nodes\":[",ctx?ctx->info.nodes:0,profile_available?"true":"false",profile_status,(unsigned long long)ir_clock_ticks_per_second())<0)pc.trace_failed=1;
    if(ctx&&profiles.data)for(i=0;i<ctx->info.nodes;i++){
        const ir_node_profile *record=(const ir_node_profile*)profiles.data+i;
        if(fprintf(pc.trace,"%s{\"index\":%u,\"executed\":%s,\"status\":%u,\"timing_valid\":%s,\"start_ticks\":%llu,\"end_ticks\":%llu}",i?",":"",i,record->executed?"true":"false",record->status,record->timing_valid?"true":"false",(unsigned long long)record->start_ticks,(unsigned long long)record->end_ticks)<0)pc.trace_failed=1;
    }
    if(ctx&&ctx->state&&irs_close(ctx)!=IR_OK)close_ok=0;
    if(close_ok)for(i=0;i<sizeof blocks/sizeof blocks[0];i++)irs_pc_free(&pc,blocks[i]);
    /* Unknown state is deliberately retained until process exit. Real device
     * callers must recover; process exit is not a DMA quiescence guarantee. */
    trace_complete=!pc.trace_failed&&!pc.observation_errors;
    if(fprintf(pc.trace,"],\"resources\":{\"services_abi\":2,\"runtime_abi\":2,\"peak_bytes\":%llu,\"inspect_stack_reserved_bytes\":0,\"inspect_workspace_bytes\":%zu,\"tensor_state_bytes\":%zu,\"context_bytes\":%zu,\"categories\":[",(unsigned long long)pc.peak_used,irs_inspect_workspace_bytes(info.tensors),irs_tensor_state_bytes(info.tensors),sizeof(irs_context))<0)pc.trace_failed=1;
    for(i=0;i<IRS_RES_COUNT;i++)if(fprintf(pc.trace,"%s{\"category\":%u,\"live_bytes\":%llu,\"peak_bytes\":%llu}",i?",":"",i,(unsigned long long)pc.category_used[i],(unsigned long long)pc.category_peak[i])<0)pc.trace_failed=1;
    if(fprintf(pc.trace,"]},\"complete\":%s,\"status\":%u,\"output_bytes\":%llu,\"live_allocations\":%llu,\"live_backing_bytes\":%llu}\n",trace_complete?"true":"false",status,(unsigned long long)output_size,(unsigned long long)pc.allocations,(unsigned long long)pc.used)<0)pc.trace_failed=1;
    if(fclose(pc.trace)!=0)pc.trace_failed=1;
    fprintf(stdout,"{\"status\":%u,\"trace_complete\":%s,\"live_allocations\":%llu}\n",status,trace_complete&&!pc.trace_failed?"true":"false",(unsigned long long)pc.allocations);
    return status==IR_OK?0:1;
}
