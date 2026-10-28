/* Offline actual-C producer/consumer boundary tests. No target addresses used. */
#include "producer.h"
#include <assert.h>
#include <stdio.h>

static volatile raw_producer_t p;
static uint32_t snapshots, expected_prefix;
static void snapshot(uint32_t index,uint32_t offset,uint32_t bytes)
{
    assert(index==snapshots && bytes==512U);
    assert(offset+512U==expected_prefix);
    assert(p.available_bytes<expected_prefix); /* must copy before publication */
    snapshots++;
}
static void init(void) { raw_producer_init(&p,1);snapshots=0; }
static void line(uint32_t n)
{
    uint32_t groups=n<21U?n:21U;
    expected_prefix=(groups-1U)*89600U;
    raw_producer_line(&p,n*1000U,snapshot);
}
int main(void)
{
    assert(sizeof(p)==416U);init();
    assert(raw_producer_next(&p,0,1024)==0);
    line(1);assert(p.line_events==1 && p.available_bytes==0 && snapshots==0);
    line(2);assert(p.available_bytes==89600 && snapshots==1);
    assert(raw_producer_next(&p,0,1024)==175);
    assert(raw_producer_next(&p,0,64)==64);
    assert(raw_producer_next(&p,64,64)==64);
    assert(raw_producer_next(&p,128,64)==47);
    assert(raw_producer_next(&p,175,1024)==0); /* faster consumer waits */
    for(uint32_t n=3;n<=22;n++) line(n);
    assert(p.line_events==22 && snapshots==20 && p.available_bytes==1792000U);
    assert(p.max_prefinal_bytes==1792000U && raw_producer_next(&p,3500,1024)==0);
    raw_producer_frame(&p,23000);
    raw_producer_line(&p,23001,snapshot); /* FRAME-before-LINE from same HAL IRQ */
    assert(p.ignored_after_frame==1 && p.line_events==22 && !p.error);
    assert(p.available_bytes==1792000U); /* FRAME alone does not publish tail */
    assert(raw_producer_complete(&p,1909600,1,0,0,24000)==0);
    assert(p.validated && p.available_bytes==1909600U);
    assert(raw_producer_next(&p,3500,1024)==229); /* 3729 whole sectors only */
    assert(raw_producer_next(&p,3729,1024)==0); /* last352 requires padded finish */
    assert(raw_producer_next(&p,3730,1024)==0);
    /* IRQ coalescence underpublishes safely, final validation still releases. */
    init();line(1);line(2);line(3);
    raw_producer_frame(&p,50000);
    assert(p.available_bytes==179200);
    assert(raw_producer_complete(&p,1909600,1,0,0,51000)==0);
    assert(raw_producer_next(&p,0,1024)==1024);
    /* Delayed producer: repeated consumer polling cannot invent bytes. */
    init();for(uint32_t i=0;i<1000;i++)assert(raw_producer_next(&p,0,1024)==0);
    line(1);for(uint32_t i=0;i<1000;i++)assert(raw_producer_next(&p,0,1024)==0);
    line(2);assert(raw_producer_next(&p,175,1024)==0);
    /* Runt frame, second frame, guard/camera error: no commit authorization. */
    raw_producer_frame(&p,4000);
    assert(raw_producer_complete(&p,1909599,1,0,0,5000)!=0);
    assert(!p.validated && raw_producer_available(&p)==0 && raw_producer_next(&p,0,64)==0);
    init();raw_producer_frame(&p,1);raw_producer_frame(&p,2);
    assert(raw_producer_complete(&p,1909600,2,0,0,3)!=0);
    init();raw_producer_frame(&p,1);
    assert(raw_producer_complete(&p,1909600,1,1,0,3)!=0);
    init();raw_producer_frame(&p,1);
    assert(raw_producer_complete(&p,1909600,1,0,1,3)!=0);
    init();line(1);line(2);raw_producer_fault(&p,4);
    assert(raw_producer_available(&p)==0);raw_producer_frame(&p,1);
    assert(raw_producer_complete(&p,1909600,1,0,0,3)!=0);
    init();for(uint32_t n=1;n<=22;n++)line(n);
    raw_producer_line(&p,23000,snapshot);assert(p.error && raw_producer_available(&p)==0);
    /* Disabled mode waits for validated FRAME and never makes snapshots. */
    raw_producer_init(&p,0);raw_producer_line(&p,1,snapshot);
    assert(!p.available_bytes && !p.line_events);
    raw_producer_frame(&p,2);assert(raw_producer_complete(&p,1909600,1,0,0,3)==0);
    puts("RAW producer: all boundary assertions passed");return 0;
}
