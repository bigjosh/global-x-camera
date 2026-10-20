/* Host-only storage stub. Never link this into firmware. */
#include <stdint.h>
#include <string.h>
#include "sd_card.h"

typedef int (*io_callback)(uint32_t, void *, uint32_t);
typedef int (*sync_callback)(void);
static io_callback read_callback, write_callback;
static sync_callback ready_callback;
static sd_card_t card;

void host_callbacks(io_callback read_fn, io_callback write_fn, sync_callback sync_fn)
{
    read_callback=read_fn; write_callback=write_fn; ready_callback=sync_fn;
}

sd_card_t *host_card(uint64_t sectors)
{
    memset(&card,0,sizeof(card));
    card.sector_count=sectors;
    card.initialized=card.controller_owned=card.media_idle=1U;
    return &card;
}

int sd_read_blocks(sd_card_t *c, uint32_t lba, void *buffer, uint32_t count)
{
    if (!c || c->error || !buffer || !count || count>64U ||
        (uint64_t)lba+count>c->sector_count) return SD_ERR_ARGUMENT;
    if (read_callback(lba,buffer,count)) { c->error=SD_ERR_DATA; return SD_ERR_DATA; }
    c->read_sectors+=count; return SD_OK;
}

int sd_write_blocks(sd_card_t *c, uint32_t lba, const void *buffer, uint32_t count)
{
    if (!c || c->error || !buffer || !count || count>64U ||
        (uint64_t)lba+count>c->sector_count) return SD_ERR_ARGUMENT;
    if (write_callback(lba,(void *)buffer,count)) { c->error=SD_ERR_DATA; return SD_ERR_DATA; }
    c->written_sectors+=count; return SD_OK;
}

int sd_sync(sd_card_t *c)
{
    if (!c) return SD_ERR_ARGUMENT;
    return ready_callback() ? SD_ERR_NOT_READY : SD_OK;
}
