#include "raw_slots.h"
#include <stddef.h>

#define VOLUME_FORMATTING 1U
#define VOLUME_READY 2U
#define CRC_OFFSET 508U

static const uint8_t volume_magic[8]={'G','X','R','W','V','O','L','1'};
static const uint8_t slot_magic[8]={'G','X','R','A','W','S','L','1'};

static void clear(void *p, uint32_t n)
{ uint8_t *b=p; while(n--) *b++=0; }
static void copy(void *d,const void *s,uint32_t n)
{ uint8_t *a=d; const uint8_t *b=s; while(n--) *a++=*b++; }
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static uint64_t get64(const uint8_t *p)
{ return get32(p)|((uint64_t)get32(p+4)<<32); }
static void put32(uint8_t *p,uint32_t x)
{ p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);p[2]=(uint8_t)(x>>16);p[3]=(uint8_t)(x>>24); }
static void put64(uint8_t *p,uint64_t x)
{ put32(p,(uint32_t)x);put32(p+4,(uint32_t)(x>>32)); }
static int equal(const uint8_t *a,const uint8_t *b,uint32_t n)
{ while(n--) if(*a++!=*b++) return 0; return 1; }
static int zero(const uint8_t *p,uint32_t n)
{ while(n--) if(*p++) return 0; return 1; }
static uint32_t crc32(const uint8_t *p,uint32_t n)
{
    uint32_t c=0xffffffffU;
    while(n--) { c^=*p++; for(uint32_t i=0;i<8;i++) c=(c>>1)^((0U-(c&1U))&0xedb88320U); }
    return ~c;
}
static void seal(uint8_t *p) { put32(p+CRC_OFFSET,crc32(p,CRC_OFFSET)); }
static int sealed(const uint8_t *p) { return get32(p+CRC_OFFSET)==crc32(p,CRC_OFFSET); }
static int fault(raw_slots_t *f,uint32_t e)
{ if(f && !f->error) f->error=e; return (int)e; }
static int initialize(raw_slots_t *f,sd_card_t *c)
{
    if(!f || !c) return RAW_SLOTS_ERR_ARGUMENT;
    clear(f,sizeof(*f));f->card=c;f->selected_slot=RAW_SLOTS_NO_SLOT;
    if(!c->initialized || c->error) return fault(f,RAW_SLOTS_ERR_STATE);
    if(c->sector_count>0x100000000ULL || c->sector_count<RAW_SLOTS_FIRST_LBA+RAW_SLOTS_STRIDE)
        return fault(f,RAW_SLOTS_ERR_CAPACITY);
    return 0;
}
static int read_one(raw_slots_t *f,uint32_t lba)
{
    if(sd_read_blocks(f->card,lba,f->io,1)) return fault(f,RAW_SLOTS_ERR_IO);
    f->read_sectors++;return 0;
}
static int write_one(raw_slots_t *f,uint32_t lba)
{
    if(sd_write_blocks(f->card,lba,f->io,1)) return fault(f,RAW_SLOTS_ERR_IO);
    f->write_sectors++;return 0;
}
static int ready(raw_slots_t *f)
{ return sd_sync(f->card)?fault(f,RAW_SLOTS_ERR_IO):0; }
static uint32_t slot_lba(uint32_t index)
{ return RAW_SLOTS_FIRST_LBA+index*RAW_SLOTS_STRIDE; }

static int volume_record(const uint8_t *p)
{
    return equal(p,volume_magic,8) && get32(p+8)==RAW_SLOTS_VERSION && sealed(p)
        && (get32(p+12)==VOLUME_FORMATTING || get32(p+12)==VOLUME_READY)
        && get64(p+16)!=0 && get32(p+32)==RAW_SLOTS_FIRST_LBA
        && get32(p+36)==RAW_SLOTS_STRIDE && get32(p+40)>0
        && get32(p+44)==RAW_SLOTS_PAYLOAD_BYTES && get32(p+48)==RAW_SLOTS_WIDTH
        && get32(p+52)==RAW_SLOTS_HEIGHT && get32(p+56)==RAW_SLOTS_ROW_BYTES
        && get32(p+60)==RAW_SLOTS_PACKING_MIPI_RAW10 && get32(p+64)==SD_SECTOR_BYTES
        && zero(p+68,CRC_OFFSET-68);
}
static void make_volume(raw_slots_t *f,uint32_t state)
{
    uint8_t *p=(uint8_t *)f->io;clear(p,512);copy(p,volume_magic,8);
    put32(p+8,RAW_SLOTS_VERSION);put32(p+12,state);put64(p+16,f->generation);
    put64(p+24,f->card->sector_count);put32(p+32,RAW_SLOTS_FIRST_LBA);
    put32(p+36,RAW_SLOTS_STRIDE);put32(p+40,f->slot_count);
    put32(p+44,RAW_SLOTS_PAYLOAD_BYTES);put32(p+48,RAW_SLOTS_WIDTH);
    put32(p+52,RAW_SLOTS_HEIGHT);put32(p+56,RAW_SLOTS_ROW_BYTES);
    put32(p+60,RAW_SLOTS_PACKING_MIPI_RAW10);put32(p+64,SD_SECTOR_BYTES);seal(p);
}
static int publish_volume(raw_slots_t *f,uint32_t state)
{
    make_volume(f,state);
    if(write_one(f,0) || ready(f) || read_one(f,0)) return f->error;
    const uint8_t *p=(const uint8_t *)f->io;
    if(!volume_record(p) || get32(p+12)!=state || get64(p+16)!=f->generation
       || get64(p+24)!=f->card->sector_count || get32(p+40)!=f->slot_count)
        return fault(f,RAW_SLOTS_ERR_VERIFY);
    return 0;
}
static void make_slot(raw_slots_t *f,uint32_t index,uint32_t state)
{
    uint8_t *p=(uint8_t *)f->io;clear(p,512);copy(p,slot_magic,8);
    put32(p+8,RAW_SLOTS_VERSION);put32(p+12,state);put64(p+16,f->generation);
    put32(p+24,index);put32(p+28,RAW_SLOTS_PAYLOAD_BYTES);
    put32(p+32,slot_lba(index)+1);put32(p+36,RAW_SLOTS_WIDTH);
    put32(p+40,RAW_SLOTS_HEIGHT);put32(p+44,RAW_SLOTS_ROW_BYTES);
    put32(p+48,RAW_SLOTS_PACKING_MIPI_RAW10);
    if(state!=RAW_SLOTS_FREE) {
        put32(p+52,f->metadata.metadata_flags);put64(p+56,f->metadata.capture_id);
        put64(p+64,f->metadata.timestamp_us);put32(p+72,f->metadata.exposure_us);
        put32(p+76,f->metadata.analog_gain_milli);put32(p+80,f->metadata.digital_gain_milli);
        put32(p+84,f->metadata.orientation);
    }
    if(state==RAW_SLOTS_FULL) put32(p+88,RAW_SLOTS_PAYLOAD_BYTES);
    seal(p);
}
static int slot_record(raw_slots_t *f,uint32_t index)
{
    const uint8_t *p=(const uint8_t *)f->io;uint32_t state=get32(p+12);
    if(!equal(p,slot_magic,8) || get32(p+8)!=RAW_SLOTS_VERSION || !sealed(p)
       || get64(p+16)!=f->generation || get32(p+24)!=index
       || get32(p+28)!=RAW_SLOTS_PAYLOAD_BYTES || get32(p+32)!=slot_lba(index)+1
       || get32(p+36)!=RAW_SLOTS_WIDTH || get32(p+40)!=RAW_SLOTS_HEIGHT
       || get32(p+44)!=RAW_SLOTS_ROW_BYTES || get32(p+48)!=RAW_SLOTS_PACKING_MIPI_RAW10
       || !zero(p+92,CRC_OFFSET-92)) return fault(f,RAW_SLOTS_ERR_HEADER);
    if(state!=RAW_SLOTS_FREE && state!=RAW_SLOTS_PARTIAL && state!=RAW_SLOTS_FULL)
        return fault(f,RAW_SLOTS_ERR_HEADER);
    if(get32(p+88)!=(state==RAW_SLOTS_FULL?RAW_SLOTS_PAYLOAD_BYTES:0)
       || (state==RAW_SLOTS_FREE && !zero(p+52,36))) return fault(f,RAW_SLOTS_ERR_HEADER);
    return 0;
}

int raw_slots_open(raw_slots_t *f,sd_card_t *c)
{
    int e=initialize(f,c);if(e) return e;
    if(read_one(f,0)) return f->error;
    const uint8_t *p=(const uint8_t *)f->io;
    if(!volume_record(p)) return fault(f,RAW_SLOTS_ERR_VOLUME);
    if(get32(p+12)!=VOLUME_READY) return fault(f,RAW_SLOTS_ERR_FORMATTING);
    if(get64(p+24)!=c->sector_count || (uint64_t)get32(p+40)*RAW_SLOTS_STRIDE
       >c->sector_count-RAW_SLOTS_FIRST_LBA) return fault(f,RAW_SLOTS_ERR_CAPACITY);
    f->generation=get64(p+16);f->slot_count=get32(p+40);f->opened=1;return 0;
}

int raw_slots_format(raw_slots_t *f,sd_card_t *c,uint32_t lo,uint32_t hi,uint32_t limit)
{
    int e=initialize(f,c);if(e) return e;
    f->generation=lo|((uint64_t)hi<<32);
    if(!f->generation) return fault(f,RAW_SLOTS_ERR_GENERATION);
    uint32_t capacity=(uint32_t)((c->sector_count-RAW_SLOTS_FIRST_LBA)/RAW_SLOTS_STRIDE);
    if(limit>capacity) return fault(f,RAW_SLOTS_ERR_CAPACITY);
    f->slot_count=limit?limit:capacity;
    if(ready(f) || read_one(f,0)) return f->error;
    if(volume_record((const uint8_t *)f->io) && get64((const uint8_t *)f->io+16)==f->generation)
        return fault(f,RAW_SLOTS_ERR_GENERATION);
    if(publish_volume(f,VOLUME_FORMATTING)) return f->error;
    for(uint32_t i=0;i<f->slot_count;i++) {
        make_slot(f,i,RAW_SLOTS_FREE);
        if(write_one(f,slot_lba(i))) return f->error;
        f->formatted_slots=i+1;sd_progress();
    }
    if(ready(f) || publish_volume(f,VOLUME_READY)) return f->error;
    f->opened=1;return 0;
}

int raw_slots_find_free(raw_slots_t *f)
{
    if(!f || !f->opened || f->active || f->error) return RAW_SLOTS_ERR_STATE;
    f->selected_valid=0;f->selected_slot=RAW_SLOTS_NO_SLOT;f->scan_headers=0;
    for(uint32_t i=0;i<f->slot_count;i++) {
        if(read_one(f,slot_lba(i))) return f->error;
        f->scan_headers++;
        if(slot_record(f,i)) return f->error;
        if(get32((const uint8_t *)f->io+12)==RAW_SLOTS_FREE) {
            f->selected_slot=i;f->payload_lba=slot_lba(i)+1;f->selected_valid=1;return 0;
        }
        sd_progress();
    }
    return fault(f,RAW_SLOTS_ERR_FULL);
}

int raw_slots_begin(raw_slots_t *f,const raw_slots_metadata_t *m)
{
    if(!f || !f->opened || !f->selected_valid || f->active || f->error)
        return RAW_SLOTS_ERR_STATE;
    if(m) copy(&f->metadata,m,sizeof(*m));
    else { clear(&f->metadata,sizeof(f->metadata));f->metadata.orientation=0xffffffffU; }
    f->written_sectors=0;f->active=1;f->selected_valid=0;
    make_slot(f,f->selected_slot,RAW_SLOTS_PARTIAL);
    if(write_one(f,slot_lba(f->selected_slot))) return f->error;
    return 0;
}

int raw_slots_append(raw_slots_t *f,const void *buffer,uint32_t count)
{
    if(!f || !f->opened || !f->active || f->error) return RAW_SLOTS_ERR_STATE;
    if(!buffer || !count || ((uintptr_t)buffer&3U)) return fault(f,RAW_SLOTS_ERR_ARGUMENT);
    if(f->written_sectors>RAW_SLOTS_WHOLE_SECTORS || count>RAW_SLOTS_WHOLE_SECTORS-f->written_sectors)
        return fault(f,RAW_SLOTS_ERR_LENGTH);
    raw_slots_writer_t writer=f->write_payload?f->write_payload:sd_write_blocks;
    if(writer(f->card,f->payload_lba+f->written_sectors,buffer,count))
        return fault(f,RAW_SLOTS_ERR_IO);
    f->written_sectors+=count;f->write_sectors+=count;return 0;
}

int raw_slots_finish(raw_slots_t *f,const void *tail)
{
    if(!f || !f->opened || !f->active || f->error) return RAW_SLOTS_ERR_STATE;
    if(!tail) return fault(f,RAW_SLOTS_ERR_ARGUMENT);
    if(f->written_sectors!=RAW_SLOTS_WHOLE_SECTORS) return fault(f,RAW_SLOTS_ERR_LENGTH);
    clear(f->io,512);copy(f->io,tail,RAW_SLOTS_TAIL_BYTES);
    raw_slots_writer_t writer=f->write_payload?f->write_payload:sd_write_blocks;
    if(writer(f->card,f->payload_lba+f->written_sectors,f->io,1))
        return fault(f,RAW_SLOTS_ERR_IO);
    f->written_sectors++;f->write_sectors++;
    if(ready(f)) return f->error;
    make_slot(f,f->selected_slot,RAW_SLOTS_FULL);
    if(write_one(f,slot_lba(f->selected_slot)) || ready(f)) return f->error;
    f->active=0;return 0;
}
