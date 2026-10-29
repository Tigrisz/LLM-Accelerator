#ifndef IR_STATIC_H
#define IR_STATIC_H
#include "ir_core.h"
#define IRS_API_VERSION 1u
#define IRS_IO_ERROR 7u
#define IRS_INVALID_STATE 8u
#define IRS_SYNC_ERROR 9u
#define IRS_MAX_TENSORS 4096u

/* Wire v1: 64-byte header, 96-byte tensors, 24-byte nodes, all little endian.
 * CRC32 is corruption detection, not authentication. No pointers on disk. */
typedef struct {uint32_t tensors,nodes,alignment;uint64_t weights,activations,workspace;} irs_info;
typedef struct {
    uint32_t api_version;void *user;
    uint32_t (*sync)(void *user,int direction); /* 1 publish, 2 acquire; nonzero => unknown */
    uint32_t (*recover)(void *user); /* 0 confirms quiescence */
    int (*now_ns)(void *user,uint64_t *ns); /* 1 valid monotonic host ns */
    void (*trace)(void *user,const char *event,uint32_t status,uint32_t completed,uint64_t ns,int valid);
} irs_platform;
typedef struct {
    uint32_t api_version;void *user;
    uint32_t (*query)(void *user,const ir_call *calls,uint32_t count);
    uint32_t (*execute)(void *user,const ir_call *calls,uint32_t count,uint32_t *completed,ir_node_profile *profiles,int *quiescent);
    uint32_t (*recover)(void *user);
} irs_backend;
typedef struct {
    irs_info info;ir_tensor *tensors;ir_call *calls;ir_node_profile *profiles;
    irs_platform platform;irs_backend backend;
    uint32_t state,completed,last_status;int valid_output,sync_unknown,backend_unknown;
    uint32_t roles[IRS_MAX_TENSORS]; /* caller-owned context; no runtime malloc */
    unsigned char supplied[IRS_MAX_TENSORS];
    uint64_t last_ns;int have_time;
} irs_context;

IR_API uint32_t irs_image_crc(const void *image,size_t size);
IR_API uint32_t irs_crc32(const void *data,size_t size);
IR_API uint32_t irs_check_span(uint64_t address,uint64_t length,unsigned bits);
IR_API uint32_t irs_inspect(const void *image,size_t size,unsigned address_bits,irs_info *info);
/* Context must be zero-initialized before its first bind. All metadata, image,
 * buffers and supplied services must be disjoint. Arenas
 * remain owned by caller and must survive unknown state until recover succeeds.
 * No mutation of calls/tensors/services by caller while bound; single thread. */
IR_API uint32_t irs_bind(irs_context *ctx,const void *image,size_t image_size,
    void *weights,uint64_t weight_bytes,void *activations,uint64_t activation_bytes,void *workspace,uint64_t workspace_bytes,
    ir_tensor *tensors,uint32_t tensor_capacity,ir_call *calls,uint32_t call_capacity,
    ir_node_profile *profiles,const irs_platform *platform,const irs_backend *backend);
IR_API uint32_t irs_input(irs_context *ctx,uint32_t index,const void *data,uint64_t size);
IR_API uint32_t irs_output(irs_context *ctx,uint32_t index,const void **data,uint64_t *size);
IR_API uint32_t irs_run(irs_context *ctx);
IR_API uint32_t irs_recover(irs_context *ctx);
IR_API uint32_t irs_close(irs_context *ctx);
IR_API size_t irs_context_size(void);
IR_API uint32_t irs_completed(const irs_context *ctx);
IR_API size_t irs_inspect_scratch_bytes(void);
#endif
