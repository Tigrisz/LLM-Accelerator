#include "ir_core.h"
#include <fenv.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <string.h>
#include <time.h>

#ifdef __FAST_MATH__
#error "This reference backend must not be compiled with fast-math"
#endif
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24 &&
               FLT_MAX_EXP == 128, "IEEE binary32 is required");
_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
               "IEEE binary64 is required");
_Static_assert(sizeof(int32_t) == 4 && CHAR_BIT == 8, "32-bit integers and bytes required");

uint32_t ir_abi_version(void) { return IR_ABI_VERSION; }
size_t ir_tensor_struct_size(void) { return sizeof(ir_tensor); }
size_t ir_call_struct_size(void) { return sizeof(ir_call); }

const char *ir_status_name(ir_status s) {
    switch (s) {
        case IR_OK: return "OK";
        case IR_INVALID_ARGUMENT: return "INVALID_ARGUMENT";
        case IR_INVALID_SHAPE: return "INVALID_SHAPE";
        case IR_UNSUPPORTED: return "UNSUPPORTED";
        case IR_RESOURCE_LIMIT: return "RESOURCE_LIMIT";
        case IR_NONFINITE: return "NONFINITE";
        case IR_NUMERIC_OVERFLOW: return "NUMERIC_OVERFLOW";
        default: return "UNKNOWN_STATUS";
    }
}

static uint64_t elements(const ir_tensor *t, int storage) {
    uint64_t n = 1;
    uint32_t i;
    for (i = 0; i < t->rank; ++i) n *= storage ? t->storage_shape[i] : t->shape[i];
    return n;
}

static int valid_span(const void *p, uint64_t bytes) {
    uintptr_t start = (uintptr_t)p;
    return p != NULL && bytes <= SIZE_MAX && bytes <= UINTPTR_MAX - start;
}

static int overlap(const void *a, uint64_t an, const void *b, uint64_t bn) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return x <= y ? (uint64_t)(y - x) < an : (uint64_t)(x - y) < bn;
}

static ir_status tensor_check(const ir_tensor *t) {
    uint64_t logical = 1, physical = 1;
    uint32_t d;
    if (t == NULL || t->data == NULL) return IR_INVALID_ARGUMENT;
    if (t->dtype != IR_FLOAT32 && t->dtype != IR_INT32) return IR_UNSUPPORTED;
    if (t->layout != IR_ROW_MAJOR) return IR_UNSUPPORTED;
    if (t->rank < 1 || t->rank > IR_MAX_RANK) return IR_INVALID_SHAPE;
    for (d = 0; d < t->rank; ++d) {
        uint64_t n = t->shape[d], p = t->storage_shape[d];
        if (n == 0 || p == 0 || n > p) return IR_INVALID_SHAPE;
        if (p > IR_MAX_ELEMENTS / physical || n > IR_MAX_ELEMENTS / logical)
            return IR_RESOURCE_LIMIT;
        physical *= p; logical *= n;
    }
    if (physical > SIZE_MAX / 4 || t->byte_length < physical * 4 ||
        !valid_span(t->data, physical * 4) ||
        (uintptr_t)t->data % _Alignof(float) != 0 ||
        (uintptr_t)t->data % _Alignof(int32_t) != 0) return IR_INVALID_ARGUMENT;
    return IR_OK;
}

static int same_shape(const ir_tensor *a, const ir_tensor *b) {
    uint32_t d;
    if (a->rank != b->rank) return 0;
    for (d = 0; d < a->rank; ++d) if (a->shape[d] != b->shape[d]) return 0;
    return 1;
}

ir_status ir_query(const ir_call *c) {
    const ir_tensor *inputs[3];
    uint32_t n = 0, i;
    uint64_t needed, output_bytes;
    ir_status s;
    if (c == NULL) return IR_INVALID_ARGUMENT;
    if (c->op != IR_LINEAR && c->op != IR_ADD && c->op != IR_RELU) return IR_UNSUPPORTED;
    inputs[n++] = c->a;
    if (c->op == IR_LINEAR || c->op == IR_ADD) inputs[n++] = c->b;
    else if (c->b != NULL) return IR_INVALID_ARGUMENT;
    if (c->bias != NULL) {
        if (c->op != IR_LINEAR) return IR_INVALID_ARGUMENT;
        inputs[n++] = c->bias;
    }
    for (i = 0; i < n; ++i) {
        s = tensor_check(inputs[i]); if (s != IR_OK) return s;
        if (inputs[i]->dtype != c->a->dtype) return IR_INVALID_ARGUMENT;
    }
    s = tensor_check(c->output); if (s != IR_OK) return s;
    if (c->output->dtype != c->a->dtype) return IR_INVALID_ARGUMENT;
    if (c->op == IR_LINEAR) {
        if (c->a->rank != 2 || c->b->rank != 1 ||
            c->a->shape[1] != c->b->shape[0] || c->output->rank != 1 ||
            c->output->shape[0] != c->a->shape[0]) return IR_INVALID_SHAPE;
        if (c->bias != NULL && (c->bias->rank != 1 ||
                               c->bias->shape[0] != c->a->shape[0])) return IR_INVALID_SHAPE;
    } else {
        if (!same_shape(c->a, c->output)) return IR_INVALID_SHAPE;
        if (c->op == IR_ADD && !same_shape(c->a, c->b)) return IR_INVALID_SHAPE;
    }
    if (c->a->dtype == IR_FLOAT32 && fegetround() != FE_TONEAREST) return IR_UNSUPPORTED;
    needed = elements(c->output, 0) * 4;
    output_bytes = elements(c->output, 1) * 4;
    if (c->workspace_bytes < needed) return IR_RESOURCE_LIMIT;
    if (!valid_span(c->workspace, needed) ||
        (uintptr_t)c->workspace % _Alignof(float) != 0 ||
        (uintptr_t)c->workspace % _Alignof(int32_t) != 0) return IR_INVALID_ARGUMENT;
    if (overlap(c->workspace, needed, c->output->data, output_bytes))
        return IR_INVALID_ARGUMENT;
    for (i = 0; i < n; ++i) {
        uint64_t bytes = elements(inputs[i], 1) * 4;
        if (overlap(inputs[i]->data, bytes, c->output->data, output_bytes) ||
            overlap(inputs[i]->data, bytes, c->workspace, needed)) return IR_INVALID_ARGUMENT;
    }
    return IR_OK;
}

static uint64_t storage_offset(const ir_tensor *t, uint64_t logical) {
    uint64_t offset = 0, stride = 1;
    uint32_t d = t->rank;
    while (d > 0) {
        --d;
        offset += (logical % t->shape[d]) * stride;
        logical /= t->shape[d];
        stride *= t->storage_shape[d];
    }
    return offset;
}

static int32_t read_i(const ir_tensor *t, uint64_t logical) {
    int32_t value;
    memcpy(&value, (const unsigned char *)t->data + storage_offset(t, logical) * 4, 4);
    return value;
}

static double read_f(const ir_tensor *t, uint64_t logical) {
    float value;
    memcpy(&value, (const unsigned char *)t->data + storage_offset(t, logical) * 4, 4);
    return (double)value;
}

static ir_status values_check(const ir_tensor *t) {
    uint64_t i, count = elements(t, 1);
    for (i = 0; i < count; ++i) {
        uint64_t rest = i;
        uint32_t d = t->rank;
        int padding = 0;
        while (d > 0) {
            --d;
            if (rest % t->storage_shape[d] >= t->shape[d]) padding = 1;
            rest /= t->storage_shape[d];
        }
        if (t->dtype == IR_FLOAT32) {
            float value;
            memcpy(&value, (const unsigned char *)t->data + i * 4, 4);
            if (!isfinite(value)) return IR_NONFINITE;
            if (padding && value != 0) return IR_INVALID_ARGUMENT;
        } else if (padding) {
            int32_t value;
            memcpy(&value, (const unsigned char *)t->data + i * 4, 4);
            if (value != 0) return IR_INVALID_ARGUMENT;
        }
    }
    return IR_OK;
}

/* At most 2^20 products of magnitude <=2^62: <2^83, well within two limbs.
 * Sign-magnitude addition avoids signed overflow and supports cancellation. */
typedef struct { uint64_t hi, lo; int negative; } wide_sum;

static void wide_add(wide_sum *s, int64_t value) {
    int negative = value < 0;
    uint64_t magnitude = negative ? (uint64_t)(-(value + 1)) + 1 : (uint64_t)value;
    if (s->negative == negative) {
        uint64_t old = s->lo;
        s->lo += magnitude;
        s->hi += s->lo < old;
    } else if (s->hi != 0 || s->lo >= magnitude) {
        uint64_t old = s->lo;
        s->lo -= magnitude;
        s->hi -= old < magnitude;
    } else {
        s->lo = magnitude - s->lo;
        s->negative = negative;
    }
    if (s->lo == 0 && s->hi == 0) s->negative = 0;
}

static ir_status integer_result(const ir_call *c, uint64_t index, int32_t *out) {
    wide_sum sum = {0, 0, 0};
    uint64_t k;
    if (c->op == IR_LINEAR) {
        for (k = 0; k < c->a->shape[1]; ++k)
            wide_add(&sum, (int64_t)read_i(c->a, index * c->a->shape[1] + k) *
                          (int64_t)read_i(c->b, k));
        if (c->bias != NULL) wide_add(&sum, read_i(c->bias, index));
    } else if (c->op == IR_ADD) {
        wide_add(&sum, read_i(c->a, index)); wide_add(&sum, read_i(c->b, index));
    } else {
        int32_t value = read_i(c->a, index);
        *out = value > 0 ? value : 0;
        return IR_OK;
    }
    if (sum.hi != 0 || sum.lo > (sum.negative ? UINT64_C(2147483648) : UINT64_C(2147483647)))
        return IR_NUMERIC_OVERFLOW;
    if (sum.negative && sum.lo == UINT64_C(2147483648)) *out = INT32_MIN;
    else *out = sum.negative ? -(int32_t)sum.lo : (int32_t)sum.lo;
    return IR_OK;
}

/* Nonoverlapping double expansion, with a bounded, checked partial array.
 * float32 products are exactly representable as double. No reassociation/FMA. */
typedef struct { double partials[64]; uint32_t count; } expansion;

static ir_status expansion_add(expansion *s, double x) {
    uint32_t i, used = 0;
    for (i = 0; i < s->count; ++i) {
        double y = s->partials[i], hi, lo;
        if (fabs(x) < fabs(y)) { double swap = x; x = y; y = swap; }
        hi = x + y;
        lo = y - (hi - x);
        if (lo != 0) s->partials[used++] = lo;
        x = hi;
    }
    if (x != 0) {
        if (used == 64) return IR_RESOURCE_LIMIT;
        s->partials[used++] = x;
    }
    s->count = used;
    return IR_OK;
}

static double expansion_finish(const expansion *s) {
    uint32_t n = s->count;
    double hi = 0, lo = 0;
    if (n == 0) return 0;
    hi = s->partials[--n];
    while (n > 0) {
        double x = hi, y = s->partials[--n], rounded;
        hi = x + y;
        rounded = hi - x;
        lo = y - rounded;
        if (lo != 0) break;
    }
    if (n > 0 && ((lo < 0 && s->partials[n-1] < 0) ||
                  (lo > 0 && s->partials[n-1] > 0))) {
        double twice = lo * 2, next = hi + twice;
        if (next - hi == twice) hi = next;
    }
    return hi;
}

static ir_status float_result(const ir_call *c, uint64_t index, float *out) {
    expansion sum = {{0}, 0};
    uint64_t k;
    double value;
    ir_status status;
    if (c->op == IR_LINEAR) {
        for (k = 0; k < c->a->shape[1]; ++k) {
            status = expansion_add(&sum, read_f(c->a, index*c->a->shape[1]+k) * read_f(c->b, k));
            if (status != IR_OK) return status;
        }
        if (c->bias != NULL) {
            status = expansion_add(&sum, read_f(c->bias, index));
            if (status != IR_OK) return status;
        }
        value = expansion_finish(&sum);
    } else if (c->op == IR_ADD) {
        value = read_f(c->a, index) + read_f(c->b, index);
    } else {
        double input = read_f(c->a, index);
        value = input > 0 ? input : 0;
    }
    /* IEEE round-to-nearest overflow midpoint, not a pre-round FLT_MAX bound. */
    if (!isfinite(value) || fabs(value) >= (double)FLT_MAX + 0x1p103)
        return IR_NUMERIC_OVERFLOW;
    *out = (float)value;
    return isfinite(*out) ? IR_OK : IR_NUMERIC_OVERFLOW;
}

ir_status ir_execute(const ir_call *c) {
    uint64_t i, count;
    ir_status status = ir_query(c);
    if (status != IR_OK) return status;
    status = values_check(c->a); if (status != IR_OK) return status;
    if (c->b != NULL) { status = values_check(c->b); if (status != IR_OK) return status; }
    if (c->bias != NULL) { status = values_check(c->bias); if (status != IR_OK) return status; }
    count = elements(c->output, 0);
    for (i = 0; i < count; ++i) {
        if (c->a->dtype == IR_INT32) {
            int32_t value;
            status = integer_result(c, i, &value);
            if (status != IR_OK) return status;
            memcpy((unsigned char *)c->workspace + i*4, &value, 4);
        } else {
            float value;
            status = float_result(c, i, &value);
            if (status != IR_OK) return status;
            memcpy((unsigned char *)c->workspace + i*4, &value, 4);
        }
    }
    for (i = 0; i < count; ++i)
        memcpy((unsigned char *)c->output->data + storage_offset(c->output, i)*4,
               (const unsigned char *)c->workspace + i*4, 4);
    return IR_OK;
}

static ir_status chain_run(const ir_call *calls, uint32_t count, uint32_t *completed,
                           ir_node_profile *profiles) {
    uint32_t i, j, k;
    ir_status status;
    if (!valid_span(completed, sizeof *completed) ||
        (uintptr_t)completed % _Alignof(uint32_t) != 0) return IR_INVALID_ARGUMENT;
    if (calls != NULL && count > 0 && count <= IR_MAX_CHAIN) {
        uint64_t call_bytes = (uint64_t)count * sizeof *calls;
        if (!valid_span(calls, call_bytes) ||
            overlap(completed, sizeof *completed, calls, call_bytes)) return IR_INVALID_ARGUMENT;
        /* Validate the counter before its first write, even for rejected nodes. */
        for (i = 0; i < count; ++i) {
            const ir_tensor *tensors[4] = {calls[i].a, calls[i].b, calls[i].bias, calls[i].output};
            for (k = 0; k < 4; ++k) {
                const ir_tensor *t = tensors[k];
                if (t == NULL) continue;
                if (!valid_span(t, sizeof *t) ||
                    overlap(completed, sizeof *completed, t, sizeof *t)) return IR_INVALID_ARGUMENT;
                if (t->data != NULL && t->byte_length > 0 &&
                    (!valid_span(t->data, t->byte_length) ||
                     overlap(completed, sizeof *completed, t->data, t->byte_length)))
                    return IR_INVALID_ARGUMENT;
            }
            if (calls[i].workspace != NULL && calls[i].workspace_bytes > 0 &&
                (!valid_span(calls[i].workspace, calls[i].workspace_bytes) ||
                 overlap(completed, sizeof *completed, calls[i].workspace, calls[i].workspace_bytes)))
                return IR_INVALID_ARGUMENT;
        }
    }
    *completed = 0;
    if (calls == NULL || count == 0 || count > IR_MAX_CHAIN) return IR_INVALID_ARGUMENT;
    for (i = 0; i < count; ++i) {
        status = ir_query(&calls[i]);
        if (status != IR_OK) return status;
    }
    /* A scratch write must not corrupt any other node's persistent tensor. */
    for (i = 0; i < count; ++i) {
        uint64_t needed = elements(calls[i].output, 0)*4;
        for (j = 0; j < count; ++j) {
            const ir_tensor *tensors[4] = {calls[j].a, calls[j].b, calls[j].bias, calls[j].output};
            for (k = 0; k < 4; ++k)
                if (tensors[k] != NULL &&
                    overlap(calls[i].workspace, needed, tensors[k]->data, elements(tensors[k], 1)*4))
                    return IR_INVALID_ARGUMENT;
        }
    }
    if (profiles != NULL) memset(profiles, 0, (size_t)count * sizeof *profiles);
    for (i = 0; i < count; ++i) {
        clock_t begin = (clock_t)-1, end;
        if (profiles != NULL) begin = clock();
        status = ir_execute(&calls[i]);
        if (profiles != NULL) {
            end = clock();
            profiles[i].executed = 1;
            profiles[i].status = (uint32_t)status;
            if (begin != (clock_t)-1 && end != (clock_t)-1 &&
                (long double)begin >= 0 && (long double)end >= 0 && end >= begin) {
                profiles[i].start_ticks = (uint64_t)begin;
                profiles[i].end_ticks = (uint64_t)end;
                profiles[i].timing_valid = 1;
            }
        }
        if (status != IR_OK) return status;
        *completed = i + 1;
    }
    return IR_OK;
}

ir_status ir_execute_chain(const ir_call *calls, uint32_t count, uint32_t *completed) {
    return chain_run(calls, count, completed, NULL);
}

size_t ir_profile_struct_size(void) { return sizeof(ir_node_profile); }
uint64_t ir_clock_ticks_per_second(void) { return (uint64_t)CLOCKS_PER_SEC; }

ir_status ir_execute_chain_profiled(const ir_call *calls, uint32_t count,
    uint32_t *completed, ir_node_profile *profiles, uint32_t capacity) {
    uint32_t i, k;
    uint64_t bytes = (uint64_t)count * sizeof *profiles;
    if (capacity < count) return IR_RESOURCE_LIMIT;
    if (calls == NULL || count == 0 || count > IR_MAX_CHAIN ||
        !valid_span(completed, sizeof *completed) ||
        !valid_span(profiles, bytes) ||
        (uintptr_t)profiles % _Alignof(ir_node_profile) != 0 ||
        !valid_span(calls, (uint64_t)count * sizeof *calls) ||
        overlap(profiles, bytes, completed, sizeof *completed) ||
        overlap(profiles, bytes, calls, (uint64_t)count * sizeof *calls)) return IR_INVALID_ARGUMENT;
    for (i = 0; i < count; ++i) {
        const ir_tensor *tensors[4] = {calls[i].a, calls[i].b, calls[i].bias, calls[i].output};
        for (k = 0; k < 4; ++k) {
            const ir_tensor *t = tensors[k];
            if (t == NULL) continue;
            if (!valid_span(t, sizeof *t) || overlap(profiles, bytes, t, sizeof *t)) return IR_INVALID_ARGUMENT;
            if (t->data != NULL && t->byte_length > 0 &&
                (!valid_span(t->data, t->byte_length) || overlap(profiles, bytes, t->data, t->byte_length)))
                return IR_INVALID_ARGUMENT;
        }
        if (calls[i].workspace != NULL && calls[i].workspace_bytes > 0 &&
            (!valid_span(calls[i].workspace, calls[i].workspace_bytes) ||
             overlap(profiles, bytes, calls[i].workspace, calls[i].workspace_bytes))) return IR_INVALID_ARGUMENT;
    }
    return chain_run(calls, count, completed, profiles);
}
