/* Project disk-I/O adapter, not an upstream FatFs source. */
#include "ff.h"
#include "diskio.h"
#include "sd_diskio.h"

static sd_card_t *bound;

int sd_disk_bind(sd_card_t *card)
{
    if (!card || !card->initialized || !card->sector_count ||
        card->sector_count>0xFFFFFFFFULL) return -1;
    bound=card;
    return 0;
}

sd_card_t *sd_disk_card(void) { return bound; }

DSTATUS disk_status(BYTE drive)
{
    return drive || !bound || !bound->initialized ? STA_NOINIT : 0U;
}

DSTATUS disk_initialize(BYTE drive)
{
    /* sd_init belongs to the application; no hidden reinitialization here. */
    return disk_status(drive);
}

static int valid_range(BYTE drive, LBA_t sector, UINT count)
{
    return !disk_status(drive) && count &&
           (uint64_t)sector+count<=bound->sector_count;
}

DRESULT disk_read(BYTE drive, BYTE *buffer, LBA_t sector, UINT count)
{
    if (!buffer || !valid_range(drive,sector,count)) return RES_PARERR;
    while (count) {
        UINT n=count>64U ? 64U : count;
        if (sd_read_blocks(bound,(uint32_t)sector,buffer,n)) return RES_ERROR;
        sector+=n; buffer+=n*512U; count-=n;
    }
    return RES_OK;
}

DRESULT disk_write(BYTE drive, const BYTE *buffer, LBA_t sector, UINT count)
{
    if (!buffer || !valid_range(drive,sector,count)) return RES_PARERR;
    while (count) {
        UINT n=count>64U ? 64U : count;
        if (sd_write_blocks(bound,(uint32_t)sector,buffer,n)) return RES_ERROR;
        sector+=n; buffer+=n*512U; count-=n;
    }
    return RES_OK;
}

DRESULT disk_ioctl(BYTE drive, BYTE command, void *buffer)
{
    if (disk_status(drive)) return RES_NOTRDY;
    switch (command) {
    case CTRL_SYNC:
        return sd_sync(bound) ? RES_ERROR : RES_OK;
    case GET_SECTOR_COUNT:
        if (!buffer) return RES_PARERR;
        *(LBA_t *)buffer=(LBA_t)bound->sector_count;
        return RES_OK;
    case GET_SECTOR_SIZE:
        if (!buffer) return RES_PARERR;
        *(WORD *)buffer=512U;
        return RES_OK;
    case GET_BLOCK_SIZE:
        if (!buffer) return RES_PARERR;
        *(DWORD *)buffer=1U; /* Physical erase alignment unknown; no TRIM. */
        return RES_OK;
    default:
        return RES_PARERR;
    }
}
