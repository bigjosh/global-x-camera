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
#define SD_DMA_MAX_TRANSFER_SECTORS 1024U
#define SD_DMA_PREERASE_MAX_SECTORS 4096U

enum sd_error {
    SD_OK=0, SD_ERR_ARGUMENT, SD_ERR_STATE, SD_ERR_CLOCK, SD_ERR_GPIO,
    SD_ERR_VOLTAGE, SD_ERR_TIMER, SD_ERR_COMMAND_TIMEOUT, SD_ERR_COMMAND_CRC,
    SD_ERR_RESPONSE, SD_ERR_CARD, SD_ERR_UNSUPPORTED, SD_ERR_NOT_READY,
    SD_ERR_CAPACITY, SD_ERR_DATA, SD_ERR_DATA_TIMEOUT, SD_ERR_LENGTH,
    SD_ERR_CONTROLLER_BUSY, SD_ERR_DMA, SD_ERR_CACHE, SD_ERR_SECURITY, SD_ERR_WAIT
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
/* Zero-copy single-buffer IDMA write. This is a blocking completion API; camera
 * DMA/interrupts may produce later bytes concurrently, but every byte in this
 * request must already be complete and remain immutable until it returns.
 * The buffer must be word-aligned secure AXI SRAM (0x34000000..0x343fffff), with
 * D-cache disabled and no outstanding dirty cache aliases. The caller must set
 * SDMMC2's RIMC master (index 3) to secure/privileged CID1, mark its configuration
 * port secure (RISUP54, SECCFGR1 bit22), and enable the SRAM banks/RISAF access.
 * Otherwise its secure guard silently overrides MSEC and protected reads can
 * return zeros without an SD/IDMA error. Alignment/range, global cache state,
 * RIMC and secure guard are checked, never changed here; SRAM bank/policy setup
 * remains the caller's duty.
 * Requests are split at 1024 sectors (16 at 100 kHz). No NVIC, WFI, linked list,
 * bus-width change, cache enable, or filesystem operation is performed.
 * Success includes DATAEND, idle DPSM, CMD12 for multiblock, and fresh card ready.
 * Failure may leave IDMA armed if DPSM cannot be stopped: media_idle=0, and the
 * buffer must remain valid/immutable until ownership is explicitly recovered.
 */
int sd_write_blocks_dma(sd_card_t *card, uint32_t lba, const void *buffer, uint32_t count);
/* Opt-in pre-announced single CMD25 transaction. The complete immutable source
 * must already be present, including any caller-provided final-sector padding.
 * Accepts 2..4096 sectors at 12.5/25 MHz only; it never splits the request.
 * After fresh ready and all normal DMA checks: CMD55(RCA), ACMD23(exact count),
 * CMD25, CMD12, fresh ready. Both application responses must set APP_CMD and
 * be free of R1 errors. An unsupported/rejected announcement fails without
 * silently reverting to unannounced writes. No CMD23 fixed-count mode is used.
 * ACMD23 is a preparation hint, not a flush command or power-loss guarantee.
 * A failed/interrupted CMD25 can leave any announced but unwritten sectors
 * undefined, so the caller must own the entire announced range exclusively.
 * The existing DMA timeout, security, cache and ownership rules still apply.
 */
int sd_write_blocks_dma_preerase(sd_card_t *card, uint32_t lba,
                                 const void *buffer, uint32_t count);
typedef struct {
    uint32_t (*milliseconds)(void);
    uint32_t wait_calls, wall_ms, active_cycles, immediate_wakes;
    uint32_t context_faults;
} sd_dma_wait_t;
enum {
    SD_WAIT_NO_CLOCK=1U, SD_WAIT_EXCEPTION=2U, SD_WAIT_PRIMASK=4U,
    SD_WAIT_BASEPRI=8U, SD_WAIT_FAULTMASK=16U, SD_WAIT_DEEP_SLEEP=32U,
    SD_WAIT_SLEEP_ON_EXIT=64U, SD_WAIT_SYSTICK_CTRL=128U,
    SD_WAIT_SYSTICK_LOAD=256U, SD_WAIT_RAM_CLOCKS=512U,
    SD_WAIT_RIF_CLOCKS=1024U, SD_WAIT_SD_CLOCK=2048U,
    SD_WAIT_BUS_CLOCKS=4096U, SD_WAIT_DEBUG_ACCESS=8192U,
    SD_WAIT_DEBUG_SLEEP=16384U
};
/* Opt-in shallow WFI during the DMA data phase only. The caller owns a working
 * 1 ms SysTick handler and supplies its monotonic counter (e.g. HAL_GetTick).
 * The counter must keep advancing in Sleep, wrap as uint32_t, and take no SD
 * action. This driver does not install/modify interrupt handlers or clocks.
 * Before use, finish all camera operations whose deadlines depend on DWT.
 * Thread mode, unmasked interrupts, 400 MHz/1 ms SysTick, shallow sleep, and
 * SDMMC2/RIF/RAM/interconnect sleep clocks and disabled debug Sleep emulation
 * are checked. Invalid setup fails SD_ERR_WAIT
 * before issuing card writes; a changed setup during DMA triggers safe abort.
 * Counters accumulate across calls: wait_calls counts WFI instructions, not
 * proven sleep; immediate_wakes counts returns without a tick advance. wall_ms
 * and active_cycles cover the DMA phase including CMD24/25 launch. Existing
 * DWT counters exclude sleeping time and must not be interpreted as wall time.
 * context_faults accumulates SD_WAIT_* bits for refused contexts, including a
 * missing milliseconds callback; it never clears itself across calls.
 * Completion/timeout/error cleanup remains identical to the default DMA API.
 */
int sd_write_blocks_dma_wait(sd_card_t *card, uint32_t lba, const void *buffer,
                             uint32_t count, sd_dma_wait_t *wait);
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
 * never per FIFO word. The override must be bounded (at most 50 ms), and must not
 * change SD registers, its clocks/pins, buffer ownership, CPU clock/cache state,
 * or call back into this driver/filesystem (no reentrancy). It may service an
 * independent camera completion/STOP without violating those restrictions.
 * It must not sleep: the current deadlines use DWT, which can stop in sleep.
 */
void sd_progress(void);

#endif
