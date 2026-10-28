#ifndef PNG_BENCH_PROTOCOL_H
#define PNG_BENCH_PROTOCOL_H
#include <stdint.h>
#define PB_FRAME_ADDRESS 0x34000000U
#define PB_FRAME_BYTES 3055360U
#define PB_WIDTH 1120U
#define PB_HEIGHT 1364U
#define PB_LOAD_ADDRESS 0x34320000U
#define PB_STACK_FLOOR 0x343A0000U
#define PB_STACK_TOP 0x343B0000U
#define PB_REPORT_ADDRESS 0x343E0000U
#define PB_REQUEST_ADDRESS 0x343E0800U
#define PB_CHUNKS_ADDRESS 0x343E1000U
#define PB_CHUNK_BYTES 32768U
#define PB_MAX_CHUNKS 100U
#define PB_MAX_OUTPUT 3200000U
#define PB_MODE_MAX 3U
#define PB_MAGIC 0x504E4231U /* PNB1: independent compute proof, not SAVE */
#define PB_READY 0x52454144U
#define PB_DONE 0x444F4E45U
#define PB_CANARY 0x504E4753U
#define PB_CPU_HZ 400000000U
#define PB_MAX_CYCLES 4000000000ULL /* cancellation at the next callback */
enum { PB_STATE_ACTIVE=1, PB_STATE_OK=2, PB_STATE_FAILED=3 };
enum { PB_PREPARE=1, PB_ENCODE=2 };
enum { PB_BAD_REQUEST=1, PB_BAD_CONTEXT=2, PB_BAD_CLOCK=3, PB_BAD_STORAGE_CLOCK=4,
       PB_BAD_DWT=5, PB_BAD_INPUT=6, PB_BAD_CANARY=7, PB_ENCODER_FAILED=8,
       PB_BAD_OUTPUT=9, PB_TIMEOUT=10, PB_BAD_FINAL_CONTEXT=11, PB_BAD_STATS=12 };
typedef struct {
    uint32_t magic, schema, operation, nonce, mode, input_fnv, output_fnv, output_bytes;
    uint32_t reserved[8];
} pb_request;
typedef struct {
    uint32_t bytes, fnv;
    uint64_t elapsed_cycles, sink_cycles, cpu_cycles;
} pb_chunk;
typedef struct {
    uint32_t magic, schema, words, state, operation, nonce, result, stage;
    uint32_t cpu_hz, frame_address, frame_bytes, width, height, mode;
    uint32_t initial_ccr, initial_control, initial_mpu, initial_fpccr;
    uint32_t final_ccr, final_control, final_ipsr, final_primask, final_faultmask, final_fpccr;
    uint32_t cfgr1, cfgr2, ahb5enr, ahb5rstr, xspi_sr, dwt_ctrl, dwt_delta;
    uint32_t input_fnv_before, input_fnv_after, output_fnv, output_bytes;
    uint32_t rows, idat_chunks, callback_calls, chunk_count, encoder_result;
    uint32_t stack_canary, frame_canary_mask, cache_owned, timed_out;
    uint64_t input_check_cycles, encode_cycles, sink_cycles, cpu_cycles;
    uint64_t cleanup_cycles, final_check_cycles, complete_cycles;
    uint64_t png_total, png_conversion, png_deflate, png_framing, png_callback, png_other;
    uint64_t sink_body_cycles;
    uint32_t png_clock_calls, png_clock_error, reserved[53], terminal;
} pb_report;
_Static_assert(sizeof(pb_request)==64,"Request layout");
_Static_assert(sizeof(pb_chunk)==32,"Chunk layout");
_Static_assert(sizeof(pb_report)==512,"Report layout");
#endif
