#define T5_TENSORS 2
#define T5_NODES 1
#define T5_ALIGNMENT 64
#define T5_ACT_BYTES 128
#define T5_WORK_BYTES 64
#define T5_WEIGHT_BYTES 0
#define T5_INPUT_COUNT 1
#define T5_OUTPUT_INDEX 0
#define T5_OUTPUT_BYTES 12
#define T5_OVERFLOW_PROBE 0
_Alignas(64) static const unsigned char t5_image[280]={73,82,83,52,66,73,78,49,1,0,0,0,4,3,2,1,2,0,0,0,1,0,0,0,64,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,0,0,0,0,0,0,0,64,0,0,0,0,0,0,0,90,149,187,17,0,0,0,0,1,0,0,0,1,0,0,0,3,0,0,0,1,0,0,0,64,0,0,0,0,0,0,0,12,0,0,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,12,0,0,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,0,0,0,1,0,0,0,255,255,255,255,255,255,255,255,0,0,0,0,0,0,0,0};
_Alignas(64) static const unsigned char t5_weights[1]={0};
_Alignas(4) static const unsigned char input_1[12]={0,0,224,192,0,0,0,0,0,0,64,64};
_Alignas(4) static const unsigned char zero_1[12]={0,0,0,0,0,0,0,0,0,0,0,0};
typedef struct {uint32_t index,size;const unsigned char *normal,*zero;} t5_input;
static const t5_input t5_inputs[T5_INPUT_COUNT]={{1,12,input_1,zero_1}};
