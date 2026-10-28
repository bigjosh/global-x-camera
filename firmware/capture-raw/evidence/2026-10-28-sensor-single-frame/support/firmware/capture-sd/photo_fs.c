/* Prototype FAT32 save layer. No RTC timestamp, filesystem journal, relocation,
 * overwrite, deletion or automatic format. Power-loss behavior is unqualified.
 */
#include <string.h>
#include "photo_fs.h"
#include "fs/ff.h"
#include "fs/diskio.h"
#include "fs/sd_diskio.h"

static FATFS volume;
static FIL file;
static photo_fs_report_t report;
static uint32_t mounted, active;
static uint8_t format_work[4096] __attribute__((aligned(4)));

const photo_fs_report_t *photo_fs_get_report(void) { return &report; }

static int failed(uint32_t stage, FRESULT result, int code)
{
    report.stage=stage; report.fat_result=(uint32_t)result;
    report.state=PHOTO_FS_STATE_ERROR;
    return code;
}

static int card_sync(uint32_t stage)
{
    if (disk_ioctl(0,CTRL_SYNC,0)!=RES_OK)
        return failed(stage,FR_DISK_ERR,PHOTO_FS_ERROR);
    return PHOTO_FS_OK;
}

static int attach(sd_card_t *card)
{
    if (!card || !card->initialized || !card->media_idle)
        return failed(PHOTO_FS_STAGE_BIND,FR_NOT_READY,PHOTO_FS_UNSAFE_MEDIA);
    if (sd_disk_bind(card))
        return failed(PHOTO_FS_STAGE_BIND,FR_INVALID_PARAMETER,PHOTO_FS_BAD_ARGUMENT);
    report.sector_count=card->sector_count;
    return PHOTO_FS_OK;
}

int photo_fs_mount(sd_card_t *card)
{
    if (active) return PHOTO_FS_BAD_STATE;
    memset(&report,0,sizeof(report));
    mounted=0U;
    int rc=attach(card);
    if (rc) return rc;
    FRESULT result=f_mount(&volume,"0:",1);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_MOUNT,result,PHOTO_FS_ERROR);
    report.cluster_bytes=(uint32_t)volume.csize*512U;
    if (volume.fs_type!=FS_FAT32 || report.cluster_bytes!=32768U) {
        (void)f_mount(0,"0:",0);
        return failed(PHOTO_FS_STAGE_MOUNT,FR_NO_FILESYSTEM,PHOTO_FS_WRONG_FORMAT);
    }
    mounted=1U; report.state=PHOTO_FS_STATE_MOUNTED;
    report.stage=PHOTO_FS_STAGE_MOUNT;
    return PHOTO_FS_OK;
}

int photo_fs_format(sd_card_t *card)
{
    if (active) return PHOTO_FS_BAD_STATE;
    memset(&report,0,sizeof(report));
    mounted=0U;
    int rc=attach(card);
    if (rc) return rc;
    (void)f_mount(0,"0:",0);
    /* No FM_SFD: f_mkfs creates one partition spanning the physical drive. */
    const MKFS_PARM options={FM_FAT32,2U,2048U,0U,32768U};
    FRESULT result=f_mkfs("0:",&options,format_work,sizeof(format_work));
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_FORMAT,result,PHOTO_FS_ERROR);
    rc=card_sync(PHOTO_FS_STAGE_FORMAT);
    return rc ? rc : photo_fs_mount(card);
}

static void make_name(char *name, uint32_t number, const char *extension)
{
    memcpy(name,"IMG00000.",9U);
    for (unsigned i=8U; i>3U; --i) {
        name[i-1U]=(char)('0'+number%10U); number/=10U;
    }
    memcpy(name+9U,extension,3U); name[12]=0;
}

int photo_fs_open(uint32_t expected_max_bytes)
{
    if (!mounted || active || report.state==PHOTO_FS_STATE_ERROR) return PHOTO_FS_BAD_STATE;
    if (!expected_max_bytes) return PHOTO_FS_BAD_ARGUMENT;
    report.completed=0U; report.bytes_written=0U;
    report.expected_max_bytes=expected_max_bytes;
    FATFS *fs=0; DWORD free_clusters=0;
    FRESULT result=f_getfree("0:",&free_clusters,&fs);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_SPACE,result,PHOTO_FS_ERROR);
    report.free_clusters=free_clusters;
    /* Keep one additional cluster for a growing root directory. */
    uint64_t need=((uint64_t)expected_max_bytes+32767U)/32768U+1U;
    if (free_clusters<need) return failed(PHOTO_FS_STAGE_SPACE,FR_DENIED,PHOTO_FS_FULL);
    for (uint32_t number=1U; number<=99999U; ++number) {
        make_name(report.final_name,number,"PNG");
        make_name(report.temporary_name,number,"TMP");
        result=f_stat(report.final_name,0);
        if (result==FR_OK) continue;
        if (result!=FR_NO_FILE) return failed(PHOTO_FS_STAGE_NAME,result,PHOTO_FS_ERROR);
        result=f_stat(report.temporary_name,0);
        if (result==FR_OK) continue;
        if (result!=FR_NO_FILE) return failed(PHOTO_FS_STAGE_NAME,result,PHOTO_FS_ERROR);
        result=f_open(&file,report.temporary_name,FA_WRITE|FA_CREATE_NEW);
        if (result==FR_EXIST) continue;
        if (result!=FR_OK) return failed(PHOTO_FS_STAGE_OPEN,result,PHOTO_FS_ERROR);
        report.file_number=number; report.state=PHOTO_FS_STATE_OPEN;
        report.stage=PHOTO_FS_STAGE_OPEN; report.fat_result=FR_OK; active=1U;
        return PHOTO_FS_OK;
    }
    return failed(PHOTO_FS_STAGE_NAME,FR_DENIED,PHOTO_FS_FULL);
}

int photo_fs_append(const void *data, size_t bytes)
{
    if (!active || report.state!=PHOTO_FS_STATE_OPEN) return PHOTO_FS_BAD_STATE;
    if ((!data && bytes) || bytes>report.expected_max_bytes-report.bytes_written)
        return failed(PHOTO_FS_STAGE_WRITE,FR_INVALID_PARAMETER,PHOTO_FS_BAD_ARGUMENT);
    const uint8_t *p=(const uint8_t *)data;
    while (bytes) {
        UINT wanted=bytes>32768U ? 32768U : (UINT)bytes, written=0U;
        FRESULT result=f_write(&file,p,wanted,&written);
        report.bytes_written+=written;
        if (result!=FR_OK) return failed(PHOTO_FS_STAGE_WRITE,result,PHOTO_FS_ERROR);
        if (written!=wanted) return failed(PHOTO_FS_STAGE_WRITE,FR_DENIED,PHOTO_FS_FULL);
        p+=wanted; bytes-=wanted;
    }
    return PHOTO_FS_OK;
}

int photo_fs_write_callback(void *context, const uint8_t *data, size_t bytes)
{
    (void)context;
    /* png16_write_fn uses boolean success, unlike the filesystem API. */
    return photo_fs_append(data,bytes)==PHOTO_FS_OK;
}

int photo_fs_finish(void)
{
    if (!active || report.state!=PHOTO_FS_STATE_OPEN || !report.bytes_written)
        return PHOTO_FS_BAD_STATE;
    FRESULT result=f_sync(&file);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_SYNC_FILE,result,PHOTO_FS_ERROR);
    result=f_close(&file);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_CLOSE,result,PHOTO_FS_ERROR);
    active=0U;
    if (card_sync(PHOTO_FS_STAGE_SYNC_CARD)) return PHOTO_FS_ERROR;
    result=f_rename(report.temporary_name,report.final_name);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_RENAME,result,PHOTO_FS_ERROR);
    if (card_sync(PHOTO_FS_STAGE_SYNC_CARD)) return PHOTO_FS_ERROR;
    report.completed=1U; report.state=PHOTO_FS_STATE_FINISHED;
    report.stage=PHOTO_FS_STAGE_RENAME; report.fat_result=FR_OK;
    return PHOTO_FS_OK;
}

int photo_fs_abort(void)
{
    if (!active) return PHOTO_FS_BAD_STATE;
    sd_card_t *card=sd_disk_card();
    /* Do not issue more media operations after unproven driver cleanup. */
    if (!card || !card->media_idle)
        return failed(PHOTO_FS_STAGE_ABORT,FR_NOT_READY,PHOTO_FS_UNSAFE_MEDIA);
    FRESULT result=f_close(&file);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_ABORT,result,PHOTO_FS_ERROR);
    active=0U;
    if (card_sync(PHOTO_FS_STAGE_ABORT)) return PHOTO_FS_ERROR;
    report.state=PHOTO_FS_STATE_ABORTED; report.stage=PHOTO_FS_STAGE_ABORT;
    report.completed=0U; report.fat_result=FR_OK;
    return PHOTO_FS_OK;
}

static int valid_name(const char *name)
{
    if (!name || strlen(name)!=12U || memcmp(name,"IMG",3U) || name[8]!='.')
        return 0;
    for (unsigned i=3U; i<8U; ++i) if (name[i]<'0' || name[i]>'9') return 0;
    return !memcmp(name+9U,"PNG",3U) || !memcmp(name+9U,"TMP",3U);
}

int photo_fs_readback(const char *name, uint32_t offset, void *buffer,
                      uint32_t capacity, uint32_t *bytes_read)
{
    if (bytes_read) *bytes_read=0U;
    if (!mounted || active) return PHOTO_FS_BAD_STATE;
    if (!valid_name(name) || !bytes_read || (!buffer && capacity))
        return PHOTO_FS_BAD_ARGUMENT;
    FRESULT result=f_open(&file,name,FA_READ);
    if (result!=FR_OK) return failed(PHOTO_FS_STAGE_READBACK,result,PHOTO_FS_ERROR);
    active=1U;
    if (offset>f_size(&file)) result=FR_INVALID_PARAMETER;
    else result=f_lseek(&file,offset);
    if (result==FR_OK) {
        UINT got=0U;
        result=f_read(&file,buffer,capacity,&got);
        *bytes_read=got;
    }
    FRESULT closed=f_close(&file);
    if (closed==FR_OK) active=0U;
    if (result==FR_OK) result=closed;
    return result==FR_OK ? PHOTO_FS_OK : failed(PHOTO_FS_STAGE_READBACK,result,PHOTO_FS_ERROR);
}
