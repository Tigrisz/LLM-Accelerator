/* Reuse the independent tiny-image builder and S4 contract assertions. */
#define main static_contract_main
#include "test_static.c"
#undef main
#include "ir_pc.h"

int main(void){
    irs_tensor_state state[3];irs_lifetime inspect[3];irs_pc pc;irs_block blocks[6]={{0}};irs_platform platform;irs_context *ctx;
    uint32_t i,j;uint64_t baseline;int32_t x[2]={2,-3},y[2]={4,5};
    assert(static_contract_main()==0);
    irs_pc_init(&pc,65536);pc.category_limits[IRS_RES_METADATA]=70;
    assert(irs_pc_alloc_kind(&pc,8,64,IRS_RES_METADATA,&blocks[0])==IR_RESOURCE_LIMIT&&pc.used==0);
    pc.category_limits[IRS_RES_METADATA]=65536;
    assert(irs_pc_alloc_kind(&pc,8,64,IRS_RES_METADATA,&blocks[0])==IR_OK);
    assert(pc.category_used[IRS_RES_METADATA]==71&&pc.peak_used==71);irs_pc_free(&pc,&blocks[0]);
    for(j=0;j<6;j++){
        uint32_t status=IR_OK;irs_pc_init(&pc,65536);pc.fail_after=(int)j;
        for(i=0;i<6;i++){status=irs_pc_alloc_kind(&pc,64,64,i%IRS_RES_COUNT,&blocks[i]);if(status!=IR_OK)break;}
        assert(status==IR_RESOURCE_LIMIT);
        for(i=0;i<6;i++)irs_pc_free(&pc,&blocks[i]);
        assert(pc.used==0&&pc.allocations==0);for(i=0;i<IRS_RES_COUNT;i++)assert(pc.category_used[i]==0);
    }
    irs_pc_init(&pc,65536);platform=irs_pc_platform(&pc);make();
    assert(irs_pc_alloc_kind(&pc,192,64,IRS_RES_ARENA,&blocks[0])==IR_OK);
    assert(irs_pc_alloc_kind(&pc,64,64,IRS_RES_ARENA,&blocks[1])==IR_OK);
    assert(irs_pc_alloc_kind(&pc,sizeof(irs_context),64,IRS_RES_METADATA,&blocks[2])==IR_OK);
    assert(irs_pc_alloc_kind(&pc,3*sizeof(ir_tensor),64,IRS_RES_METADATA,&blocks[3])==IR_OK);
    assert(irs_pc_alloc_kind(&pc,sizeof(ir_call),64,IRS_RES_METADATA,&blocks[4])==IR_OK);
    assert(irs_pc_alloc_kind(&pc,sizeof(ir_node_profile),64,IRS_RES_PROFILE,&blocks[5])==IR_OK);
    ctx=blocks[2].data;
    assert(irs_bind_v2(ctx,image,sizeof image,NULL,0,blocks[0].data,192,blocks[1].data,64,blocks[3].data,3,blocks[4].data,1,blocks[5].data,state,3,inspect,sizeof inspect,&platform,NULL)==IR_OK);
    baseline=pc.used;
    assert(irs_pc_check_transient(&pc,IRS_RES_METADATA,irs_inspect_workspace_bytes(3))==IR_OK);
    assert(irs_pc_check_transient(&pc,IRS_RES_METADATA,65536)==IR_RESOURCE_LIMIT&&pc.used==baseline);
    for(i=0;i<1000;i++){
        const void *output;uint64_t size;
        assert(irs_input(ctx,0,x,sizeof x)==IR_OK&&irs_input(ctx,1,y,sizeof y)==IR_OK);
        assert(irs_run(ctx)==IR_OK&&ctx->completed==1);
        assert(irs_output(ctx,2,&output,&size)==IR_OK&&((const int32_t*)output)[0]==6&&((const int32_t*)output)[1]==2);
        assert(pc.used==baseline&&pc.allocations==6);
    }
    pc.sync_fail=2;assert(irs_input(ctx,0,x,sizeof x)==IR_OK&&irs_input(ctx,1,y,sizeof y)==IR_OK);
    assert(irs_run(ctx)==IRS_SYNC_ERROR&&irs_close(ctx)==IRS_INVALID_STATE&&pc.used==baseline);
    assert(irs_recover(ctx)!=IR_OK);pc.sync_fail=0;assert(irs_recover(ctx)==IR_OK&&irs_close(ctx)==IR_OK);
    for(i=0;i<6;i++)irs_pc_free(&pc,&blocks[i]);
    assert(pc.used==0&&pc.allocations==0);
    printf("{\"iterations\":1000,\"live_bytes\":%llu,\"peak_bytes\":%llu,\"allocation_failures\":6,\"recovery_released\":true}\n",(unsigned long long)pc.used,(unsigned long long)pc.peak_used);
    return 0;
}
