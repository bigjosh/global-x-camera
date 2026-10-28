#ifndef GLOBAL_X_SD_CARD_H
#define GLOBAL_X_SD_CARD_H

#include <stdint.h>

/* Explicit reviewed-driver opt-in. Historical builds retain their exact
 * executable paths until the new profile is independently qualified. */
#ifndef SD_REVIEW_PROFILE
#define SD_REVIEW_PROFILE 0
#endif
#if SD_REVIEW_PROFILE != 0 && SD_REVIEW_PROFILE != 1
#error "SD_REVIEW_PROFILE must be 0 or 1"
#endif
#ifndef SD_IDMA_READ
#define SD_IDMA_READ 0
#endif
#if SD_IDMA_READ != 0 && SD_IDMA_READ != 1
#error "SD_IDMA_READ must be 0 or 1"
#endif
#if SD_IDMA_READ && !SD_REVIEW_PROFILE
#error "IDMA reads require the explicit reviewed driver profile"
#endif
#ifndef SD_STARTUP_OPT
#define SD_STARTUP_OPT 0
#endif
#if SD_STARTUP_OPT != 0 && SD_STARTUP_OPT != 1
#error "SD_STARTUP_OPT must be 0 or 1"
#endif
#ifndef SD_EARLY_RUN_CLOCK
#define SD_EARLY_RUN_CLOCK 0
#endif
#if SD_EARLY_RUN_CLOCK != 0 && SD_EARLY_RUN_CLOCK != 1
#error "SD_EARLY_RUN_CLOCK must be 0 or 1"
#endif

#ifndef SD_HIGH_SPEED_COMBINED_ELECTRICAL
#define SD_HIGH_SPEED_COMBINED_ELECTRICAL 0
#endif
#if SD_HIGH_SPEED_COMBINED_ELECTRICAL != 0 && SD_HIGH_SPEED_COMBINED_ELECTRICAL != 1
#error "SD_HIGH_SPEED_COMBINED_ELECTRICAL must be 0 or 1"
#endif
#ifndef SD_HIGH_SPEED_FIXED_COMPENSATION
#define SD_HIGH_SPEED_FIXED_COMPENSATION 0
#endif
#if SD_HIGH_SPEED_FIXED_COMPENSATION != 0 && SD_HIGH_SPEED_FIXED_COMPENSATION != 1
#error "SD_HIGH_SPEED_FIXED_COMPENSATION must be 0 or 1"
#endif

/* Native SDMMC2, 3.3 V. Historical builds default to one bit. Four-bit builds
 * must explicitly define SD_BUS_WIDTH=4; init negotiates the card before changing
 * the host width. No card cache, UHS or trim commands are enabled.
 * Erase is an explicit opt-in API, never part of initialization.
 * All APIs are synchronous and require one owner.
 * The caller must place this object and its buffers outside the capture frame.
 * Zero-initialize the object before its first sd_init().
 */
#ifndef SD_BUS_WIDTH
#define SD_BUS_WIDTH 1
#endif
#if SD_BUS_WIDTH != 1 && SD_BUS_WIDTH != 4
#error "SD_BUS_WIDTH must be 1 or 4"
#endif
#if SD_STARTUP_OPT && (!SD_REVIEW_PROFILE || SD_BUS_WIDTH != 4)
#error "Startup optimization requires the reviewed four-bit profile"
#endif
#if SD_STARTUP_OPT
typedef struct {
    uint32_t magic,version,gpio_settle_cycles,train_cycles;
    uint32_t train_hz,train_min_cycles,run_settle_cycles,run_hz;
    uint32_t scr_reads,scr_hits,scr_valid,cache_owner;
    uint32_t result,reserved0,reserved1,reserved2;
} sd_startup_proof_t;
extern volatile sd_startup_proof_t sd_startup_proof;
#endif
#ifndef SD_GPIO_SPEED
#define SD_GPIO_SPEED 3
#endif
#if SD_GPIO_SPEED < 0 || SD_GPIO_SPEED > 3
#error "SD_GPIO_SPEED must be in 0..3"
#endif
#if (SD_GPIO_SPEED == 1 || SD_GPIO_SPEED == 2) && SD_BUS_WIDTH != 4
#error "Intermediate GPIO speed diagnostics require four-bit mode"
#endif
#ifndef SD_FIXED_COMPENSATION
#define SD_FIXED_COMPENSATION 0
#endif
#if SD_FIXED_COMPENSATION != 0 && SD_FIXED_COMPENSATION != 1
#error "SD_FIXED_COMPENSATION must be 0 or 1"
#endif
#if SD_FIXED_COMPENSATION && SD_GPIO_SPEED != 3
#error "Fixed compensation diagnostic requires unchanged GPIO speed 3"
#endif
#ifndef SD_CLOCK_NEGEDGE
#define SD_CLOCK_NEGEDGE 0
#endif
#if SD_CLOCK_NEGEDGE != 0 && SD_CLOCK_NEGEDGE != 1
#error "SD_CLOCK_NEGEDGE must be 0 or 1"
#endif
#if SD_CLOCK_NEGEDGE && (SD_BUS_WIDTH != 4 || SD_GPIO_SPEED == 0 || (SD_FIXED_COMPENSATION && !SD_HIGH_SPEED_FIXED_COMPENSATION))
#error "Clock phase diagnostic requires four bits, speed 1..3 and unchanged compensation"
#endif
#ifndef SD_CLOCK_NEGEDGE_INIT
#define SD_CLOCK_NEGEDGE_INIT 0
#endif
#if SD_CLOCK_NEGEDGE_INIT != 0 && SD_CLOCK_NEGEDGE_INIT != 1
#error "SD_CLOCK_NEGEDGE_INIT must be 0 or 1"
#endif
#if SD_CLOCK_NEGEDGE_INIT && (!SD_CLOCK_NEGEDGE || SD_GPIO_SPEED != 3)
#error "Initial falling-edge launch requires run falling-edge launch and GPIO speed3"
#endif
#ifndef SD_HIGH_SPEED
#define SD_HIGH_SPEED 0
#endif
#if SD_HIGH_SPEED != 0 && SD_HIGH_SPEED != 1
#error "SD_HIGH_SPEED must be 0 or 1"
#endif
#if SD_HIGH_SPEED && (!SD_REVIEW_PROFILE || !SD_CLOCK_NEGEDGE_INIT || SD_BUS_WIDTH != 4 || SD_GPIO_SPEED != 3 || (SD_FIXED_COMPENSATION && !SD_HIGH_SPEED_FIXED_COMPENSATION))
#error "High-speed profile requires reviewed four-bit falling-edge mode with the dedicated pin profile"
#endif
#ifndef SD_HIGH_SPEED_MIXED_SLEW
#define SD_HIGH_SPEED_MIXED_SLEW 0
#endif
#if SD_HIGH_SPEED_MIXED_SLEW != 0 && SD_HIGH_SPEED_MIXED_SLEW != 1
#error "SD_HIGH_SPEED_MIXED_SLEW must be 0 or 1"
#endif
#if SD_HIGH_SPEED_MIXED_SLEW && (!SD_HIGH_SPEED || !SD_REVIEW_PROFILE || SD_GPIO_SPEED != 3 || (SD_FIXED_COMPENSATION && !SD_HIGH_SPEED_COMBINED_ELECTRICAL))
#error "Mixed slew requires the isolated reviewed High Speed profile and unchanged compensation"
#endif
#if SD_HIGH_SPEED_FIXED_COMPENSATION && (!SD_HIGH_SPEED || !SD_FIXED_COMPENSATION || (SD_HIGH_SPEED_MIXED_SLEW && !SD_HIGH_SPEED_COMBINED_ELECTRICAL))
#error "High Speed fixed compensation requires isolated uniform-slew High Speed mode"
#endif
#if SD_HIGH_SPEED_COMBINED_ELECTRICAL && (!SD_HIGH_SPEED_MIXED_SLEW || !SD_HIGH_SPEED_FIXED_COMPENSATION)
#error "Combined electrical trial requires both explicit High Speed experiments"
#endif
#if SD_EARLY_RUN_CLOCK && (!SD_REVIEW_PROFILE || !SD_STARTUP_OPT || SD_BUS_WIDTH != 4 || !SD_CLOCK_NEGEDGE_INIT || SD_HIGH_SPEED || SD_IDMA_READ || SD_GPIO_SPEED != 3 || SD_FIXED_COMPENSATION)
#error "Early run clock requires the isolated reviewed startup Default-Speed profile"
#endif
#if SD_EARLY_RUN_CLOCK
/* ECK1: retained across deinit; reset only by a fresh admitted init. Counts
 * prove that the idle clock change follows CMD9 and precedes CMD7. Timestamps
 * use the caller's 400 MHz DWT domain and require modulo-32-bit subtraction.
 * This record is evidence, never a substitute for live storage ownership. */
typedef struct {
    uint32_t magic,version,requested_hz,csd_tran_speed;
    uint32_t csd_max_hz,csd_command_count,switch_command_count,select_command_count;
    uint32_t clock_before,clock_after,timer_before,timer_after;
    uint32_t switch_begin_cycles,switch_end_cycles,select_begin_cycles,result;
} sd_early_clock_proof_t;
extern volatile sd_early_clock_proof_t sd_early_clock_proof;
#endif
#if SD_HIGH_SPEED
typedef struct {
    uint32_t requested_hz, kernel_hz, check_done, switch_done;
    uint32_t check_r1, switch_r1, check_sta, switch_sta;
    uint32_t configured_clkcr, qualified;
    uint32_t gpio_c_before, gpio_c_after, gpio_e_before, gpio_e_after;
    uint8_t check_status[64], switch_status[64];
} sd_high_speed_proof_t;
extern volatile sd_high_speed_proof_t sd_high_speed_proof;
#endif
#if SD_FIXED_COMPENSATION
typedef struct {
    uint32_t clock_before, clock_after, reset, svmcr2, svmcr3;
    uint32_t before, after, applied;
} sd_compensation_proof_t;
extern volatile sd_compensation_proof_t sd_compensation_proof;
#endif
#if SD_GPIO_SPEED != 3
/* Diagnostic-only proof, separate from sd_card_t and absent in default builds.
 * Captured after pin configuration and before sd_init() returns; retained on
 * deinit. This does not inspect or change I/O compensation configuration. */
typedef struct {
    uint32_t requested_speed, c_mask, c_before, c_after;
    uint32_t e_mask, e_before, e_after, applied;
} sd_gpio_proof_t;
extern volatile sd_gpio_proof_t sd_gpio_proof;
#endif
#if SD_BUS_WIDTH == 4
/* Separate debugger evidence, preserving sd_card_t's existing ABI. Reset at
 * fresh init, retained through deinit. negotiated_width becomes4 only after
 * accepted ACMD6, host-width readback and final fresh READY/TRANSFER proof. */
typedef struct {
    uint32_t requested_width, scr_widths, acmd6_r1, acmd6_accepted;
    uint32_t configured_clkcr, negotiated_width;
} sd_width_proof_t;
extern volatile sd_width_proof_t sd_bus_width_proof;
#endif
#define SD_SECTOR_BYTES 512U
#define SD_MAX_TRANSFER_SECTORS 64U
#define SD_DMA_MAX_TRANSFER_SECTORS 1024U
#define SD_DMA_PREERASE_MAX_SECTORS 4096U

enum sd_error {
    SD_OK=0, SD_ERR_ARGUMENT, SD_ERR_STATE, SD_ERR_CLOCK, SD_ERR_GPIO,
    SD_ERR_VOLTAGE, SD_ERR_TIMER, SD_ERR_COMMAND_TIMEOUT, SD_ERR_COMMAND_CRC,
    SD_ERR_RESPONSE, SD_ERR_CARD, SD_ERR_UNSUPPORTED, SD_ERR_NOT_READY,
    SD_ERR_CAPACITY, SD_ERR_DATA, SD_ERR_DATA_TIMEOUT, SD_ERR_LENGTH,
    SD_ERR_CONTROLLER_BUSY, SD_ERR_DMA, SD_ERR_CACHE, SD_ERR_SECURITY, SD_ERR_WAIT,
    SD_ERR_PRODUCER
};

enum sd_stage {
    SD_STAGE_NONE=0, SD_STAGE_PREFLIGHT, SD_STAGE_GPIO, SD_STAGE_IDENTIFY,
    SD_STAGE_SELECT, SD_STAGE_READ, SD_STAGE_WRITE, SD_STAGE_SYNC,
    SD_STAGE_ABORT, SD_STAGE_DEINIT, SD_STAGE_SCR, SD_STAGE_ERASE,
    SD_STAGE_BUS_WIDTH, SD_STAGE_SWITCH
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
/* SD_IDMA_READ selects a RAM diagnostic receive path for this same API.
 * Its destination must be word-aligned secure AXI SRAM, D-cache disabled,
 * with the same RIFSC security prerequisites as DMA writes below. The caller
 * owns the entire destination until completion or proven abort; it must not
 * overlap live code, proofs or the original image retained for comparison.
 * Requests split at 512 sectors (16 at 100 kHz), retaining HWFC, CRC checks,
 * CMD12 and fresh readiness. No CPU FIFO access, WFI or interrupts are used.
 * Failure can leave DMA ownership active; a failure is never valid image data.
 */
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
    uint8_t bytes[8]; /* SCR wire order: bytes[0] holds bits63..56. */
    uint32_t valid, erased_byte; /* DATA_STAT_AFTER_ERASE: 0x00 or0xFF. */
} sd_scr_t;
/* Explicit readonly ACMD51. This does not alter sd_card_t. Four-bit init also
 * reads SCR internally before width negotiation; one-bit init does not.
 * Success validates SCR_STRUCTURE=0 and decodes bit55 from bytes[1]. */
int sd_read_scr(sd_card_t *card, sd_scr_t *scr);
#if SD_STARTUP_OPT
/* Startup profile reuses a validated SCR only within the current successful
 * initialization. Any driver fault, deinit or new init invalidates it. The
 * caller must reinitialize after card replacement; no card-detect is inferred.
 * This explicit diagnostic always performs a new wire read instead. */
int sd_read_scr_fresh(sd_card_t *card, sd_scr_t *scr);
#endif
typedef struct {
    uint32_t started, completed, first_lba, last_lba;
    uint32_t timeout_ms, elapsed_ms, last_r1, command_count;
} sd_erase_t;
/* DESTRUCTIVE explicit full-card CMD32/CMD33/CMD38 erase. Never called by init.
 * The caller authorizes loss of all card contents. timeout_ms=1000..600000;
 * polls busy with a wrap-safe extended DWT clock and sd_progress(). Timeout
 * leaves media_idle=0: it is not permission to reset/power off a busy erase.
 * While idle, selects the known 100 kHz bus clock and programs DTIMER for the
 * requested timeout plus 1 s, covering R1b busy independently of prior reads.
 * Restores the original supported clock/timer only after fresh card/host idle;
 * an uncertain error leaves the 100 kHz clock and controller ownership intact.
 * The observed erased read value is separately obtained with sd_read_scr(). */
int sd_erase_all(sd_card_t *card, uint32_t timeout_ms, sd_erase_t *proof);
typedef struct {
    /* Publish an immutable prefix. Return0 on success, nonzero on producer
     * failure. No SD reentry, sleep, or controller/clock/cache changes allowed.
     * Must be bounded and include the required producer-to-CPU memory barrier.
     * Bounded fault validation may take up to 3 seconds (e.g. camera stop/I2C
     * timeouts); ordinary calls should return promptly.
     * The API's 3-second producer deadline is checked AFTER every callback,
     * before accepting new bytes. Expiry before CMD25 makes no card write;
     * expiry during CMD25 aborts through the normal idle-proof cleanup.
     * All bytes, including end magic and padding, must be validated before
     * publishing the full extent. Unpublished memory is never read. */
    int (*publish)(void *context, uint32_t *available_bytes);
    void *context;
    uint32_t mode, initial_available_bytes, published_bytes, queued_bytes;
    uint32_t publication_calls, starved_polls, producer_error;
    uint32_t producer_wait_cycles, max_wait_cycles;
} sd_stream_t;
enum { SD_STREAM_NONE=0U, SD_STREAM_IDMA=1U, SD_STREAM_PIO=2U };
/* One ACMD23+CMD25; accepts the same range/security/clock rules as preerase.
 * Waits for at least one complete sector before announcement. If the initial
 * publication covers the full transfer, uses the existing IDMA fast path.
 * Otherwise PIO feeds only complete published sectors; HWFC_EN stalls SDMMC_CK
 * when FIFO data runs out (RM0486 30.7.1). IDMA cannot safely pause on a missing
 * linked-list node: ABR=0 is an error, not producer backpressure.
 * Producer must finish within3s of API entry; data phase has the existing5s
 * bound. No source copying, speculative reads, linked list or WFI is used.
 * On success mode/queued_bytes identify how the transaction was fed. */
int sd_write_blocks_stream_preerase(sd_card_t *card, uint32_t lba,
                                    const void *buffer, uint32_t count,
                                    sd_stream_t *stream);
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
 * Leaves CLK input/pull-down and CMD/used DAT pins input/pull-up while powered.
 * The one-bit build also retains the unused DAT3 input/pull-up.
 * GPIO/PWR clocks and VDDIO5 supply-valid remain enabled for other users.
 */
int sd_deinit(sd_card_t *card);

/* Optional monotonic-clock service hook. The weak default is empty. A caller
 * may override it to extend DWT's 32-bit count while long filesystem operations
 * run. Calls occur at command/chunk boundaries and throughout bounded waits,
 * never per FIFO word. Healthy service should finish within 50 ms. A bounded
 * camera fault path may take roughly 2 seconds for sequential pipe/VC stop
 * waits plus an I2C timeout, up to 3 seconds total. It must latch the fault and
 * return to the SD owner, never park or perform failure cleanup from the hook.
 * Consumers must account for that blocking interval and recheck deadlines
 * after service before using newly published data; a deadline cannot interrupt
 * a callback. The stream API checks its deadline before accepting publication.
 * The override must not
 * change SD registers, its clocks/pins, buffer ownership, CPU clock/cache state,
 * or call back into this driver/filesystem (no reentrancy). It may service an
 * independent camera completion/STOP without violating those restrictions.
 * It must not sleep: the current deadlines use DWT, which can stop in sleep.
 */
void sd_progress(void);

#endif
