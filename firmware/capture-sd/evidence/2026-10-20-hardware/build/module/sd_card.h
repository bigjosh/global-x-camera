#ifndef GLOBAL_X_SD_CARD_H
#define GLOBAL_X_SD_CARD_H

#include <stdint.h>

/* Native SDMMC2, one bit, 3.3 V. No card cache, UHS, bus-width, erase or trim
 * commands are enabled. All APIs are synchronous and require one owner.
 * The caller must place this object and its buffers outside the capture frame.
 * Zero-initialize the object before its first sd_init().
 */
#define SD_SECTOR_BYTES 512U
#define SD_MAX_TRANSFER_SECTORS 64U

enum sd_error {
    SD_OK=0, SD_ERR_ARGUMENT, SD_ERR_STATE, SD_ERR_CLOCK, SD_ERR_GPIO,
    SD_ERR_VOLTAGE, SD_ERR_TIMER, SD_ERR_COMMAND_TIMEOUT, SD_ERR_COMMAND_CRC,
    SD_ERR_RESPONSE, SD_ERR_CARD, SD_ERR_UNSUPPORTED, SD_ERR_NOT_READY,
    SD_ERR_CAPACITY, SD_ERR_DATA, SD_ERR_DATA_TIMEOUT, SD_ERR_LENGTH,
    SD_ERR_CONTROLLER_BUSY
};

enum sd_stage {
    SD_STAGE_NONE=0, SD_STAGE_PREFLIGHT, SD_STAGE_GPIO, SD_STAGE_IDENTIFY,
    SD_STAGE_SELECT, SD_STAGE_READ, SD_STAGE_WRITE, SD_STAGE_SYNC,
    SD_STAGE_ABORT, SD_STAGE_DEINIT
};

typedef struct sd_card {
    uint64_t sector_count;
    uint64_t read_sectors, written_sectors;
    uint64_t read_cycles, write_cycles, ready_cycles;
    uint32_t initialized, controller_owned, media_idle;
    uint32_t clock_hz, ocr, rca, cid[4], csd[4];
    /* First error stays latched until a fresh init; further reads/writes refuse
     * to proceed. sd_sync/deinit can still establish idle and release ownership.
     * media_idle proves an observed idle protocol state, not power-loss safety
     * of a filesystem or the card's internal flash translation layer. */
    uint32_t error, error_stage, error_command, error_sta;
    uint32_t stage, last_command, last_argument, last_sta, last_r1;
    uint32_t command_count, last_ready_r1, last_stop_r1, cleanup_error;
    uint32_t transfer_words, transfer_sta, transfer_cycles, init_cycles;
    uint32_t gpioc_idr, gpioe_idr, vddio5_control;
    /* Private saved host state; do not modify while initialized. */
    uint32_t saved_sdmmc_mux, saved_demcr, saved_dwt, timer_owned;
} sd_card_t;

/* max_hz selects 100 kHz, 12.5 MHz or 25 MHz. Other values are rejected.
 * Requires the retained 400 MHz CPU / 150 MHz HCLK clock configuration.
 * Init does not reset the sensor, CPU, NOR interface, or card power.
 * A hardware transfer holds at most 64 sectors, reduced to 16 at 100 kHz so
 * payload time alone fits the 2 s read deadline. Write deadline is 5 s per chunk,
 * followed by at most 2 s to establish ready. These are finite bench timeouts,
 * not guaranteed latency bounds for every card or maintenance condition.
 */
int sd_init(sd_card_t *card, uint32_t max_hz);
int sd_read_blocks(sd_card_t *card, uint32_t lba, void *buffer, uint32_t count);
int sd_write_blocks(sd_card_t *card, uint32_t lba, const void *buffer, uint32_t count);
/* Wait for ready/TRANSFER, DAT0 HIGH and idle host state. This driver never
 * enables the optional SD card cache. No cache-flush feature is assumed. */
int sd_sync(sd_card_t *card);
/* Refuses to disable the controller unless card idle is freshly verified.
 * Leaves CLK input/pull-down and CMD/DAT0/DAT3 input/pull-up while card is powered.
 * GPIO/PWR clocks and VDDIO5 supply-valid remain enabled for other users.
 */
int sd_deinit(sd_card_t *card);

/* Optional monotonic-clock service hook. The weak default is empty. A caller
 * may override it to extend DWT's 32-bit count while long filesystem operations
 * run. Calls occur at command/chunk boundaries and throughout bounded waits,
 * never per FIFO word. The override must be short, nonblocking, and must not
 * mutate hardware or call back into this driver/filesystem (no reentrancy).
 */
void sd_progress(void);

#endif
