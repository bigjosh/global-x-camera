#include "producer.h"

volatile raw_producer_t raw_producer;

/* These order CPU publication/observation; they do not flush camera DMA. The
 * experimental line holdback and hardware qualification address DMA visibility.
 */
static void barrier(void)
{
#if defined(__arm__) || defined(__thumb__)
    __asm volatile("dmb 0xF":::"memory");
#else
    __asm volatile("":::"memory");
#endif
}

void raw_producer_init(volatile raw_producer_t *p,uint32_t enabled)
{
    volatile uint32_t *words=(volatile uint32_t *)p;
    for(uint32_t i=0;i<sizeof(*p)/sizeof(uint32_t);i++) words[i]=0;
    p->magic=RAW_PRODUCER_MAGIC;p->schema=1;p->enabled=enabled?1U:0U;
}

void raw_producer_fault(volatile raw_producer_t *p,uint32_t error)
{
    p->error|=error?error:RAW_PRODUCER_ERR_CAPTURE;barrier();
}

void raw_producer_line(volatile raw_producer_t *p,uint32_t cycle,
                       raw_producer_snapshot_t snapshot)
{
    if(!p->enabled || p->error) return;
    if(p->frame_seen) { p->ignored_after_frame++;return; }
    uint32_t event=p->line_events+1U;
    if(event>RAW_PRODUCER_MAX_LINE_EVENTS) {
        raw_producer_fault(p,RAW_PRODUCER_ERR_LINES);return;
    }
    p->line_events=event;p->last_line_cycle=cycle;
    if(event==1U) p->first_line_cycle=cycle;
    /* Event 22 can represent only the final20 lines, not another64. Cap before
     * subtracting the holdback so the final partial group never overpublishes.
     * Coalesced/missed IRQs can only underpublish; FRAME releases the remainder.
     */
    uint32_t groups=event<RAW_PRODUCER_FULL_GROUPS?event:RAW_PRODUCER_FULL_GROUPS;
    uint32_t bytes=(groups-1U)*RAW_PRODUCER_GROUP_BYTES;
    if(bytes>p->available_bytes) {
        if(snapshot) {
            uint32_t n=p->snapshot_count;
            if(n>=RAW_PRODUCER_SNAPSHOT_CAPACITY) {
                raw_producer_fault(p,RAW_PRODUCER_ERR_LINES);return;
            }
            uint32_t offset=bytes-RAW_PRODUCER_SNAPSHOT_BYTES;
            snapshot(n,offset,RAW_PRODUCER_SNAPSHOT_BYTES);
            p->snapshots[n][0]=offset;p->snapshots[n][1]=RAW_PRODUCER_SNAPSHOT_BYTES;
            p->snapshot_count=n+1U;
        }
        if(!p->available_bytes) p->first_prefix_cycle=cycle;
        p->max_prefinal_bytes=bytes;
        barrier();p->available_bytes=bytes;
    }
    p->events[event-1U][0]=cycle;p->events[event-1U][1]=p->available_bytes;
}

void raw_producer_frame(volatile raw_producer_t *p,uint32_t cycle)
{
    if(p->frame_seen) { raw_producer_fault(p,RAW_PRODUCER_ERR_FRAME);return; }
    p->frame_seen=1;p->frame_cycle=cycle;barrier();
}

uint32_t raw_producer_complete(volatile raw_producer_t *p,uint32_t bytes,
    uint32_t frames,uint32_t errors,uint32_t canary,uint32_t cycle)
{
    if(p->magic!=RAW_PRODUCER_MAGIC || p->schema!=1U) {
        raw_producer_fault(p,RAW_PRODUCER_ERR_ARGUMENT);return p->error;
    }
    if(!p->frame_seen || frames!=1U || bytes!=RAW_PRODUCER_BYTES)
        raw_producer_fault(p,RAW_PRODUCER_ERR_FRAME);
    if(errors || canary) raw_producer_fault(p,RAW_PRODUCER_ERR_CAPTURE);
    if(p->error) return p->error;
    p->validation_cycle=cycle;p->validated=1;
    barrier();p->available_bytes=RAW_PRODUCER_BYTES;return 0;
}

uint32_t raw_producer_available(const volatile raw_producer_t *p)
{
    if(p->error) return 0;
    uint32_t available=p->available_bytes;barrier();
    /* An IRQ can fault between the first check and this observation. A fault
     * immediately after return still leaves the slot PARTIAL at the final gate. */
    return p->error?0U:available;
}

uint32_t raw_producer_next(const volatile raw_producer_t *p,
                          uint32_t submitted,uint32_t maximum)
{
    if(!maximum || submitted>=3729U) return 0;
    uint32_t available=raw_producer_available(p)/512U;
    if(available>3729U) available=3729U;
    if(available<=submitted) return 0;
    uint32_t count=available-submitted;
    return count<maximum?count:maximum;
}
