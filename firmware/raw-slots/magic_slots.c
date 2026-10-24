#include "magic_slots.h"
#include <stddef.h>

_Static_assert(MAGIC_SLOTS_PADDING_BYTES==152U,"magic slot padding");
_Static_assert(MAGIC_SLOTS_PADDED_BYTES==1909760U,"magic slot extent");

static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static int fault(magic_slots_t *f,uint32_t error)
{ if(f && !f->error) f->error=error; return (int)error; }

int magic_slots_open(magic_slots_t *f,sd_card_t *card,uint32_t erased_byte)
{
    if(!f || !card) return MAGIC_SLOTS_ERR_ARGUMENT;
    uint8_t *bytes=(uint8_t *)f;
    for(size_t i=0;i<sizeof(*f);++i) bytes[i]=0;
    f->card=card;f->selected_slot=MAGIC_SLOTS_NO_SLOT;f->erased_byte=erased_byte;
    if(erased_byte!=0U && erased_byte!=255U) return fault(f,MAGIC_SLOTS_ERR_ARGUMENT);
    if(!card->initialized || card->error) return fault(f,MAGIC_SLOTS_ERR_STATE);
    if(card->sector_count<MAGIC_SLOTS_STRIDE || card->sector_count>0x100000000ULL)
        return fault(f,MAGIC_SLOTS_ERR_CAPACITY);
    f->slot_count=(uint32_t)(card->sector_count/MAGIC_SLOTS_STRIDE);
    f->opened=1;return 0;
}

int magic_slots_find_free(magic_slots_t *f)
{
    if(!f || !f->opened || f->active || f->error) return MAGIC_SLOTS_ERR_STATE;
    if(!f->card->initialized || f->card->error) return fault(f,MAGIC_SLOTS_ERR_STATE);
    f->selected_valid=0;f->selected_slot=MAGIC_SLOTS_NO_SLOT;f->scan_headers=0;
    uint32_t erased_word=f->erased_byte*0x01010101U;
    for(uint32_t i=0;i<f->slot_count;++i) {
        uint32_t lba=i*MAGIC_SLOTS_STRIDE;
        if(sd_read_blocks(f->card,lba,f->io,1)) return fault(f,MAGIC_SLOTS_ERR_IO);
        f->read_sectors++;f->scan_headers++;
        if(get32((const uint8_t *)f->io)==erased_word) {
            f->selected_slot=i;f->slot_lba=lba;f->selected_valid=1;return 0;
        }
        sd_progress();
    }
    return fault(f,MAGIC_SLOTS_ERR_FULL);
}

int magic_slots_write(magic_slots_t *f,const void *buffer,
                      magic_slots_writer_t writer,void *context)
{
    if(!f || !f->opened || !f->selected_valid || f->active || f->error)
        return MAGIC_SLOTS_ERR_STATE;
    if(!buffer || !writer || ((uintptr_t)buffer&3U))
        return fault(f,MAGIC_SLOTS_ERR_ARGUMENT);
    const uint8_t *p=(const uint8_t *)buffer;
    if(get32(p)!=MAGIC_SLOTS_START_MAGIC) return fault(f,MAGIC_SLOTS_ERR_MARKER);
    if(!f->card->initialized || f->card->error) return fault(f,MAGIC_SLOTS_ERR_STATE);
    uint64_t before=f->card->written_sectors;
    f->active=1;f->selected_valid=0;f->written_sectors=0;
    int result=writer(f->card,f->slot_lba,buffer,MAGIC_SLOTS_STRIDE,context);
    if(result || f->card->error) return fault(f,MAGIC_SLOTS_ERR_IO);
    if(!f->card->media_idle) return fault(f,MAGIC_SLOTS_ERR_NOT_IDLE);
    if(f->card->written_sectors-before!=MAGIC_SLOTS_STRIDE)
        return fault(f,MAGIC_SLOTS_ERR_LENGTH);
    if(get32(p)!=MAGIC_SLOTS_START_MAGIC ||
       get32(p+MAGIC_SLOTS_TRAILER_OFFSET)!=MAGIC_SLOTS_END_MAGIC)
        return fault(f,MAGIC_SLOTS_ERR_MARKER);
    for(uint32_t i=MAGIC_SLOTS_OBJECT_BYTES;i<MAGIC_SLOTS_PADDED_BYTES;++i)
        if(p[i]) return fault(f,MAGIC_SLOTS_ERR_MARKER);
    f->written_sectors=MAGIC_SLOTS_STRIDE;f->write_sectors+=MAGIC_SLOTS_STRIDE;
    f->active=0;return 0;
}
