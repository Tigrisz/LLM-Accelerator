#ifndef IR_PC_H
#define IR_PC_H
#include "ir_static.h"
#include <stdio.h>
#define IRS_PC_SERVICES_ABI 2u /* irs_pc/irs_block extended: recompile C clients. */
enum {IRS_RES_ARENA=0,IRS_RES_METADATA=1,IRS_RES_PROFILE=2,IRS_RES_TRACE=3,IRS_RES_TASK=4,IRS_RES_SOURCE=5,IRS_RES_COUNT=6};
typedef struct {void *user;uint64_t size;uint32_t (*read_at)(void*,uint64_t,void*,size_t,size_t*);} irs_reader;
typedef struct {void *raw,*data,*owner;uint64_t charge,size;uint32_t category;} irs_block;
/* Blocks must start zero-initialized, are move-only, and may only be freed
 * through their owner. alloc/read reject a nonempty destination unchanged. */
typedef struct {
    uint64_t budget,used,allocations;int fail_after,sync_fail,clock_unavailable;
    FILE *trace;uint32_t events,observation_errors;int trace_failed;
    uint64_t peak_used,peak_allocations,rejected_allocations;
    uint64_t category_used[IRS_RES_COUNT],category_peak[IRS_RES_COUNT],category_limits[IRS_RES_COUNT];
} irs_pc;
IR_API void irs_pc_init(irs_pc *pc,uint64_t budget);
IR_API uint32_t irs_read_exact(const irs_reader *r,uint64_t offset,void *dst,uint64_t size);
IR_API uint32_t irs_pc_alloc(irs_pc *pc,uint64_t size,uint32_t alignment,irs_block *out);
IR_API uint32_t irs_pc_alloc_kind(irs_pc *pc,uint64_t size,uint32_t alignment,uint32_t category,irs_block *out);
IR_API uint32_t irs_pc_reclassify(irs_pc *pc,irs_block *block,uint32_t category);
/* Preflight a synchronous fixed stack working set; records its reserved peak. */
IR_API uint32_t irs_pc_check_transient(irs_pc *pc,uint32_t category,uint64_t bytes);
IR_API uint32_t irs_pc_free(irs_pc *pc,irs_block *block);
IR_API uint32_t irs_pc_read(irs_pc *pc,const char *path,uint64_t limit,irs_block *out);
IR_API irs_platform irs_pc_platform(irs_pc *pc);
#endif
