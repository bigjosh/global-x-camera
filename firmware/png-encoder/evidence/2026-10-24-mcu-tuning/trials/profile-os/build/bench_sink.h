#ifndef PNG_BENCH_SINK_H
#define PNG_BENCH_SINK_H
#include <stddef.h>
#include <stdint.h>
#include "bench_protocol.h"
typedef struct {
    uint64_t (*now)(void *user);
    void *clock_user;
    volatile pb_chunk *chunks;
    uint64_t begin, deadline, sink_cycles;
    uint32_t bytes, fnv, calls, chunk_count, error;
} pb_sink;
void pb_sink_init(pb_sink *sink, uint64_t (*now)(void *), void *clock_user,
                  volatile pb_chunk *chunks, uint64_t begin, uint64_t deadline);
int pb_sink_write(void *user, const uint8_t *data, size_t bytes);
int pb_sink_finish(pb_sink *sink, uint64_t end);
#endif
