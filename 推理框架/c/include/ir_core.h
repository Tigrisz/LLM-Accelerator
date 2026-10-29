#ifndef IR_CORE_H
#define IR_CORE_H

#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define IR_API __declspec(dllexport)
#else
#define IR_API
#endif

#define IR_ABI_VERSION 1u
#define IR_MAX_RANK 4u
#define IR_MAX_ELEMENTS UINT64_C(1048576)
#define IR_MAX_CHAIN 1024u

typedef enum {
    IR_OK = 0, IR_INVALID_ARGUMENT = 1, IR_INVALID_SHAPE = 2,
    IR_UNSUPPORTED = 3, IR_RESOURCE_LIMIT = 4, IR_NONFINITE = 5,
    IR_NUMERIC_OVERFLOW = 6
} ir_status;
typedef enum { IR_FLOAT32 = 1, IR_INT32 = 2 } ir_dtype;
typedef enum { IR_ROW_MAJOR = 1 } ir_layout;
typedef enum { IR_LINEAR = 1, IR_ADD = 2, IR_RELU = 3 } ir_op;

/* Native in-process ABI, never an on-disk format. Unused dimensions are ignored.
 * Caller owns every buffer. byte_length is the available buffer capacity. */
typedef struct {
    void *data;
    uint64_t byte_length;
    uint32_t dtype;
    uint32_t layout;
    uint32_t rank;
    uint64_t shape[IR_MAX_RANK];
    uint64_t storage_shape[IR_MAX_RANK];
} ir_tensor;

/* LINEAR: a=W, b=x, optional bias. ADD: a+b, no bias. RELU: a, b/bias=NULL.
 * Output and workspace must not overlap inputs or each other.
 * Workspace needs product(output.shape)*4 bytes, aligned for float/int32_t. */
typedef struct {
    uint32_t op;
    const ir_tensor *a;
    const ir_tensor *b;
    const ir_tensor *bias;
    ir_tensor *output;
    void *workspace;
    uint64_t workspace_bytes;
} ir_call;

/* Optional observation ABI. CPU ticks are process clock(), never device time.
 * status/ticks are meaningful only when executed/timing_valid respectively. */
typedef struct {
    uint32_t executed;
    uint32_t status;
    uint64_t start_ticks;
    uint64_t end_ticks;
    uint32_t timing_valid;
    uint32_t reserved;
} ir_node_profile;

IR_API uint32_t ir_abi_version(void);
IR_API size_t ir_tensor_struct_size(void);
IR_API size_t ir_call_struct_size(void);
IR_API const char *ir_status_name(ir_status status);
IR_API ir_status ir_query(const ir_call *call);
IR_API ir_status ir_execute(const ir_call *call);
/* Prevalidates all call metadata. On a numeric failure, earlier successful
 * calls remain committed; failing/later outputs remain unchanged.
 * completed_steps must be independent of the call array, tensor descriptors,
 * declared tensor buffers and workspaces. For a valid count, overlap or an
 * invalid declared span is rejected before writing completed_steps. */
IR_API ir_status ir_execute_chain(const ir_call *calls, uint32_t count,
                                 uint32_t *completed_steps);
IR_API size_t ir_profile_struct_size(void);
IR_API uint64_t ir_clock_ticks_per_second(void);
/* Needs count independent profile records. Invalid observation span/capacity
 * is rejected before any writes. Metadata failure leaves profiles unchanged.
 * Executed numerical failure is recorded; later records have executed=0. */
IR_API ir_status ir_execute_chain_profiled(const ir_call *calls, uint32_t count,
    uint32_t *completed_steps, ir_node_profile *profiles, uint32_t capacity);
#endif
