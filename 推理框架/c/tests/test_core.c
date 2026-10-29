#include "ir_core.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); return 1; } \
} while (0)

static ir_tensor vector(void *data, uint32_t dtype, uint64_t length) {
    ir_tensor t = {0};
    t.data = data; t.byte_length = length * 4; t.dtype = dtype;
    t.layout = IR_ROW_MAJOR; t.rank = 1;
    t.shape[0] = length; t.storage_shape[0] = length;
    return t;
}

int main(void) {
    int32_t a_data[] = {1, INT32_MAX}, b_data[] = {2, 1}, out_data[] = {-99, -99};
    int32_t scratch[2];
    ir_tensor a = vector(a_data, IR_INT32, 2), b = vector(b_data, IR_INT32, 2);
    ir_tensor out = vector(out_data, IR_INT32, 2);
    ir_call call = {IR_ADD, &a, &b, NULL, &out, scratch, sizeof scratch};
    CHECK(ir_abi_version() == IR_ABI_VERSION);
    CHECK(ir_tensor_struct_size() == sizeof(ir_tensor));
    CHECK(ir_call_struct_size() == sizeof(ir_call));
    CHECK(ir_query(&call) == IR_OK);
    CHECK(ir_execute(&call) == IR_NUMERIC_OVERFLOW);
    CHECK(out_data[0] == -99 && out_data[1] == -99);
    b_data[1] = -1;
    CHECK(ir_execute(&call) == IR_OK);
    CHECK(out_data[0] == 3 && out_data[1] == INT32_MAX - 1);
    call.output = &a;
    CHECK(ir_query(&call) == IR_INVALID_ARGUMENT);
    call.output = &out; call.workspace_bytes = 0;
    CHECK(ir_execute(&call) == IR_RESOURCE_LIMIT);
    call.workspace_bytes = sizeof scratch; a.byte_length = 1;
    CHECK(ir_execute(&call) == IR_INVALID_ARGUMENT);
    a.byte_length = sizeof a_data; a.rank = 0;
    CHECK(ir_execute(&call) == IR_INVALID_SHAPE);
    a.rank = 1; a.layout = 99;
    CHECK(ir_execute(&call) == IR_UNSUPPORTED);
    a.layout = IR_ROW_MAJOR; a.dtype = 99;
    CHECK(ir_execute(&call) == IR_UNSUPPORTED);
    a.dtype = IR_INT32; a.data = ((unsigned char *)a_data) + 1;
    CHECK(ir_execute(&call) == IR_INVALID_ARGUMENT);
    a.data = a_data;
    CHECK(ir_execute(NULL) == IR_INVALID_ARGUMENT);
    call.op = 999;
    CHECK(ir_execute(&call) == IR_UNSUPPORTED);

    {
        int32_t w[] = {INT32_MAX, INT32_MAX, INT32_MAX,
                       -INT32_MAX, -INT32_MAX, -INT32_MAX};
        int32_t x[] = {INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX};
        int32_t y = -1, work;
        ir_tensor wt = vector(w, IR_INT32, 6), xt = vector(x, IR_INT32, 6);
        ir_tensor yt = vector(&y, IR_INT32, 1);
        ir_call dot = {IR_LINEAR, &wt, &xt, NULL, &yt, &work, sizeof work};
        wt.rank = 2; wt.shape[0] = wt.storage_shape[0] = 1;
        wt.shape[1] = wt.storage_shape[1] = 6;
        CHECK(ir_execute(&dot) == IR_OK && y == 0);
        w[0] = INT32_MIN; x[0] = 1;
        wt.shape[1] = wt.storage_shape[1] = 1;
        xt.shape[0] = xt.storage_shape[0] = 1;
        CHECK(ir_execute(&dot) == IR_OK && y == INT32_MIN);
    }
    {
        float av[] = {FLT_MAX}, bv[] = {0x1p100f}, result = -99, work;
        ir_tensor at = vector(av, IR_FLOAT32, 1), bt = vector(bv, IR_FLOAT32, 1);
        ir_tensor rt = vector(&result, IR_FLOAT32, 1);
        ir_call add = {IR_ADD, &at, &bt, NULL, &rt, &work, sizeof work};
        CHECK(ir_execute(&add) == IR_OK && result == FLT_MAX);
        bv[0] = 0x1p104f; result = -99;
        CHECK(ir_execute(&add) == IR_NUMERIC_OVERFLOW && result == -99);
        av[0] = NAN;
        CHECK(ir_execute(&add) == IR_NONFINITE);
        av[0] = 1; bv[0] = 2;
        CHECK(fesetround(FE_DOWNWARD) == 0);
        CHECK(ir_execute(&add) == IR_UNSUPPORTED);
        CHECK(fesetround(FE_TONEAREST) == 0);
    }
    {
        int32_t source[] = {-1, 2, 0, 0, 3, -4, 0, 0};
        int32_t result[] = {-99, -99, 77, 77, -99, -99, 77, 77};
        int32_t work[4];
        ir_tensor st = vector(source, IR_INT32, 8), rt = vector(result, IR_INT32, 8);
        ir_call relu = {IR_RELU, &st, NULL, NULL, &rt, work, sizeof work};
        st.rank = rt.rank = 2;
        st.shape[0] = rt.shape[0] = st.storage_shape[0] = rt.storage_shape[0] = 2;
        st.shape[1] = rt.shape[1] = 2;
        st.storage_shape[1] = rt.storage_shape[1] = 4;
        CHECK(ir_execute(&relu) == IR_OK);
        CHECK(result[0] == 0 && result[1] == 2 && result[4] == 3 && result[5] == 0);
        CHECK(result[2] == 77 && result[7] == 77);
        source[2] = 1;
        CHECK(ir_execute(&relu) == IR_INVALID_ARGUMENT);
    }
    {
        int32_t source = 7, result = -99, work = 13;
        ir_tensor st = vector(&source, IR_INT32, 1), rt = vector(&result, IR_INT32, 1);
        ir_call relu = {IR_RELU, &st, NULL, NULL, &rt, &work, sizeof work};
        CHECK(ir_execute_chain(&relu, 1, (uint32_t *)&source) == IR_INVALID_ARGUMENT);
        CHECK(source == 7 && result == -99);
        relu.op = 999;
        CHECK(ir_execute_chain(&relu, 1, (uint32_t *)&result) == IR_INVALID_ARGUMENT);
        CHECK(result == -99);
        relu.op = IR_RELU;
        CHECK(ir_execute_chain(&relu, 1, (uint32_t *)&work) == IR_INVALID_ARGUMENT && work == 13);
        CHECK(ir_execute_chain(&relu, 1, &relu.op) == IR_INVALID_ARGUMENT && relu.op == IR_RELU);
        CHECK(ir_execute_chain(&relu, 1, &st.rank) == IR_INVALID_ARGUMENT && st.rank == 1);
    }
    {
        uint32_t completed = 99;
        CHECK(ir_execute_chain(NULL, 0, &completed) == IR_INVALID_ARGUMENT);
        CHECK(completed == 0);
        CHECK(ir_execute_chain(&call, 1, NULL) == IR_INVALID_ARGUMENT);
    }
    {
        int32_t source = 7, result = -99, work;
        ir_tensor st = vector(&source, IR_INT32, 1), rt = vector(&result, IR_INT32, 1);
        ir_call relu = {IR_RELU, &st, NULL, NULL, &rt, &work, sizeof work};
        ir_node_profile profile;
        uint32_t completed = 99;
        CHECK(ir_execute_chain_profiled(&relu, 1, &completed, &profile, 0) == IR_RESOURCE_LIMIT);
        CHECK(completed == 99 && result == -99);
        CHECK(ir_execute_chain_profiled(&relu, 1, &completed, (ir_node_profile *)&source, 1) == IR_INVALID_ARGUMENT);
        CHECK(source == 7 && completed == 99);
        CHECK(ir_execute_chain_profiled(&relu, 1, &completed, &profile, 1) == IR_OK);
        CHECK(result == 7 && completed == 1 && profile.executed == 1 && profile.status == IR_OK);
        CHECK(ir_profile_struct_size() == sizeof profile && ir_clock_ticks_per_second() > 0);
    }
    puts("C_CORE_TESTS_PASS");
    return 0;
}
