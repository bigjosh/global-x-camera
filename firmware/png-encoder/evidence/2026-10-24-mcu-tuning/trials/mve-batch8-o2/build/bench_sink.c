#include "bench_sink.h"

void pb_sink_init(pb_sink *s, uint64_t (*now)(void *), void *user,
                  volatile pb_chunk *chunks, uint64_t begin, uint64_t deadline)
{
    *s=(pb_sink){.now=now,.clock_user=user,.chunks=chunks,.begin=begin,
                 .deadline=deadline,.fnv=2166136261U};
}

static int checkpoint(pb_sink *s,uint64_t end,uint64_t sink_cycles)
{
    if(s->chunk_count>=PB_MAX_CHUNKS || end<s->begin || end-s->begin<sink_cycles) {
        s->error=PB_BAD_STATS; return 0;
    }
    volatile pb_chunk *c=s->chunks+s->chunk_count++;
    c->bytes=s->bytes; c->fnv=s->fnv;
    c->elapsed_cycles=end-s->begin; c->sink_cycles=sink_cycles;
    c->cpu_cycles=c->elapsed_cycles-sink_cycles;
    return 1;
}

int pb_sink_write(void *user,const uint8_t *data,size_t n)
{
    pb_sink *s=user;
    uint64_t start=s->now(s->clock_user);
    ++s->calls;
    if(start<s->begin || start-s->begin>s->deadline) { s->error=PB_TIMEOUT; return 0; }
    if(n>PB_MAX_OUTPUT-s->bytes || (!data && n)) { s->error=PB_BAD_OUTPUT; return 0; }
    while(n) {
        size_t part=PB_CHUNK_BYTES-(s->bytes%PB_CHUNK_BYTES);
        if(part>n) part=n;
        for(size_t i=0;i<part;i++) s->fnv=(s->fnv^data[i])*16777619U;
        s->bytes+=(uint32_t)part; data+=part; n-=part;
        if(s->bytes%PB_CHUNK_BYTES==0) {
            uint64_t now=s->now(s->clock_user);
            if(now<start || !checkpoint(s,now,s->sink_cycles+now-start)) return 0;
        }
    }
    uint64_t end=s->now(s->clock_user);
    if(end<start) { s->error=PB_BAD_STATS; return 0; }
    s->sink_cycles+=end-start;
    if(end-s->begin>s->deadline) { s->error=PB_TIMEOUT; return 0; }
    return 1;
}

int pb_sink_finish(pb_sink *s,uint64_t end)
{
    if(s->error) return 0;
    if(s->bytes%PB_CHUNK_BYTES || !s->chunk_count) return checkpoint(s,end,s->sink_cycles);
    return 1;
}
