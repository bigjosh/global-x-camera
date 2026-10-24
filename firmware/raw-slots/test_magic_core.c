/* Actual magic-slot allocator against a memory-backed SD transport. */
#include "magic_slots.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_SECTORS (3U*MAGIC_SLOTS_STRIDE+13U)
static uint8_t disk[TEST_SECTORS*512U];
static uint8_t storage[MAGIC_SLOTS_PADDED_BYTES+32U] __attribute__((aligned(32)));
static uint8_t *object=storage+12; /* camera at+4 is16B-aligned, SD at12mod16 */
static sd_card_t card;
static magic_slots_t slots;
static uint32_t reads, fail_read, writes, progresses, writer_mode;

static void put32(uint8_t *p,uint32_t value)
{ for(unsigned i=0;i<4;++i) p[i]=(uint8_t)(value>>(8U*i)); }
static uint8_t *slot(unsigned n) { return disk+(size_t)n*MAGIC_SLOTS_PADDED_BYTES; }
static void fresh(uint8_t erased)
{
    memset(disk,erased,sizeof(disk));memset(&card,0,sizeof(card));
    card.initialized=1;card.media_idle=1;card.sector_count=TEST_SECTORS;
    reads=fail_read=writes=progresses=writer_mode=0;
}
static void reopen(uint8_t erased)
{
    card.error=0;card.media_idle=1;reads=fail_read=0;
    assert(magic_slots_open(&slots,&card,erased)==0);
}
int sd_read_blocks(sd_card_t *c,uint32_t lba,void *buffer,uint32_t count)
{
    reads++;
    assert(count==1U && (uint64_t)lba+count<=TEST_SECTORS);
    if(c->error || (fail_read && reads==fail_read)) { c->error=1;return 1; }
    memcpy(buffer,disk+(size_t)lba*512U,512U);return 0;
}
void sd_progress(void) { progresses++; }
static int writer(sd_card_t *c,uint32_t lba,const void *buffer,uint32_t count,void *context)
{
    assert(context==&writer_mode);assert(count==MAGIC_SLOTS_STRIDE);
    assert(buffer==object);assert((uint64_t)lba+count<=TEST_SECTORS);writes++;
    if(writer_mode==1) { /* error after the leading sector consumed the slot */
        memcpy(disk+(size_t)lba*512U,buffer,512U);c->error=1;c->media_idle=0;return 1;
    }
    /* Model a streaming producer: footer is absent before writer entry. */
    if(writer_mode!=2) put32(object+MAGIC_SLOTS_TRAILER_OFFSET,MAGIC_SLOTS_END_MAGIC);
    if(writer_mode==5) object[MAGIC_SLOTS_OBJECT_BYTES]=1;
    memcpy(disk+(size_t)lba*512U,buffer,(size_t)count*512U);
    c->written_sectors+=count-(writer_mode==3?1U:0U);
    c->media_idle=writer_mode==4?0U:1U;return 0;
}
static void prepare(void)
{
    memset(storage,0xcc,sizeof(storage));memset(object,0,MAGIC_SLOTS_PADDED_BYTES);
    put32(object,MAGIC_SLOTS_START_MAGIC);
    for(uint32_t i=0;i<MAGIC_SLOTS_IMAGE_BYTES;i+=5) {
        uint32_t pixel=(i/5)*4;uint8_t low=0;
        for(uint32_t j=0;j<4;j++) {
            uint32_t v=(pixel+j)&1023;object[4+i+j]=(uint8_t)(v>>2);low|=(v&3)<<(2*j);
        }
        object[4+i+4]=low;
    }
}
static void select(void) { assert(magic_slots_find_free(&slots)==0); }
static int save(void) { return magic_slots_write(&slots,object,writer,&writer_mode); }

int main(int argc,char **argv)
{
    assert(MAGIC_SLOTS_OBJECT_BYTES==1909608U && MAGIC_SLOTS_PADDING_BYTES==152U);
    assert(((uintptr_t)object&3U)==0 && (((uintptr_t)object+4U)&15U)==0);
    fresh(0xff);
    assert(magic_slots_open(NULL,&card,255)==MAGIC_SLOTS_ERR_ARGUMENT);
    assert(magic_slots_open(&slots,&card,1)==MAGIC_SLOTS_ERR_ARGUMENT);
    card.sector_count=MAGIC_SLOTS_STRIDE-1;
    assert(magic_slots_open(&slots,&card,255)==MAGIC_SLOTS_ERR_CAPACITY);
    card.sector_count=0x100000001ULL;
    assert(magic_slots_open(&slots,&card,255)==MAGIC_SLOTS_ERR_CAPACITY);
    card.sector_count=0x100000000ULL;
    assert(magic_slots_open(&slots,&card,255)==0);
    assert(slots.slot_count==0x100000000ULL/MAGIC_SLOTS_STRIDE);

    for(unsigned erased=0;erased<=255;erased+=255) {
        fresh((uint8_t)erased);reopen((uint8_t)erased);select();
        assert(slots.selected_slot==0 && slots.slot_lba==0 && reads==1 && writes==0);
        for(unsigned byte=0;byte<4;++byte) {
            memset(slot(0),erased,512);slot(0)[byte]=(uint8_t)(erased^1);
            reopen((uint8_t)erased);select();assert(slots.selected_slot==1 && reads==2);
        }
        /* Unknown marker is occupied even if its first byte is erased. */
        memset(slot(0),erased,512);slot(0)[1]=0x5a;
        memcpy(slot(1),"bad!",4);reopen((uint8_t)erased);select();
        assert(slots.selected_slot==2 && reads==3);
        memcpy(slot(2),"used",4);reopen((uint8_t)erased);
        assert(magic_slots_find_free(&slots)==MAGIC_SLOTS_ERR_FULL && !slots.selected_valid);
        assert(writes==0);
        if(erased==255) break;
    }
    fresh(255);reopen(255);fail_read=1;
    assert(magic_slots_find_free(&slots)==MAGIC_SLOTS_ERR_IO && !slots.selected_valid && writes==0);
    fresh(255);reopen(255);select();prepare();object[0]=0;
    assert(save()==MAGIC_SLOTS_ERR_MARKER && writes==0 && !slots.active);
    fresh(255);reopen(255);select();prepare();
    assert(magic_slots_write(&slots,object+1,writer,&writer_mode)==MAGIC_SLOTS_ERR_ARGUMENT && writes==0);

    for(writer_mode=1;writer_mode<=5;) {
        unsigned mode=writer_mode;fresh(255);reopen(255);select();prepare();writer_mode=mode;
        int result=save();
        assert(result==(mode==1?MAGIC_SLOTS_ERR_IO:mode==3?MAGIC_SLOTS_ERR_LENGTH:
                       mode==4?MAGIC_SLOTS_ERR_NOT_IDLE:MAGIC_SLOTS_ERR_MARKER));
        assert(writes==1 && slots.active && !slots.selected_valid && !slots.written_sectors);
        assert(save()==MAGIC_SLOTS_ERR_STATE && writes==1);
        reopen(255);select();assert(slots.selected_slot==1);writer_mode=mode+1;
    }

    /* Fixture: complete first slot, interrupted second, untouched third/tail. */
    fresh(255);reopen(255);select();prepare();assert(save()==0);
    assert(writes==1 && !slots.active && slots.written_sectors==3730 && slots.write_sectors==3730);
    assert(card.written_sectors==3730 && !memcmp(slot(0),object,MAGIC_SLOTS_PADDED_BYTES));
    for(size_t i=MAGIC_SLOTS_PADDED_BYTES;i<sizeof(disk);++i) assert(disk[i]==255);
    for(unsigned i=0;i<12;++i) assert(storage[i]==0xcc);
    for(unsigned i=12+MAGIC_SLOTS_PADDED_BYTES;i<sizeof(storage);++i) assert(storage[i]==0xcc);
    reopen(255);select();assert(slots.selected_slot==1);prepare();writer_mode=1;
    assert(save()==MAGIC_SLOTS_ERR_IO);reopen(255);select();assert(slots.selected_slot==2);
    assert(argc==2);FILE *out=fopen(argv[1],"wb");assert(out);
    assert(fwrite(disk,1,sizeof(disk),out)==sizeof(disk));assert(!fclose(out));
    puts("magic slot core: passed");return 0;
}
