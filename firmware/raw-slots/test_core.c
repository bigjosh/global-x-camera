/* Host-only executable: the actual C storage core against a deterministic SD
 * transport, including injected write/sync errors. No physical disks/devices. */
#include "raw_slots.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_SLOTS 3U
#define TEST_SECTORS (RAW_SLOTS_FIRST_LBA+TEST_SLOTS*RAW_SLOTS_STRIDE+13U)
static uint8_t disk[TEST_SECTORS*512U];
static uint32_t fail_write, fail_sync, writes, syncs, progresses, dma_writes;
static raw_slots_t fs;
static sd_card_t card;
static uint8_t frame[RAW_SLOTS_PAYLOAD_BYTES] __attribute__((aligned(32)));
static uint8_t padded[RAW_SLOTS_PADDED_BYTES] __attribute__((aligned(32)));
static uint32_t whole_count,whole_lba;


int sd_read_blocks(sd_card_t *c,uint32_t lba,void *buffer,uint32_t count)
{
    if(c->error || (uint64_t)lba+count>TEST_SECTORS) return 1;
    memcpy(buffer,disk+(size_t)lba*512,(size_t)count*512);return 0;
}
int sd_write_blocks(sd_card_t *c,uint32_t lba,const void *buffer,uint32_t count)
{
    writes++;
    if((fail_write && writes==fail_write) || c->error || (uint64_t)lba+count>TEST_SECTORS) {
        c->error=1;return 1;
    }
    memcpy(disk+(size_t)lba*512,buffer,(size_t)count*512);return 0;
}
int sd_sync(sd_card_t *c)
{
    syncs++;
    if(fail_sync && syncs==fail_sync) { c->error=1;c->media_idle=0;return 1; }
    c->media_idle=1;return 0;
}
void sd_progress(void) { progresses++; }
static int dma_write(sd_card_t *c,uint32_t lba,const void *b,uint32_t n)
{ dma_writes++;return sd_write_blocks(c,lba,b,n); }
static int whole_write(sd_card_t *c,uint32_t lba,const void *b,uint32_t n)
{ whole_count=n;whole_lba=lba;return dma_write(c,lba,b,n); }
static void fresh_card(void)
{
    memset(&card,0,sizeof(card));card.initialized=1;card.media_idle=1;card.sector_count=TEST_SECTORS;
    fail_write=fail_sync=writes=syncs=progresses=dma_writes=0;
}
static void reset_disk(void) { memset(disk,0xa5,sizeof(disk));fresh_card(); }
static uint32_t u32(const uint8_t *p)
{ return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void p32(uint8_t *p,uint32_t x)
{ for(uint32_t i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i)); }
static void seal(uint8_t *p)
{
    uint32_t c=~0U;
    for(uint32_t i=0;i<508;i++) { c^=p[i];for(uint32_t b=0;b<8;b++)c=(c>>1)^((0U-(c&1U))&0xedb88320U); }
    p32(p+508,~c);
}
static uint8_t *header(uint32_t slot) { return disk+(RAW_SLOTS_FIRST_LBA+slot*RAW_SLOTS_STRIDE)*512U; }
static void format(uint32_t limit)
{ assert(raw_slots_format(&fs,&card,0x12345678,0xabcdef12,limit)==0); }
static void begin(void)
{
    assert(raw_slots_find_free(&fs)==0);
    raw_slots_metadata_t m={0};m.capture_id=42;m.exposure_us=20000;
    m.analog_gain_milli=m.digital_gain_milli=1000;m.orientation=~0U;
    assert(raw_slots_begin(&fs,&m)==0);
}
static void save(void)
{
    begin();fs.write_payload=dma_write;
    assert(raw_slots_append(&fs,frame,1)==0);
    assert(raw_slots_append(&fs,frame+512,127)==0);
    assert(raw_slots_append(&fs,frame+128*512,RAW_SLOTS_WHOLE_SECTORS-128)==0);
    assert(raw_slots_finish(&fs,frame+RAW_SLOTS_WHOLE_SECTORS*512)==0);
    assert(!fs.active && fs.written_sectors==RAW_SLOTS_PAYLOAD_SECTORS);
}

int main(int argc,char **argv)
{
    /* Every sample cycles 0..1023, exercising both low bits independently. */
    for(uint32_t i=0;i<RAW_SLOTS_PAYLOAD_BYTES;i+=5) {
        uint32_t pixel=(i/5)*4;uint8_t low=0;
        for(uint32_t j=0;j<4;j++) { uint32_t v=(pixel+j)&1023;frame[i+j]=(uint8_t)(v>>2);low|=(v&3)<<(2*j); }
        frame[i+4]=low;
    }
    reset_disk();assert(raw_slots_open(&fs,&card)==RAW_SLOTS_ERR_VOLUME);
    assert(raw_slots_format(&fs,&card,0,0,0)==RAW_SLOTS_ERR_GENERATION);
    assert(raw_slots_format(&fs,&card,1,0,4)==RAW_SLOTS_ERR_CAPACITY);
    card.sector_count=RAW_SLOTS_FIRST_LBA+RAW_SLOTS_STRIDE-1;
    assert(raw_slots_format(&fs,&card,1,0,0)==RAW_SLOTS_ERR_CAPACITY);
    reset_disk();format(0);assert(fs.slot_count==3 && fs.formatted_slots==3 && progresses==3);
    assert(raw_slots_format(&fs,&card,0x12345678,0xabcdef12,0)==RAW_SLOTS_ERR_GENERATION);
    assert(raw_slots_open(&fs,&card)==0);assert(raw_slots_find_free(&fs)==0 && fs.selected_slot==0);

    /* Full stream: arbitrary chunk boundaries, no-copy callback, last-sector
       zeros, neighbors and unused capacity never changed. */
    save();assert(dma_writes==4);assert(u32(header(0)+12)==RAW_SLOTS_FULL);
    assert(memcmp(header(0)+512,frame,sizeof(frame))==0);
    for(uint32_t i=0;i<160;i++)assert(header(0)[512+sizeof(frame)+i]==0);
    assert(u32(header(1)+12)==RAW_SLOTS_FREE);
    assert(disk[(TEST_SECTORS-1)*512]==0xa5);
    assert(raw_slots_open(&fs,&card)==0);begin();assert(fs.selected_slot==1);
    assert(raw_slots_append(&fs,frame,7)==0);assert(u32(header(1)+12)==RAW_SLOTS_PARTIAL);
    assert(raw_slots_open(&fs,&card)==0);assert(raw_slots_find_free(&fs)==0 && fs.selected_slot==2 && fs.scan_headers==3);
    /* Publish host interoperability fixture with FULL/PARTIAL/FREE. */
    if(argc>1) { FILE *f=fopen(argv[1],"wb");assert(f);assert(fwrite(disk,1,sizeof(disk),f)==sizeof(disk));assert(fclose(f)==0); }

    begin();assert(fs.selected_slot==2);
    assert(raw_slots_open(&fs,&card)==0);assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_FULL);
    /* Invalid/blank/foreign generation is never mistaken for FREE. */
    reset_disk();format(0);memset(header(0),0xff,512);
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    reset_disk();format(0);header(0)[100]^=1;
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    reset_disk();format(0);header(0)[16]^=1;seal(header(0));
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    reset_disk();format(0);p32(header(0)+24,1);seal(header(0));
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    reset_disk();format(0);p32(header(0)+88,1);seal(header(0));
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    reset_disk();format(0);p32(header(0)+12,0);seal(header(0));
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_HEADER);
    /* Format interrupted after invalidation cannot reopen. Earlier stale
       payload is deliberately untouched, and new generation must differ. */
    reset_disk();fail_write=3;assert(raw_slots_format(&fs,&card,1,0,0)==RAW_SLOTS_ERR_IO);
    assert(fs.formatted_slots==1);fresh_card();assert(raw_slots_open(&fs,&card)==RAW_SLOTS_ERR_FORMATTING);
    assert(raw_slots_format(&fs,&card,1,0,0)==RAW_SLOTS_ERR_GENERATION);
    assert(raw_slots_format(&fs,&card,2,0,0)==0);
    reset_disk();fail_sync=2;assert(raw_slots_format(&fs,&card,1,0,0)==RAW_SLOTS_ERR_IO);
    assert(fs.formatted_slots==0);fresh_card();assert(raw_slots_open(&fs,&card)==RAW_SLOTS_ERR_FORMATTING);
    reset_disk();format(1);assert(fs.slot_count==1);save();
    assert(raw_slots_find_free(&fs)==RAW_SLOTS_ERR_FULL);
    /* Payload errors do not promote PARTIAL; wrong length fails closed. */
    reset_disk();format(0);begin();fail_write=writes+1;
    assert(raw_slots_append(&fs,frame,1)==RAW_SLOTS_ERR_IO);assert(u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    fresh_card();assert(raw_slots_open(&fs,&card)==0);assert(raw_slots_find_free(&fs)==0 && fs.selected_slot==1);
    reset_disk();format(0);begin();assert(raw_slots_finish(&fs,frame)==RAW_SLOTS_ERR_LENGTH);
    assert(u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    reset_disk();format(0);begin();assert(raw_slots_append(&fs,frame,3730)==RAW_SLOTS_ERR_LENGTH);
    reset_disk();format(0);begin();assert(raw_slots_append(&fs,frame+1,1)==RAW_SLOTS_ERR_ARGUMENT);
    reset_disk();format(0);begin();assert(raw_slots_append(&fs,frame,3729)==0);
    fail_sync=syncs+1;assert(raw_slots_finish(&fs,frame+3729*512)==RAW_SLOTS_ERR_IO);
    assert(u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    /* Whole-image path uses one callback, commits separately, and keeps the
       original disk format. Padding and producer length fail closed. */
    memcpy(padded,frame,sizeof(frame));memset(padded+sizeof(frame),0,160);
    reset_disk();format(0);begin();fs.write_payload=whole_write;
    uint32_t before=writes;
    assert(raw_slots_write_padded(&fs,padded)==0);
    assert(dma_writes==1 && writes==before+1 && whole_count==3730 && whole_lba==9);
    assert(fs.active && fs.written_sectors==3730 && u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    assert(memcmp(header(0)+512,padded,sizeof(padded))==0);
    assert(raw_slots_commit(&fs)==0 && !fs.active && u32(header(0)+12)==RAW_SLOTS_FULL);
    assert(u32(header(1)+12)==RAW_SLOTS_FREE && disk[(TEST_SECTORS-1)*512]==0xa5);
    reset_disk();format(0);begin();fs.write_payload=whole_write;padded[sizeof(frame)]=1;
    before=writes;assert(raw_slots_write_padded(&fs,padded)==RAW_SLOTS_ERR_ARGUMENT);
    assert(writes==before && u32(header(0)+12)==RAW_SLOTS_PARTIAL);padded[sizeof(frame)]=0;
    reset_disk();format(0);begin();fs.write_payload=whole_write;fail_write=writes+1;
    assert(raw_slots_write_padded(&fs,padded)==RAW_SLOTS_ERR_IO);
    assert(raw_slots_commit(&fs)==RAW_SLOTS_ERR_STATE && u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    reset_disk();format(0);begin();fs.write_payload=whole_write;
    assert(raw_slots_write_padded(&fs,padded)==0);fail_sync=syncs+1;
    assert(raw_slots_commit(&fs)==RAW_SLOTS_ERR_IO && u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    reset_disk();format(0);begin();fs.write_payload=whole_write;
    assert(raw_slots_commit(&fs)==RAW_SLOTS_ERR_LENGTH && u32(header(0)+12)==RAW_SLOTS_PARTIAL);
    reset_disk();format(0);begin();fs.write_payload=whole_write;
    assert(raw_slots_append(&fs,frame,1)==0);
    assert(raw_slots_write_padded(&fs,padded)==RAW_SLOTS_ERR_LENGTH);
    reset_disk();format(0);begin();fs.write_payload=whole_write;
    assert(raw_slots_write_padded(&fs,padded+1)==RAW_SLOTS_ERR_ARGUMENT);
    reset_disk();format(0);begin();
    assert(raw_slots_write_padded(&fs,padded)==RAW_SLOTS_ERR_ARGUMENT);
    /* Bounds/card identity are checked on mount. */
    fresh_card();card.sector_count--;
    assert(raw_slots_open(&fs,&card)==RAW_SLOTS_ERR_CAPACITY);
    reset_disk();format(0);disk[508]^=1;
    assert(raw_slots_open(&fs,&card)==RAW_SLOTS_ERR_VOLUME);
    puts("raw_slots C core: all assertions passed");return 0;
}
