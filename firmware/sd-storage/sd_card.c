/* CMSIS-only native SDMMC2 storage driver, derived from the qualified read-only
 * smoke helper. PC2/3/4 AF11 = CLK/CMD/DAT0. Optional four-bit builds add
 * PC5/PC0/PE4 AF11 = DAT1/DAT2/DAT3; one-bit builds leave PE4 input/pull-up.
 *
 * Sources: RM0486 Rev4 Table220 and section30.6.2; pinned CubeN6 HAL_SD_ReadBlocks,
 * HAL_SD_WriteBlocks and LL SDMMC_CmdStopTransfer. Open-ended CMD18/CMD25 use
 * DATAEND followed by CMD12/CMDSTOP, then an explicit ready/TRANSFER check.
 *
 * The opt-in single-buffer IDMA API accepts secure AXI SRAM only. No HAL library dependency, interrupt configuration,
 * CPU/PLL/NOR clock changes, card power switching, or filesystem operations.
 * All errors are bounded; an unverified abort leaves media_idle=0 and the host
 * powered. The caller must not treat that case as permission to cut power.
 */
#include "sd_card.h"
#include <stddef.h>
#include "stm32n657xx.h"

/* Opt-in diagnostic builds only. The default driver has no trace dependency
 * and no extra instructions; marks are fixed stores, never FIFO/poll logging.
 * The capture owner initializes the RAM record after enabling its SRAM bank. */
#ifndef RAW_CYCLE_TRACE
#define RAW_CYCLE_TRACE 0
#endif
#if RAW_CYCLE_TRACE
#include "cycle_trace.h"
#else
#define CYCLE_MARK(name) ((void)0)
#define CYCLE_COUNT(name) ((void)0)
#endif

#define X SDMMC2_S
#define R RCC_S
#define C GPIOC_S
#define E GPIOE_S
#define P PWR_S
#define CPU_CYCLES_US 400UL
#define HCLK_HZ 150000000UL
#if SD_HIGH_SPEED
#define SD_KERNEL_HZ 100000000UL
#include "sd_clock_profile.h"
#else
#define SD_KERNEL_HZ HCLK_HZ
#endif
#define CMD_TIMEOUT_CYCLES 100000000UL  /* 250 ms */
#define READY_TIMEOUT_CYCLES 800000000UL /* 2 s */
#define READ_TIMEOUT_CYCLES 800000000UL
#define WRITE_TIMEOUT_CYCLES 2000000000UL /* 5 s, below CYCCNT wrap */
#define POLL_LIMIT 120000000UL
#define CMD_FLAGS (SDMMC_STA_CCRCFAIL|SDMMC_STA_CTIMEOUT|SDMMC_STA_CMDREND|SDMMC_STA_CMDSENT|SDMMC_STA_BUSYD0END)
#define DATA_ERRORS (SDMMC_STA_DCRCFAIL|SDMMC_STA_DTIMEOUT|SDMMC_STA_RXOVERR|SDMMC_STA_TXUNDERR)
#define DATA_FLAGS (DATA_ERRORS|SDMMC_STA_DATAEND|SDMMC_STA_DBCKEND|SDMMC_STA_DABORT|SDMMC_STA_BUSYD0END)
#define DMA_ERRORS (DATA_ERRORS|SDMMC_STA_IDMATE)
#define DMA_FLAGS (DATA_FLAGS|SDMMC_STA_IDMATE|SDMMC_STA_IDMABTC)
#define R1_ERRORS 0xFDFFE008UL
#define DAT0 (1UL<<4)
#if SD_CLOCK_NEGEDGE
#define PHASE_BITS SDMMC_CLKCR_NEGEDGE
#else
#define PHASE_BITS 0UL
#endif
/* Default-Speed initialization uses the requested falling launch. At 50 MHz,
 * the High-Speed datasheet output delay is referenced to rising SDCLK:
 * NEGEDGE=0 launches on the following 100 MHz kernel falling edge (~5 ns). */
#define INIT_PHASE_BITS PHASE_BITS
#if SD_HIGH_SPEED
#define RUN_PHASE_BITS 0UL
#define RUN_PHASE_MASK SDMMC_CLKCR_NEGEDGE
#else
#define RUN_PHASE_BITS PHASE_BITS
#define RUN_PHASE_MASK PHASE_BITS
#endif
#if SD_BUS_WIDTH == 4
#define C_MASK ((3UL<<0)|(3UL<<4)|(3UL<<6)|(3UL<<8)|(3UL<<10))
#define C_PINS ((1UL<<0)|(1UL<<2)|(1UL<<3)|(1UL<<4)|(1UL<<5))
#define C_PULLS ((1UL<<0)|(1UL<<6)|(1UL<<8)|(1UL<<10))
#define C_MODES ((2UL<<0)|(2UL<<4)|(2UL<<6)|(2UL<<8)|(2UL<<10))
#define C_AF_MASK ((15UL<<0)|(0xFFFFUL<<8))
#define C_AF_BITS ((11UL<<0)|(0xBBBBUL<<8))
#define C_IDLE_PINS ((1UL<<0)|(1UL<<3)|(1UL<<4)|(1UL<<5))
#define WIDTH_BITS SDMMC_CLKCR_WIDBUS_0
#else
#define C_MASK ((3UL<<4)|(3UL<<6)|(3UL<<8))
#define C_PINS ((1UL<<2)|(1UL<<3)|(1UL<<4))
#define C_PULLS ((1UL<<6)|(1UL<<8))
#define C_MODES ((2UL<<4)|(2UL<<6)|(2UL<<8))
#define C_AF_MASK (0xFFFUL<<8)
#define C_AF_BITS (0xBBBUL<<8)
#define C_IDLE_PINS ((1UL<<3)|DAT0)
#define WIDTH_BITS 0UL
#endif

_Static_assert(SDMMC2_BASE_S==0x58026800UL, "SDMMC2 address");
_Static_assert(offsetof(SDMMC_TypeDef,FIFO)==0x80, "FIFO offset");
_Static_assert(SD_MAX_TRANSFER_SECTORS*SD_SECTOR_BYTES<=0x1FFFFFFUL, "DLEN");
_Static_assert(SD_DMA_MAX_TRANSFER_SECTORS*SD_SECTOR_BYTES<=0x1FFFFFFUL, "IDMA DLEN");
_Static_assert(SD_DMA_PREERASE_MAX_SECTORS*SD_SECTOR_BYTES<=0x1FFFFFFUL, "preerase IDMA DLEN");

enum response { RESP_NONE, RESP_R1, RESP_R2, RESP_R3, RESP_R6, RESP_R7 };

#if SD_BUS_WIDTH == 4
static int read_scr_selected(sd_card_t *c,sd_scr_t *scr);
volatile sd_width_proof_t sd_bus_width_proof;
_Static_assert(sizeof(sd_width_proof_t)==24U,"bus-width proof ABI");
#endif
#if SD_HIGH_SPEED
volatile sd_high_speed_proof_t sd_high_speed_proof;
_Static_assert(sizeof(sd_high_speed_proof_t)==184U,"high-speed proof ABI");
#endif

#if SD_GPIO_SPEED != 3
volatile sd_gpio_proof_t sd_gpio_proof;
_Static_assert(sizeof(sd_gpio_proof_t)==32U,"GPIO speed proof ABI");
#endif
#if SD_FIXED_COMPENSATION
volatile sd_compensation_proof_t sd_compensation_proof;
_Static_assert(sizeof(sd_compensation_proof_t)==32U,"compensation proof ABI");
#endif
#if SD_STARTUP_OPT
volatile sd_startup_proof_t sd_startup_proof;
_Static_assert(sizeof(sd_startup_proof_t)==64U,"startup proof ABI");
static sd_scr_t startup_scr;
static sd_card_t *startup_scr_owner;
static void startup_scr_invalidate(void)
{
    startup_scr.valid=0; startup_scr_owner=NULL;
    sd_startup_proof.scr_valid=0; sd_startup_proof.cache_owner=0;
}
#endif

#if SD_EARLY_RUN_CLOCK
volatile sd_early_clock_proof_t sd_early_clock_proof;
_Static_assert(sizeof(sd_early_clock_proof_t)==64U,"early clock proof ABI");
#endif

__attribute__((weak)) void sd_progress(void)
{
}

static int fault(sd_card_t *c, uint32_t error)
{
#if SD_EARLY_RUN_CLOCK
    if(!sd_early_clock_proof.result) sd_early_clock_proof.result=error;
#endif
#if SD_STARTUP_OPT
    startup_scr_invalidate();
    if(!sd_startup_proof.result) sd_startup_proof.result=error;
#endif
    CYCLE_MARK(SD_LAST_ERROR);
    CYCLE_COUNT(SD_ERROR_CALLS);
    if (!c->error) {
        c->error=error;
        c->error_stage=c->stage;
        c->error_command=c->last_command;
        c->error_sta=c->last_sta;
    }
    return (int)error;
}

#if SD_HIGH_SPEED
static int high_speed_host_guard(sd_card_t *c)
{
    if (!(R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) || !sd_review_clock_proof.owned ||
            (R->CCIPR8&RCC_CCIPR8_SDMMC2SEL)!=SD_REVIEW_MUX_BITS ||
            !(R->DIVENR&RCC_DIVENR_IC5EN) ||
            (R->IC5CFGR&SD_REVIEW_IC5_MASK)!=SD_REVIEW_IC5_BITS ||
            !sd_review_clock_sources()) return fault(c,SD_ERR_CLOCK);
    uint32_t phase=(sd_high_speed_proof.qualified || c->clock_hz==50000000U)?RUN_PHASE_BITS:INIT_PHASE_BITS;
    if ((c->clock_hz!=100000U && c->clock_hz!=25000000U && c->clock_hz!=50000000U) ||
            SD_KERNEL_HZ%(2U*c->clock_hz) ||
            X->CLKCR!=((SD_KERNEL_HZ/(2U*c->clock_hz))|SDMMC_CLKCR_HWFC_EN|
                ((sd_bus_width_proof.configured_clkcr&SDMMC_CLKCR_WIDBUS)==WIDTH_BITS?WIDTH_BITS:0U)|phase))
        return fault(c,SD_ERR_CLOCK);
    return SD_OK;
}
#define SD_HOST_GUARD(card) do {int guard=high_speed_host_guard(card);if(guard)return guard;} while(0)
#elif SD_STARTUP_OPT
#define SD_HOST_GUARD(card) do {if(!(R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN))return fault(card,SD_ERR_CLOCK);} while(0)
#else
#define SD_HOST_GUARD(card) ((void)0)
#endif

static int delay_us(sd_card_t *c, uint32_t us)
{
    sd_progress();
    uint32_t start=DWT->CYCCNT;
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        if ((uint32_t)(DWT->CYCCNT-start)>=us*CPU_CYCLES_US) {
            sd_progress();
            return SD_OK;
        }
        if (!(i&4095UL)) sd_progress();
    }
    sd_progress();
    return fault(c,SD_ERR_TIMER);
}

static void sample_response(sd_card_t *c, uint32_t sta)
{
    c->last_sta=sta;
    c->last_r1=X->RESP1;
    c->command_count++;
}

#if SD_REVIEW_PROFILE
static int command_checked(sd_card_t *c, uint32_t index, uint32_t argument,
                           enum response response, uint32_t data,
                           uint32_t completed_read_at_media_end)
#else
static int command(sd_card_t *c, uint32_t index, uint32_t argument,
                   enum response response, uint32_t data)
#endif
{
    sd_progress();
    uint32_t start=DWT->CYCCNT, sta=0;
    c->last_command=index;
    c->last_argument=argument;
    if (X->STA&SDMMC_STA_CPSMACT) return fault(c,SD_ERR_CONTROLLER_BUSY);
    X->ICR=CMD_FLAGS;
    X->ARG=argument;
    X->CMD=index|SDMMC_CMD_CPSMEN|(data ? SDMMC_CMD_CMDTRANS : 0)|
        (index==12 ? SDMMC_CMD_CMDSTOP : 0)|
        (response==RESP_NONE ? 0 :
         response==RESP_R2 ? SDMMC_CMD_WAITRESP : SDMMC_CMD_WAITRESP_0);
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        sta=X->STA;
        uint32_t terminal=response==RESP_NONE ? SDMMC_STA_CMDSENT :
            SDMMC_STA_CMDREND|SDMMC_STA_CCRCFAIL|SDMMC_STA_CTIMEOUT;
        if ((sta&terminal) && !(sta&SDMMC_STA_CPSMACT)) break;
        if ((uint32_t)(DWT->CYCCNT-start)>=CMD_TIMEOUT_CYCLES) {
            sample_response(c,sta);
            return fault(c,SD_ERR_COMMAND_TIMEOUT);
        }
        if (i==POLL_LIMIT-1) {
            sample_response(c,sta);
            return fault(c,SD_ERR_TIMER);
        }
        if (!(i&4095UL)) sd_progress();
    }
    sample_response(c,sta);
    X->ICR=CMD_FLAGS;
    if (index==12) {
        c->last_stop_r1=X->RESP1;
        X->CMD&=~SDMMC_CMD_CMDSTOP;
    }
    if (sta&SDMMC_STA_CTIMEOUT) return fault(c,SD_ERR_COMMAND_TIMEOUT);
    if ((sta&SDMMC_STA_CCRCFAIL) && response!=RESP_R3)
        return fault(c,SD_ERR_COMMAND_CRC);
    if ((response==RESP_R1 || response==RESP_R6 || response==RESP_R7) &&
        (X->RESPCMD&63UL)!=index) return fault(c,SD_ERR_RESPONSE);
    uint32_t errors=R1_ERRORS;
    /* As in ST's LL stop helper: the card may flag the address beyond its last
     * sector while an open-ended read is being stopped at the end of media. */
#if SD_REVIEW_PROFILE
    /* Only a complete, CRC-good read whose owned extent ends at the last
     * sector may excuse an extra open-ended read address. A write or failed
     * read must never hide the card's OUT_OF_RANGE status. */
    if (index==12 && completed_read_at_media_end) errors&=~(1UL<<31);
#else
    if (index==12) errors&=~(1UL<<31);
#endif
    if (response==RESP_R1 && (X->RESP1&errors)) return fault(c,SD_ERR_CARD);
    if (response==RESP_R6 && (X->RESP1&0xE000UL)) return fault(c,SD_ERR_CARD);
    return SD_OK;
}

#if SD_REVIEW_PROFILE
static int command(sd_card_t *c, uint32_t index, uint32_t argument,
                   enum response response, uint32_t data)
{
    return command_checked(c,index,argument,response,data,0);
}
#endif

static int ready(sd_card_t *c)
{
    sd_progress();
    uint32_t start=DWT->CYCCNT;
    c->media_idle=0;
    for (uint32_t i=0;i<2000;++i) {
        sd_progress();
        int result=command(c,13,c->rca,RESP_R1,0);
        if (result) {
            c->ready_cycles+=(uint32_t)(DWT->CYCCNT-start);
            return result;
        }
        c->last_ready_r1=X->RESP1;
        c->gpioc_idr=C->IDR;
        if ((c->last_ready_r1&0x1F00UL)==0x900UL &&
            (c->gpioc_idr&DAT0) &&
            !(X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) &&
            !(X->IDMACTRL&SDMMC_IDMA_IDMAEN)) {
            c->media_idle=1;
            c->ready_cycles+=(uint32_t)(DWT->CYCCNT-start);
            return SD_OK;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=READY_TIMEOUT_CYCLES) break;
        result=delay_us(c,1000);
        if (result) return result;
    }
    c->ready_cycles+=(uint32_t)(DWT->CYCCNT-start);
    return fault(c,SD_ERR_NOT_READY);
}

#if SD_REVIEW_PROFILE
static int ready_after_transfer(sd_card_t *c)
{
    int result=ready(c);
    if (result) return result;
    /* R1b after CMD12 can expose a late timeout or data error. CMD13 does
     * not clear these sticky flags, so inspect them before cleanup clears
     * DATA_FLAGS. DABORT alone is expected from our deliberate CMD12 only
     * after the caller has proved DATAEND, full length and no earlier error. */
    uint32_t sta=X->STA;
    if (sta&DMA_ERRORS) {
        c->last_sta=sta;
        return fault(c,(sta&SDMMC_STA_IDMATE)?SD_ERR_DMA:SD_ERR_DATA);
    }
    return SD_OK;
}
#endif

/* Error recovery does not report the original operation as successful. It only
 * attempts to establish a quiescent device. RM0486 section 30.6.2 permits CMD12
 * to abort all data read/write commands. After CMDREND, drain receive data and
 * flush the FIFO while DPSMACT is still set; FIFORST is not writable when idle.
 */
static void abort_transfer(sd_card_t *c, uint32_t reading)
{
    uint32_t saved_stage=c->stage, start=DWT->CYCCNT;
    c->stage=SD_STAGE_ABORT;
    c->media_idle=0;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    int result=command(c,12,0,RESP_R1,0);
    /* A naturally completed single-block transfer may not respond to CMD12.
     * Do not infer idle from that timeout: check the host and CMD13 below. */
    if (result && result!=SD_ERR_COMMAND_TIMEOUT) {
        c->cleanup_error=(uint32_t)result;
        c->stage=saved_stage;
        return;
    }
    if (!result) {
        if (reading) {
            /* A stopped transfer has at most the remaining FIFO contents.
             * The finite word bound also prevents a faulty model/peripheral
             * from turning error cleanup into another unbounded read. */
#if SD_REVIEW_PROFILE
            /* RM0486 30.6.2: after CMDREND the remaining receive FIFO must
             * be drained before FIFORST. N6's FIFO holds 256 words, not64.
             * No further card data enters after this completed CMD12. */
            const uint32_t drain_words=256U;
#else
            const uint32_t drain_words=64U;
#endif
            for (uint32_t n=0;n<drain_words;++n) {
                uint32_t sta=X->STA;
                if (!(sta&SDMMC_STA_DPSMACT) || (sta&SDMMC_STA_RXFIFOE)) break;
                uint32_t discarded=X->FIFO;
                (void)discarded;
            }
            if ((X->STA&SDMMC_STA_DPSMACT) && !(X->STA&SDMMC_STA_RXFIFOE)) {
                c->cleanup_error=SD_ERR_LENGTH;
                c->stage=saved_stage;
                return;
            }
        }
        /* FIFORST is legal only with IDMA off and DPSM active (RM p1439).
         * It clears pending FIFO contents so the abort can reach DABORT/idle. */
        if (X->STA&SDMMC_STA_DPSMACT) X->DCTRL|=SDMMC_DCTRL_FIFORST;
    }
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        uint32_t sta=X->STA;
        if (!(sta&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))) {
            X->DCTRL=0;
            X->ICR=DATA_FLAGS;
            c->cleanup_error=(uint32_t)ready(c);
            c->stage=saved_stage;
            return;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=READY_TIMEOUT_CYCLES) break;
    }
    c->cleanup_error=SD_ERR_NOT_READY;
    c->stage=saved_stage;
}

static uint32_t load_word(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
        ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}

static void store_word(uint8_t *p, uint32_t v)
{
    p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8);
    p[2]=(uint8_t)(v>>16); p[3]=(uint8_t)(v>>24);
}

static int transfer(sd_card_t *c, uint32_t lba, uint8_t *buffer,
                    uint32_t count, uint32_t writing)
{
#if RAW_CYCLE_TRACE
    if (!writing) { CYCLE_MARK(SD_READ_LATEST_BEGIN); CYCLE_COUNT(SD_READ_TRANSFERS); }
#endif
    int result=ready(c);
    if (result) return result;
    uint32_t start=DWT->CYCCNT, words=0, total=count*128UL, sta=0;
    uint32_t timeout=writing ? WRITE_TIMEOUT_CYCLES : READ_TIMEOUT_CYCLES;
    c->media_idle=0;
    c->transfer_words=0;
    c->transfer_sta=0;
    X->DCTRL=0; X->ICR=DATA_FLAGS;
    X->DTIMER=c->clock_hz*2UL; /* Hardware wait/busy bound, plus whole-transfer DWT bound. */
    X->DLEN=count*SD_SECTOR_BYTES;
    X->DCTRL=(9UL<<SDMMC_DCTRL_DBLOCKSIZE_Pos)|
        (writing ? 0 : SDMMC_DCTRL_DTDIR);
    uint32_t index=writing ? (count==1 ? 24UL : 25UL) : (count==1 ? 17UL : 18UL);
#if RAW_CYCLE_TRACE
    if (!writing) CYCLE_MARK(SD_READ_CMD_BEGIN_LATEST);
#endif
    result=command(c,index,(c->ocr&(1UL<<30)) ? lba : lba*512UL,RESP_R1,1);
    if (result) {
        abort_transfer(c,!writing);
        return result;
    }
#if RAW_CYCLE_TRACE
    if (!writing) CYCLE_MARK(SD_READ_CMD_DONE_LATEST);
#endif
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        sta=X->STA;
        c->last_sta=sta;
        if (sta&DATA_ERRORS) { result=fault(c,SD_ERR_DATA); break; }
        /* Table220: DATAEND is final complete/CRC-good; TX also includes the
         * last block's busy completion. DBCKEND is not required at final end.
         * Do not read an inactive FIFO merely because RXFIFOE has deasserted. */
        if ((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) {
#if RAW_CYCLE_TRACE
            if (!writing) CYCLE_MARK(SD_READ_DATAEND_LATEST);
#endif
            break;
        }
        if (writing) {
            if ((sta&SDMMC_STA_TXFIFOHE) && words<total) {
                /* N6 has a 256-word FIFO. HALF-empty is a refill trigger,
                 * not permission to stop once half+1 full: BUSSPEED=0 waits
                 * for a full FIFO (or all DLEN bytes) before sending. A
                 * 16-word refill stalled at 144 words on multi-block writes.
                 * RM0486 pp1396-1398: fill until full or the last word.
                 * Bound one refill even if hardware drains concurrently. */
                for (uint32_t n=0;n<256UL && words<total;++n) {
                    uint32_t fifo_sta=X->STA;
                    if ((fifo_sta&(SDMMC_STA_TXFIFOF|DATA_ERRORS)) ||
                        !(fifo_sta&SDMMC_STA_DPSMACT)) break;
                    X->FIFO=load_word(buffer+4UL*words);
                    words++;
                }
            }
        } else if ((sta&SDMMC_STA_RXFIFOHF) && total-words>=16UL) {
            for (uint32_t n=0;n<16;++n) {
                store_word(buffer+4UL*words,X->FIFO);
                words++;
            }
        } else if (!(sta&SDMMC_STA_RXFIFOE) && words<total) {
            store_word(buffer+4UL*words,X->FIFO);
            words++;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=timeout) {
            result=fault(c,SD_ERR_DATA_TIMEOUT); break;
        }
        if (i==POLL_LIMIT-1) result=fault(c,SD_ERR_TIMER);
    }
    c->transfer_words=words; c->transfer_sta=sta;
    c->transfer_cycles=DWT->CYCCNT-start;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if (!result && (words!=total || !(sta&SDMMC_STA_DATAEND) ||
        (sta&(DATA_ERRORS|SDMMC_STA_DPSMACT)))) result=fault(c,SD_ERR_LENGTH);
    if (!result && count>1) {
#if SD_REVIEW_PROFILE
        result=command_checked(c,12,0,RESP_R1,0,
            !writing && (uint64_t)lba+count==c->sector_count);
#else
        result=command(c,12,0,RESP_R1,0);
#endif
    }
    if (result) {
        abort_transfer(c,!writing);
        return result;
    }
#if !SD_REVIEW_PROFILE
    X->DCTRL=0;
    X->ICR=DATA_FLAGS;
#endif
#if SD_REVIEW_PROFILE
    result=ready_after_transfer(c);
#else
    result=ready(c);
#endif
    if (result) return result;
#if SD_REVIEW_PROFILE
    /* CMD12's R1b busy can reactivate DPSM after DATAEND. DBLOCKSIZE,
     * DTDIR and DTMODE are only writable again after fresh idle proof. */
    X->DCTRL=0;
    X->ICR=DATA_FLAGS;
#endif
    if (writing) c->written_sectors+=count;
    else c->read_sectors+=count;
#if RAW_CYCLE_TRACE
    if (!writing) CYCLE_MARK(SD_READ_LATEST_DONE);
#endif
    return SD_OK;
}

/* With IDMA enabled, hardware owns FIFO draining/flushing during CMD12 abort
 * (RM0486 30.6.2). IDMAEN itself is writable only while DPSM is inactive. Do not
 * reuse the CPU FIFO abort, write FIFORST, or disable IDMA underneath active DMA.
 */
static void abort_dma_write(sd_card_t *c)
{
    uint32_t saved_stage=c->stage, start=DWT->CYCCNT;
    c->stage=SD_STAGE_ABORT;
    c->media_idle=0;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    int result=command(c,12,0,RESP_R1,0);
    if (result && result!=SD_ERR_COMMAND_TIMEOUT) {
        c->cleanup_error=(uint32_t)result;
        c->stage=saved_stage;
        return;
    }
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        uint32_t sta=X->STA;
        if (!(sta&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))) {
            X->IDMACTRL=0;
            __DSB();
            X->DCTRL=0;
            X->ICR=DMA_FLAGS;
            c->cleanup_error=(uint32_t)ready(c);
            c->stage=saved_stage;
            return;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=READY_TIMEOUT_CYCLES) break;
        if (!(i&255UL)) sd_progress();
    }
    c->cleanup_error=SD_ERR_NOT_READY;
    c->stage=saved_stage;
}

static uint32_t dma_wait_context(void)
{
    const uint32_t ram=RCC_MEMLPENR_AXISRAM1LPEN|RCC_MEMLPENR_AXISRAM2LPEN|
        RCC_MEMLPENR_AXISRAM3LPEN|RCC_MEMLPENR_AXISRAM4LPEN|
        RCC_MEMLPENR_AXISRAM5LPEN|RCC_MEMLPENR_AXISRAM6LPEN;
    const uint32_t rif=RCC_AHB3LPENR_RIFSCLPEN|RCC_AHB3LPENR_RISAFLPEN;
    const uint32_t bus=RCC_BUSLPENR_ACLKNLPEN|RCC_BUSLPENR_ACLKNCLPEN;
    const uint32_t tick=SysTick_CTRL_ENABLE_Msk|SysTick_CTRL_TICKINT_Msk|SysTick_CTRL_CLKSOURCE_Msk;
    uint32_t faults=0;
    if (__get_IPSR()) faults|=SD_WAIT_EXCEPTION;
    if (__get_PRIMASK()) faults|=SD_WAIT_PRIMASK;
    if (__get_BASEPRI()) faults|=SD_WAIT_BASEPRI;
    if (__get_FAULTMASK()) faults|=SD_WAIT_FAULTMASK;
    if (SCB->SCR&SCB_SCR_SLEEPDEEP_Msk) faults|=SD_WAIT_DEEP_SLEEP;
    if (SCB->SCR&SCB_SCR_SLEEPONEXIT_Msk) faults|=SD_WAIT_SLEEP_ON_EXIT;
    if ((SysTick->CTRL&tick)!=tick) faults|=SD_WAIT_SYSTICK_CTRL;
    if (SysTick->LOAD!=399999UL) faults|=SD_WAIT_SYSTICK_LOAD;
    if ((R->MEMLPENR&ram)!=ram) faults|=SD_WAIT_RAM_CLOCKS;
    if ((R->AHB3LPENR&rif)!=rif) faults|=SD_WAIT_RIF_CLOCKS;
    if (!(R->AHB5LPENR&RCC_AHB5LPENR_SDMMC2LPEN)) faults|=SD_WAIT_SD_CLOCK;
    /* RM0486 14.6.11: both NoC paths must remain available for AXISRAM3..6. */
    if ((R->BUSLPENR&bus)!=bus) faults|=SD_WAIT_BUS_CLOCKS;
    /* Never read a clock-gated/reset peripheral. Debug Sleep emulation keeps
     * CPU/peripheral clocks running (14.6.13), invalidating real-Sleep trials. */
    if (!(R->MISCENR&RCC_MISCENR_DBGEN) || (R->MISCRSTR&RCC_MISCRSTR_DBGRST))
        faults|=SD_WAIT_DEBUG_ACCESS;
    else if (DBGMCU_S->CR&DBGMCU_CR_DBG_SLEEP) faults|=SD_WAIT_DEBUG_SLEEP;
    return faults;
}

static int preannounce(sd_card_t *c,uint32_t count)
{
    CYCLE_MARK(SD_PREANNOUNCE_BEGIN);
    CYCLE_COUNT(SD_PREANNOUNCE_CALLS);
    int result=command(c,55,c->rca,RESP_R1,0);
    if(result) return result;
    if(!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    result=command(c,23,count,RESP_R1,0);
    if(result) return result;
    if(!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    CYCLE_MARK(SD_PREANNOUNCE_DONE);
    return SD_OK;
}

static int transfer_dma_write(sd_card_t *c, uint32_t lba,
                              const uint8_t *buffer, uint32_t count, sd_dma_wait_t *wait,
                              uint32_t preerase)
{
    CYCLE_COUNT(SD_WRITE_TRANSFERS);
    CYCLE_COUNT(SD_IDMA_TRANSFERS);
    CYCLE_MARK(SD_WRITE_READY_BEGIN);
    int result=ready(c);
    if (result) return result;
    CYCLE_MARK(SD_WRITE_READY_DONE);
    /* No second owner or abandoned DMA is allowed. All fields below are only
     * written after ready() has freshly observed an inactive host. */
    if (X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    uint32_t start=DWT->CYCCNT, sta=0;
    uint32_t wall_start=wait ? wait->milliseconds() : 0;
    c->media_idle=0;
    c->transfer_words=0;
    c->transfer_sta=0;
    if (preerase) {
        /* SD Physical Layer, APP_CMD and pre-erase write requirements:
         * APP_CMD must acknowledge both the
         * prefix and accepted ACMD. Announce exactly the exclusively owned
         * destination extent, then issue CMD25 next (no intervening CMD13).
         * ACMD23 does not terminate the write: CMD12 is still required. */
        if ((result=preannounce(c,count))) return result;
    }
    CYCLE_MARK(SD_WRITE_SETUP_BEGIN);
    X->DCTRL=0;
    X->ICR=DMA_FLAGS;
    X->DTIMER=c->clock_hz*2UL;
    X->DLEN=count*SD_SECTOR_BYTES;
    X->DCTRL=9UL<<SDMMC_DCTRL_DBLOCKSIZE_Pos;
    X->IDMABASER=(uint32_t)(uintptr_t)buffer;
    /* No CPU writes or dirty cache lines may remain unpublished before DMA. */
    __DSB();
    X->IDMACTRL=SDMMC_IDMA_IDMAEN;
#if RAW_CYCLE_TRACE
    if (count>1) { CYCLE_MARK(SD_CMD25_BEGIN); CYCLE_COUNT(SD_CMD25_CALLS); }
#endif
    result=command(c,count==1 ? 24UL : 25UL,
                   (c->ocr&(1UL<<30)) ? lba : lba*512UL,RESP_R1,1);
    if (!result) {
#if RAW_CYCLE_TRACE
        if (count>1) CYCLE_MARK(SD_CMD25_DONE);
#endif
        for (uint32_t i=0;i<POLL_LIMIT;++i) {
            sta=X->STA;
            c->last_sta=sta;
            /* IDMATE can accompany DATAEND, so errors have precedence. */
            if (sta&DMA_ERRORS) {
                result=fault(c,(sta&SDMMC_STA_IDMATE) ? SD_ERR_DMA : SD_ERR_DATA);
                break;
            }
            /* Single-buffer DATAEND means both the memory-side IDMA and DPSM
             * are complete (RM0486 p1402). It is not merely FIFO queued. */
            if ((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) {
                CYCLE_MARK(SD_DATAEND);
                break;
            }
            if ((wait && (uint32_t)(wait->milliseconds()-wall_start)>=5000UL) ||
                (uint32_t)(DWT->CYCCNT-start)>=WRITE_TIMEOUT_CYCLES) {
                result=fault(c,SD_ERR_DATA_TIMEOUT);
                break;
            }
            if (i==POLL_LIMIT-1) result=fault(c,SD_ERR_TIMER);
            if (wait) {
                sd_progress(); /* keep independent event servicing live */
                uint32_t context_faults=dma_wait_context();
                if (context_faults) {
                    wait->context_faults|=context_faults;
                    result=fault(c,SD_ERR_WAIT); break;
                }
                uint32_t before=wait->milliseconds();
                wait->wait_calls++; __DSB(); __WFI();
                if (wait->milliseconds()==before) wait->immediate_wakes++;
            } else if (!(i&255UL)) sd_progress();
        }
    }
    c->transfer_sta=sta;
    c->transfer_cycles=DWT->CYCCNT-start;
    if (wait) {
        wait->wall_ms+=(uint32_t)(wait->milliseconds()-wall_start);
        wait->active_cycles+=c->transfer_cycles;
    }
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if (!result && (!(sta&SDMMC_STA_DATAEND) ||
        (sta&(DMA_ERRORS|SDMMC_STA_DPSMACT)) || X->DCOUNT))
        result=fault(c,SD_ERR_LENGTH);
    if (result) {
        abort_dma_write(c);
        return result;
    }
    CYCLE_MARK(SD_WRITE_CLEANUP_BEGIN);
    /* DPSM is inactive: release DMA ownership before any subsequent command. */
    X->IDMACTRL=0;
    __DSB();
    CYCLE_MARK(SD_IDMA_RELEASED);
    c->transfer_words=count*128UL;
    if (count>1) {
        CYCLE_MARK(SD_CMD12_BEGIN);
        CYCLE_COUNT(SD_CMD12_WRITE_CALLS);
        result=command(c,12,0,RESP_R1,0);
        if (!result) CYCLE_MARK(SD_CMD12_DONE);
    }
    if (result) {
        abort_dma_write(c);
        return result;
    }
#if !SD_REVIEW_PROFILE
    X->DCTRL=0;
    X->ICR=DMA_FLAGS;
#endif
    CYCLE_MARK(SD_WRITE_FINAL_READY_BEGIN);
#if SD_REVIEW_PROFILE
    result=ready_after_transfer(c);
#else
    result=ready(c);
#endif
#if SD_REVIEW_PROFILE
    if (!result) { X->DCTRL=0; X->ICR=DMA_FLAGS; }
#endif
    if (!result) c->written_sectors+=count;
    if (!result) {
        CYCLE_MARK(SD_WRITE_FINAL_READY_DONE);
        CYCLE_MARK(SD_WRITE_DONE);
    }
    return result;
}

#if SD_HIGH_SPEED
static int high_speed_status_valid(const uint8_t *status)
{
    /* SD Physical Layer section 4.3.10, 512-bit switch-function status.
     * Wire bytes are MSB first. No UHS/current-limit/driver-strength group is
     * changed: all groups except access mode are requested as 0xF. */
    uint32_t current=((uint32_t)status[0]<<8)|status[1];
    uint32_t support=((uint32_t)status[12]<<8)|status[13];
    if(!current || current>200U || status[17]>1U || !(support&2U) ||
            (status[16]&15U)!=1U) return SD_ERR_UNSUPPORTED;
    for(unsigned n=14;n<=16;++n)
        if((status[n]&15U)==15U || (status[n]>>4)==15U) return SD_ERR_UNSUPPORTED;
    if(status[17]==1U && (status[29]&2U)) return SD_ERR_NOT_READY;
    return SD_OK;
}

static int high_speed_status_read(sd_card_t *c,uint32_t switching)
{
    int result=ready(c);
    if(result) return result;
    if(X->IDMACTRL || c->clock_hz!=25000000U)
        return fault(c,SD_ERR_CLOCK);
    c->stage=SD_STAGE_SWITCH;c->media_idle=0;
    uint8_t status[64];uint32_t words=0,sta=0,start=DWT->CYCCNT;
    X->DCTRL=0;X->ICR=DATA_FLAGS;X->DTIMER=c->clock_hz*2U;
    X->DLEN=64U;
    X->DCTRL=(6U<<SDMMC_DCTRL_DBLOCKSIZE_Pos)|SDMMC_DCTRL_DTDIR;
    result=command(c,6,switching?0x80FFFFF1U:0x00FFFFF1U,RESP_R1,1);
    uint32_t r1=c->last_r1;
    if(!result) for(uint32_t i=0;i<POLL_LIMIT;i++) {
        sta=X->STA;c->last_sta=sta;
        if(sta&DATA_ERRORS) {result=fault(c,SD_ERR_DATA);break;}
        if(words<16U && !(sta&SDMMC_STA_RXFIFOE)) {
            store_word(status+words*4U,X->FIFO);words++;
        }
        if((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT) && words==16U) break;
        if((uint32_t)(DWT->CYCCNT-start)>=READ_TIMEOUT_CYCLES) {
            result=fault(c,SD_ERR_DATA_TIMEOUT);break;
        }
        if(i==POLL_LIMIT-1U) result=fault(c,SD_ERR_TIMER);
        if(!(i&255U)) sd_progress();
    }
    c->transfer_words=words;c->transfer_sta=sta;c->transfer_cycles=DWT->CYCCNT-start;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if(!result && (words!=16U || !(sta&SDMMC_STA_DATAEND) ||
            (sta&(DATA_ERRORS|SDMMC_STA_DPSMACT)) || X->DCOUNT))
        result=fault(c,SD_ERR_LENGTH);
    if(result) {abort_transfer(c,1);return result;}
    X->DCTRL=0;X->ICR=DATA_FLAGS;
    volatile uint8_t *saved=switching?sd_high_speed_proof.switch_status:sd_high_speed_proof.check_status;
    for(uint32_t i=0;i<64U;i++) saved[i]=status[i];
    if(switching) {sd_high_speed_proof.switch_r1=r1;sd_high_speed_proof.switch_sta=sta;}
    else {sd_high_speed_proof.check_r1=r1;sd_high_speed_proof.check_sta=sta;}
    if((result=ready(c))) return result;
    result=high_speed_status_valid(status);
    if(result) return fault(c,result);
    if(switching) sd_high_speed_proof.switch_done=1U;
    else sd_high_speed_proof.check_done=1U;
    return SD_OK;
}

static int high_speed_enable(sd_card_t *c)
{
    int result=high_speed_status_read(c,0);
    if(result) return result;
    result=high_speed_status_read(c,1);
    if(result) return result;
    /* A function switch takes effect within eight clocks after its status
     * data block. Keep 25 MHz running for at least 1 us before accelerating. */
    if((result=delay_us(c,1))) return result;
    if((X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) || X->IDMACTRL)
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    X->CLKCR=(SD_KERNEL_HZ/(2U*50000000U))|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|RUN_PHASE_BITS;
    sd_high_speed_proof.configured_clkcr=X->CLKCR;
    if(X->CLKCR!=(1U|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|RUN_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
    c->clock_hz=50000000U;
    if((result=ready(c))) return result;
    sd_bus_width_proof.configured_clkcr=X->CLKCR;
    sd_high_speed_proof.qualified=1U;
    return SD_OK;
}
#endif

#if SD_EARLY_RUN_CLOCK
/* CSD bits103:96 encode a decimal multiplier and transfer-rate unit, not a
 * binary frequency. Keep decoding integral and reject every reserved value.
 * Maximum valid product is800 MHz, which fits uint32_t. This does not negotiate
 * High Speed: the admitted requested rate remains <=25 MHz Default Speed. */
static uint32_t csd_transfer_hz(uint32_t encoded)
{
    static const uint8_t tenths[16]={0,10,12,13,15,20,25,30,35,40,45,50,55,60,70,80};
    static const uint32_t units[4]={100000U,1000000U,10000000U,100000000U};
    uint32_t unit=encoded&7U,multiplier=(encoded>>3)&15U;
    if((encoded&~0x7FU) || unit>3U || !multiplier) return 0;
    return (units[unit]/10U)*tenths[multiplier];
}

static int early_run_clock(sd_card_t *c,uint32_t run_hz)
{
    sd_early_clock_proof.csd_tran_speed=c->csd[0]&255U;
    sd_early_clock_proof.csd_max_hz=csd_transfer_hz(c->csd[0]&255U);
    sd_early_clock_proof.csd_command_count=c->command_count;
    if(!sd_early_clock_proof.csd_max_hz || sd_early_clock_proof.csd_max_hz<run_hz)
        return fault(c,SD_ERR_UNSUPPORTED);
    if((run_hz!=12500000U && run_hz!=25000000U) || c->clock_hz!=100000U ||
            SD_KERNEL_HZ%(2U*run_hz) || c->last_command!=9U)
        return fault(c,SD_ERR_CLOCK);
    SD_HOST_GUARD(c);
    CYCLE_MARK(SD_CLOCK_SWITCH_BEGIN);
    sd_early_clock_proof.switch_begin_cycles=DWT->CYCCNT;
    if((X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) || X->IDMACTRL)
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    const uint32_t initial=(SD_KERNEL_HZ/(2U*100000U))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS;
    const uint32_t desired=(SD_KERNEL_HZ/(2U*run_hz))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS;
    sd_early_clock_proof.clock_before=X->CLKCR;
    sd_early_clock_proof.timer_before=X->DTIMER;
    if(sd_early_clock_proof.clock_before!=initial) return fault(c,SD_ERR_CLOCK);
    if(sd_early_clock_proof.timer_before!=200000U) return fault(c,SD_ERR_TIMER);
    sd_early_clock_proof.switch_command_count=c->command_count;
    X->CLKCR=desired;
    __DSB();
    sd_early_clock_proof.clock_after=X->CLKCR;
    if(sd_early_clock_proof.clock_after!=desired) return fault(c,SD_ERR_CLOCK);
    c->clock_hz=run_hz;
    /* CMD7 is R1b. Preserve a two-second hardware busy bound in the NEW clock
     * domain before any command can assert busy. No ready()/CMD13 while STBY. */
    X->DTIMER=run_hz*2U;
    __DSB();
    sd_early_clock_proof.timer_after=X->DTIMER;
    if(sd_early_clock_proof.timer_after!=run_hz*2U) return fault(c,SD_ERR_TIMER);
    sd_startup_proof.run_hz=run_hz;
    uint32_t settle_begin=DWT->CYCCNT;
    int result=delay_us(c,1);
    if(result) return result;
    sd_startup_proof.run_settle_cycles=(uint32_t)(DWT->CYCCNT-settle_begin);
    sd_early_clock_proof.switch_end_cycles=DWT->CYCCNT;
    CYCLE_MARK(SD_CLOCK_SWITCH_DONE);
    return SD_OK;
}

static int identify(sd_card_t *c,uint32_t run_hz)
#else
static int identify(sd_card_t *c)
#endif
{
    int result;
    c->stage=SD_STAGE_IDENTIFY;
    CYCLE_MARK(SD_CMD0_BEGIN);
    if ((result=command(c,0,0,RESP_NONE,0))) return result;
    CYCLE_MARK(SD_CMD0_DONE);
    CYCLE_MARK(SD_CMD8_BEGIN);
    if ((result=command(c,8,0x1AAUL,RESP_R7,0))) return result;
    CYCLE_MARK(SD_CMD8_DONE);
    if ((X->RESP1&0xFFFUL)!=0x1AAUL) return fault(c,SD_ERR_UNSUPPORTED);
    uint32_t start=DWT->CYCCNT;
    CYCLE_MARK(SD_ACMD41_BEGIN);
    for (uint32_t i=0;i<2000;++i) {
        CYCLE_COUNT(SD_ACMD41_ATTEMPTS);
        if ((result=command(c,55,0,RESP_R1,0))) return result;
        if (!(X->RESP1&(1UL<<5))) return fault(c,SD_ERR_RESPONSE);
        /* HCS, 3.2-3.4 V. No S18R, XPC, cache enabling or mode switching. */
        if ((result=command(c,41,0x40300000UL,RESP_R3,0))) return result;
        c->ocr=X->RESP1;
        if (c->ocr&(1UL<<31)) break;
        if ((uint32_t)(DWT->CYCCNT-start)>=READY_TIMEOUT_CYCLES || i==1999)
            return fault(c,SD_ERR_NOT_READY);
        if ((result=delay_us(c,1000))) return result;
    }
    CYCLE_MARK(SD_ACMD41_DONE);
    CYCLE_MARK(SD_IDENTIFY_REGS_BEGIN);
    if ((result=command(c,2,0,RESP_R2,0))) return result;
    c->cid[0]=X->RESP1; c->cid[1]=X->RESP2;
    c->cid[2]=X->RESP3; c->cid[3]=X->RESP4;
    if ((result=command(c,3,0,RESP_R6,0))) return result;
    c->rca=X->RESP1&0xFFFF0000UL;
    if (!c->rca) return fault(c,SD_ERR_RESPONSE);
    if ((result=command(c,9,c->rca,RESP_R2,0))) return result;
    c->csd[0]=X->RESP1; c->csd[1]=X->RESP2;
    c->csd[2]=X->RESP3; c->csd[3]=X->RESP4;
    uint32_t version=c->csd[0]>>30;
    if (version==1 && (c->ocr&(1UL<<30))) {
        uint32_t size=((c->csd[1]&63UL)<<16)|(c->csd[2]>>16);
        c->sector_count=((uint64_t)size+1)<<10;
    } else if (version==0 && !(c->ocr&(1UL<<30))) {
        uint32_t size=((c->csd[1]&1023UL)<<2)|(c->csd[2]>>30);
        uint32_t mult=(c->csd[2]>>15)&7UL, readlen=(c->csd[1]>>16)&15UL;
        if (readlen<9 || readlen>11) return fault(c,SD_ERR_CAPACITY);
        c->sector_count=((uint64_t)size+1)<<(mult+2+readlen-9);
    } else return fault(c,SD_ERR_UNSUPPORTED);
    if (!c->sector_count || c->sector_count>(1ULL<<32))
        return fault(c,SD_ERR_CAPACITY);
    CYCLE_MARK(SD_IDENTIFY_REGS_DONE);
#if SD_EARLY_RUN_CLOCK
    if((result=early_run_clock(c,run_hz))) return result;
#endif
    c->stage=SD_STAGE_SELECT;
    CYCLE_MARK(SD_SELECT_BEGIN);
#if SD_EARLY_RUN_CLOCK
    sd_early_clock_proof.select_begin_cycles=DWT->CYCCNT;
    if((result=command(c,7,c->rca,RESP_R1,0))) return result;
    sd_early_clock_proof.select_command_count=c->command_count;
    if((result=ready(c))) return result;
#else
    if ((result=command(c,7,c->rca,RESP_R1,0)) || (result=ready(c))) return result;
#endif
    if (!(c->ocr&(1UL<<30)) && (result=command(c,16,512,RESP_R1,0))) return result;
    CYCLE_MARK(SD_SELECT_DONE);
    return SD_OK;
}

#if SD_HIGH_SPEED
static int sd_init_attempt(sd_card_t *c, uint32_t max_hz)
#else
int sd_init(sd_card_t *c, uint32_t max_hz)
#endif
{
    if (!c) return SD_ERR_ARGUMENT;
    if (c->initialized || c->controller_owned) return SD_ERR_STATE;
#if SD_EARLY_RUN_CLOCK
    volatile uint8_t *early_clear=(volatile uint8_t *)&sd_early_clock_proof;
    for(size_t i=0;i<sizeof(sd_early_clock_proof);i++) early_clear[i]=0;
    sd_early_clock_proof.magic=0x314B4345U; /* ECK1 */
    sd_early_clock_proof.version=1U;
    sd_early_clock_proof.requested_hz=max_hz;
#endif
#if SD_STARTUP_OPT
    startup_scr_invalidate();
    volatile uint8_t *startup_clear=(volatile uint8_t *)&sd_startup_proof;
    for(size_t i=0;i<sizeof(sd_startup_proof);i++) startup_clear[i]=0;
    sd_startup_proof.magic=0x31504F53U; /* SOP1 */
    sd_startup_proof.version=1U;
#endif
    CYCLE_MARK(SD_INIT_BEGIN);
    CYCLE_COUNT(SD_INIT_CALLS);
#if SD_BUS_WIDTH == 4
    volatile uint8_t *width_clear=(volatile uint8_t *)&sd_bus_width_proof;
    for (size_t i=0;i<sizeof(sd_bus_width_proof);++i) width_clear[i]=0;
    sd_bus_width_proof.requested_width=4U;
#endif
#if SD_GPIO_SPEED != 3
    volatile uint8_t *gpio_clear=(volatile uint8_t *)&sd_gpio_proof;
    for (size_t i=0;i<sizeof(sd_gpio_proof);++i) gpio_clear[i]=0;
    sd_gpio_proof.requested_speed=SD_GPIO_SPEED;
    sd_gpio_proof.c_mask=C_MASK;
#if SD_BUS_WIDTH == 4
    sd_gpio_proof.e_mask=3UL<<8;
#endif
#endif
#if SD_FIXED_COMPENSATION
    volatile uint8_t *comp_clear=(volatile uint8_t *)&sd_compensation_proof;
    for (size_t i=0;i<sizeof(sd_compensation_proof);++i) comp_clear[i]=0;
#endif
    volatile uint8_t *p=(volatile uint8_t *)c;
    for (size_t i=0;i<sizeof(*c);++i) p[i]=0;
    c->stage=SD_STAGE_PREFLIGHT;
#if SD_STARTUP_OPT
    if(max_hz==100000U) return fault(c,SD_ERR_ARGUMENT);
#endif
#if SD_HIGH_SPEED
    volatile uint8_t *hs_clear=(volatile uint8_t *)&sd_high_speed_proof;
    for(size_t i=0;i<sizeof(sd_high_speed_proof);++i) hs_clear[i]=0;
    sd_high_speed_proof.requested_hz=max_hz;
    sd_high_speed_proof.kernel_hz=SD_KERNEL_HZ;
    if(max_hz!=50000000UL) return fault(c,SD_ERR_ARGUMENT);
#else
    if (max_hz!=100000UL && max_hz!=12500000UL && max_hz!=25000000UL)
        return fault(c,SD_ERR_ARGUMENT);
#if SD_FIXED_COMPENSATION || (SD_CLOCK_NEGEDGE && !SD_CLOCK_NEGEDGE_INIT) || SD_GPIO_SPEED == 1 || SD_GPIO_SPEED == 2
    if (max_hz!=25000000UL) return fault(c,SD_ERR_ARGUMENT);
#endif
#if SD_CLOCK_NEGEDGE_INIT
    if (max_hz!=12500000UL && max_hz!=25000000UL) return fault(c,SD_ERR_ARGUMENT);
#endif
#endif
    if (__get_IPSR() || (__get_CONTROL()&1U)) return fault(c,SD_ERR_STATE);
    if (R->CFGR1!=0x33330000UL || R->CFGR2!=0x00100000UL ||
        R->PLL1CFGR1!=0x00404B00UL || R->PLL1CFGR2 ||
        R->PLL1CFGR3!=0x49000005UL ||
        (R->IC1CFGR&(RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))!=0x20000UL ||
        (R->IC2CFGR&(RCC_IC2CFGR_IC2INT|RCC_IC2CFGR_IC2SEL))!=0x30000UL ||
        !(R->DIVENR&RCC_DIVENR_IC2EN) || (R->HSICFGR&RCC_HSICFGR_HSIDIV))
        return fault(c,SD_ERR_CLOCK);
    if (R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) return fault(c,SD_ERR_CONTROLLER_BUSY);
    R->AHB4ENSR=RCC_AHB4ENSR_PWRENS|RCC_AHB4ENSR_GPIOCENS|RCC_AHB4ENSR_GPIOEENS;
    (void)R->AHB4ENR;
#if SD_FIXED_COMPENSATION
    /* Prove this clock before any PWR register read. No supply is enabled here. */
    if (!(R->AHB4ENR&RCC_AHB4ENR_PWREN)) return fault(c,SD_ERR_CLOCK);
#endif
    if (P->SVMCR2&PWR_SVMCR2_VDDIO5VRSEL) return fault(c,SD_ERR_VOLTAGE);
#if SD_BUS_WIDTH == 4
    for (uint32_t pin=0;pin<=5;++pin) {
        if (!(C_PINS&(1UL<<pin))) continue;
#else
    for (uint32_t pin=2;pin<=4;++pin) {
#endif
        uint32_t mode=(C->MODER>>(2*pin))&3UL;
        if (mode==1 || mode==2) return fault(c,SD_ERR_GPIO);
    }
    uint32_t mode=(E->MODER>>8)&3UL;
    if (mode==1 || mode==2) return fault(c,SD_ERR_GPIO);
    c->saved_demcr=CoreDebug->DEMCR; c->saved_dwt=DWT->CTRL;
    if (c->saved_dwt&DWT_CTRL_NOCYCCNT_Msk) return fault(c,SD_ERR_TIMER);
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
    c->timer_owned=1;
    __DSB(); __ISB();
    uint32_t start=DWT->CYCCNT;
    int result=delay_us(c,1);
    if (result) return result;
    c->stage=SD_STAGE_GPIO;
    CYCLE_MARK(SD_GPIO_BEGIN);
#if SD_GPIO_SPEED != 3
    sd_gpio_proof.c_before=C->OSPEEDR;
    sd_gpio_proof.e_before=E->OSPEEDR;
#endif
    C->BSRR=1UL<<(2+16);
    C->OTYPER&=~C_PINS;
    C->MODER&=~C_MASK;
    C->PUPDR=(C->PUPDR&~C_MASK)|C_PULLS;
#if SD_HIGH_SPEED
    sd_high_speed_proof.gpio_c_before=C->OSPEEDR;
    sd_high_speed_proof.gpio_e_before=E->OSPEEDR;
#endif
#if SD_HIGH_SPEED_MIXED_SLEW
    /* DS14791 HS table: CLK=01, CMD/DAT=00. PC1 and other pins untouched. */
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|(1UL<<4);
#elif SD_GPIO_SPEED == 3
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|C_MASK;
#else
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|(C_MASK/3U*SD_GPIO_SPEED);
    sd_gpio_proof.c_after=C->OSPEEDR;
    if ((sd_gpio_proof.c_after&C_MASK)!=(C_MASK/3U*SD_GPIO_SPEED) ||
            ((sd_gpio_proof.c_before^sd_gpio_proof.c_after)&~C_MASK))
        return fault(c,SD_ERR_GPIO);
#endif
    E->MODER&=~(3UL<<8);
    E->PUPDR=(E->PUPDR&~(3UL<<8))|(1UL<<8);
    P->SVMCR2|=PWR_SVMCR2_VDDIO5SV;
    c->vddio5_control=P->SVMCR2;
#if SD_FIXED_COMPENSATION
    /* ES0620 2.2.20 fixed code: EN=0, CS=1, RANSRC=7, RAPSRC=8.
     * ES0620 2.2.19 and RM0486 require both independent supplies valid before
     * accessing this SYSCFG register. Do not manufacture missing VDDIO3SV.
     * Change only VDDIO5CCCR; no automatic compensation/HSI-ready wait.
     */
    sd_compensation_proof.svmcr2=P->SVMCR2;
    sd_compensation_proof.svmcr3=P->SVMCR3;
    if (!(sd_compensation_proof.svmcr2&PWR_SVMCR2_VDDIO5SV) ||
            !(sd_compensation_proof.svmcr3&PWR_SVMCR3_VDDIO3SV))
        return fault(c,SD_ERR_VOLTAGE);
    sd_compensation_proof.clock_before=R->APB4ENR2;
    sd_compensation_proof.reset=R->APB4RSTR2;
    if (sd_compensation_proof.reset&RCC_APB4RSTR2_SYSCFGRST)
        return fault(c,SD_ERR_CLOCK);
    if (!(sd_compensation_proof.clock_before&RCC_APB4ENR2_SYSCFGEN))
        R->APB4ENSR2=RCC_APB4ENSR2_SYSCFGENS;
    __DSB();
    sd_compensation_proof.clock_after=R->APB4ENR2;
    sd_compensation_proof.reset=R->APB4RSTR2;
    if (sd_compensation_proof.clock_after!=(sd_compensation_proof.clock_before|RCC_APB4ENR2_SYSCFGEN) ||
            (sd_compensation_proof.reset&RCC_APB4RSTR2_SYSCFGRST))
        return fault(c,SD_ERR_CLOCK);
    sd_compensation_proof.before=SYSCFG_S->VDDIO5CCCR;
    SYSCFG_S->VDDIO5CCCR=0x287U;
    __DSB();
    sd_compensation_proof.after=SYSCFG_S->VDDIO5CCCR;
    if (sd_compensation_proof.after!=0x287U) return fault(c,SD_ERR_GPIO);
    sd_compensation_proof.applied=1U;
#endif
    CYCLE_MARK(SD_GPIO_SETTLE_BEGIN);
#if SD_STARTUP_OPT
    uint32_t startup_begin=DWT->CYCCNT;
#endif
    if ((result=delay_us(c,1000))) return result;
#if SD_STARTUP_OPT
    sd_startup_proof.gpio_settle_cycles=(uint32_t)(DWT->CYCCNT-startup_begin);
#endif
    CYCLE_MARK(SD_GPIO_SETTLE_DONE);
    c->gpioc_idr=C->IDR; c->gpioe_idr=E->IDR;
    if ((c->gpioc_idr&C_IDLE_PINS)!=C_IDLE_PINS ||
        !(c->gpioe_idr&(1UL<<4))) return fault(c,SD_ERR_GPIO);
    c->saved_sdmmc_mux=R->CCIPR8&RCC_CCIPR8_SDMMC2SEL;
#if SD_HIGH_SPEED
    if(!sd_review_clock_acquire()) {
        c->controller_owned=sd_review_clock_proof.owned;
        if(c->controller_owned)c->cleanup_error=SD_ERR_CLOCK;
        return fault(c,SD_ERR_CLOCK);
    }
#else
    R->CCIPR8&=~RCC_CCIPR8_SDMMC2SEL;
#endif
    R->AHB5ENSR=RCC_AHB5ENSR_SDMMC2ENS;
#if SD_HIGH_SPEED
    if (!(R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN)) {
        if(!sd_review_clock_release()) {c->cleanup_error=SD_ERR_CLOCK;c->controller_owned=1;}
        return fault(c,SD_ERR_CLOCK);
    }
#elif SD_STARTUP_OPT
    if(!(R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN)) return fault(c,SD_ERR_CLOCK);
#else
    (void)R->AHB5ENR;
#endif
    R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
    __DSB();
    c->controller_owned=1;
    X->MASK=0; X->POWER=0; X->DCTRL=0; X->IDMACTRL=0; X->CMD=0;
#if SD_CLOCK_NEGEDGE_INIT
    /* Configure before enabling the controller clock output. The input clock
     * remains SELCLKRX=0; only host CMD/DAT launch changes to falling edge. */
    if (X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    X->CLKCR=(SD_KERNEL_HZ/(2U*100000U))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS;
    if (X->CLKCR!=((SD_KERNEL_HZ/(2U*100000U))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
#else
    X->CLKCR=750UL|SDMMC_CLKCR_HWFC_EN;
#endif
    C->AFR[0]=(C->AFR[0]&~C_AF_MASK)|C_AF_BITS;
    C->MODER=(C->MODER&~C_MASK)|C_MODES;
    if ((C->MODER&C_MASK)!=C_MODES ||
        (C->AFR[0]&C_AF_MASK)!=C_AF_BITS ||
        (E->MODER&(3UL<<8)) || (E->PUPDR&(3UL<<8))!=(1UL<<8))
        return fault(c,SD_ERR_GPIO);
    X->POWER=SDMMC_POWER_PWRCTRL;
    c->clock_hz=100000UL;
#if SD_REVIEW_PROFILE
    /* CMD7 can return R1b during identification, before the first data API
     * otherwise initializes DTIMER. Its reset value0 can latch a Busy
     * timeout on a legitimate select-card response. Set the two-second
     * identification-clock bound while both state machines are idle. */
    if (X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    X->DTIMER=c->clock_hz*2UL;
#endif
    CYCLE_MARK(SD_CLOCK_TRAIN_BEGIN);
#if SD_STARTUP_OPT
    /* The fixed Nucleo/card wiring supplies VCC from the already running
     * target3.3V rail, valid before the retained1ms GPIO settle interval.
     * VDDIO5SV alone is not supply evidence. SD4.4/6.4.1 then permits1ms
     * of continuous100kHz clocks (100 >=74), with CMD held high. This profile
     * must not be used for a separately switched/ramping card supply. */
    if(X->POWER!=SDMMC_POWER_PWRCTRL ||
       X->CLKCR!=((SD_KERNEL_HZ/(2U*100000U))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
    sd_startup_proof.train_hz=100000U;sd_startup_proof.train_min_cycles=400000U;
    startup_begin=DWT->CYCCNT;
    if((result=delay_us(c,1000))) return result;
    sd_startup_proof.train_cycles=(uint32_t)(DWT->CYCCNT-startup_begin);
#else
    if ((result=delay_us(c,10000))) return result;
#endif
    CYCLE_MARK(SD_CLOCK_TRAIN_DONE);
#if SD_EARLY_RUN_CLOCK
    if((result=identify(c,max_hz))) return result;
#else
    if ((result=identify(c))) return result;
#if SD_CLOCK_NEGEDGE
    /* RM0486 Rev4 p1433: change only with both state machines idle. Historical
     * profiles leave 100 kHz identification unchanged; the explicit INIT
     * option applies the same launch phase there. Neither changes SELCLKRX,
     * BUSSPEED, GPIO speed or compensation. */
    if (X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))
        return fault(c,SD_ERR_CONTROLLER_BUSY);
#endif
    CYCLE_MARK(SD_CLOCK_SWITCH_BEGIN);
#if SD_HIGH_SPEED
    const uint32_t run_hz=25000000U;
#else
    const uint32_t run_hz=max_hz;
#endif
    X->CLKCR=(SD_KERNEL_HZ/(2*run_hz))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS;
#if SD_CLOCK_NEGEDGE
    if (X->CLKCR!=((SD_KERNEL_HZ/(2*run_hz))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
#endif
    c->clock_hz=run_hz;
#if SD_STARTUP_OPT
    /* No PLL/source changes here: only an idle SD divider. One microsecond
     * supplies >=12 clocks at supported run rates; the following fresh CMD13
     * also preserves readiness. CMD6's later8-clock switch delay is separate. */
    __DSB();
    if(X->CLKCR!=((SD_KERNEL_HZ/(2U*run_hz))|SDMMC_CLKCR_HWFC_EN|INIT_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
    sd_startup_proof.run_hz=run_hz;startup_begin=DWT->CYCCNT;
    if((result=delay_us(c,1))) return result;
    sd_startup_proof.run_settle_cycles=(uint32_t)(DWT->CYCCNT-startup_begin);
    if((result=ready(c))) return result;
#else
    if ((result=delay_us(c,1000)) || (result=ready(c))) return result;
#endif
    CYCLE_MARK(SD_CLOCK_SWITCH_DONE);
#endif
#if SD_BUS_WIDTH == 4
    /* SCR data is still received on DAT0. Require both mandatory one-bit and
     * requested four-bit capability; never silently run a four-bit build in
     * one-bit mode. CMD6 here is ACMD6 (argument2), not high-speed CMD6. */
    sd_scr_t scr;
    CYCLE_MARK(SD_WIDTH_BEGIN);
    if ((result=read_scr_selected(c,&scr))) return result;
    CYCLE_MARK(SD_WIDTH_SCR_DONE);
    c->stage=SD_STAGE_BUS_WIDTH;
    sd_bus_width_proof.scr_widths=scr.bytes[1]&15U;
    if ((scr.bytes[1]&5U)!=5U) return fault(c,SD_ERR_UNSUPPORTED);
#if SD_HIGH_SPEED
    /* SD_SPEC 1 (v1.10) introduced the native CMD6 switch function. */
    if (!(scr.bytes[0]&15U)) return fault(c,SD_ERR_UNSUPPORTED);
#endif
    c->media_idle=0;
    if ((result=command(c,55,c->rca,RESP_R1,0))) return result;
    if (!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    result=command(c,6,2,RESP_R1,0);
    sd_bus_width_proof.acmd6_r1=c->last_r1;
    if (result) return result;
    if (!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    sd_bus_width_proof.acmd6_accepted=1U;
    CYCLE_MARK(SD_WIDTH_ACMD6_DONE);
    if ((X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) || X->IDMACTRL)
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    /* An uncertain ACMD6 response retains ownership and does not guess which
     * width the card selected. Only successful negotiation reaches this. */
    E->OTYPER&=~(1UL<<4);
#if SD_HIGH_SPEED_MIXED_SLEW
    E->OSPEEDR&=~(3UL<<8);
#elif SD_GPIO_SPEED == 3
    E->OSPEEDR=(E->OSPEEDR&~(3UL<<8))|(3UL<<8);
#else
    E->OSPEEDR=(E->OSPEEDR&~(3UL<<8))|((uint32_t)SD_GPIO_SPEED<<8);
    sd_gpio_proof.e_after=E->OSPEEDR;
    if ((sd_gpio_proof.e_after&(3UL<<8))!=((uint32_t)SD_GPIO_SPEED<<8) ||
            ((sd_gpio_proof.e_before^sd_gpio_proof.e_after)&~(3UL<<8)))
        return fault(c,SD_ERR_GPIO);
#endif
    E->AFR[0]=(E->AFR[0]&~(15UL<<16))|(11UL<<16);
    E->MODER=(E->MODER&~(3UL<<8))|(2UL<<8);
    if ((E->MODER&(3UL<<8))!=(2UL<<8) ||
        (E->AFR[0]&(15UL<<16))!=(11UL<<16)) return fault(c,SD_ERR_GPIO);
    X->CLKCR|=WIDTH_BITS;
    __DSB();
    sd_bus_width_proof.configured_clkcr=X->CLKCR;
    if ((X->CLKCR&SDMMC_CLKCR_WIDBUS)!=WIDTH_BITS) return fault(c,SD_ERR_CLOCK);
    if ((result=ready(c))) return result;
    sd_bus_width_proof.negotiated_width=4U;
    CYCLE_MARK(SD_WIDTH_DONE);
#endif
#if SD_GPIO_SPEED != 3
    sd_gpio_proof.c_after=C->OSPEEDR; sd_gpio_proof.e_after=E->OSPEEDR;
    if ((sd_gpio_proof.c_after&sd_gpio_proof.c_mask)!=(sd_gpio_proof.c_mask/3U*SD_GPIO_SPEED) ||
            (sd_gpio_proof.e_after&sd_gpio_proof.e_mask)!=(sd_gpio_proof.e_mask/3U*SD_GPIO_SPEED) ||
            ((sd_gpio_proof.c_before^sd_gpio_proof.c_after)&~sd_gpio_proof.c_mask) ||
            ((sd_gpio_proof.e_before^sd_gpio_proof.e_after)&~sd_gpio_proof.e_mask))
        return fault(c,SD_ERR_GPIO);
    sd_gpio_proof.applied=1U;
#endif
#if SD_HIGH_SPEED
    sd_high_speed_proof.gpio_c_after=C->OSPEEDR;
    sd_high_speed_proof.gpio_e_after=E->OSPEEDR;
#if SD_HIGH_SPEED_MIXED_SLEW
    const uint32_t wanted_c_speed=1UL<<4,wanted_e_speed=0;
#else
    const uint32_t wanted_c_speed=C_MASK,wanted_e_speed=3UL<<8;
#endif
    if((C->OSPEEDR&C_MASK)!=wanted_c_speed || (E->OSPEEDR&(3UL<<8))!=wanted_e_speed ||
            ((C->OSPEEDR^sd_high_speed_proof.gpio_c_before)&~C_MASK) ||
            ((E->OSPEEDR^sd_high_speed_proof.gpio_e_before)&~(3UL<<8)))
        return fault(c,SD_ERR_GPIO);
    if((result=high_speed_enable(c))) return result;
#endif
    c->initialized=1;
    c->init_cycles=DWT->CYCCNT-start;
    CYCLE_MARK(SD_INIT_DONE);
    return SD_OK;
}

#if SD_HIGH_SPEED
int sd_init(sd_card_t *c,uint32_t max_hz)
{
    if(!c) return SD_ERR_ARGUMENT;
    if(c->initialized || c->controller_owned) return SD_ERR_STATE;
    int result=sd_init_attempt(c,max_hz);
    if(result && c && c->controller_owned) {
        /* Failed negotiation never becomes success. A fresh idle proof permits
         * restoring the nondefault RCC mux before later ROM recovery. If the
         * host/card remains ambiguous, preserve ownership for cold recovery. */
        if((R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN) &&
                !(X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) && !X->IDMACTRL) {
            int cleanup=ready(c);
            if(!cleanup) {
                c->initialized=1;
                cleanup=sd_deinit(c);
                if(cleanup)c->initialized=0;
            }
            c->cleanup_error=(uint32_t)cleanup;
        } else if(!c->cleanup_error) c->cleanup_error=SD_ERR_CONTROLLER_BUSY;
    }
    return result;
}
#endif

static int block_request(sd_card_t *c, uint32_t lba, void *buffer,
                         uint32_t count, uint32_t writing)
{
    if (!c || !buffer || !count) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    if (c->error) return (int)c->error;
    c->stage=writing ? SD_STAGE_WRITE : SD_STAGE_READ;
    if ((uint64_t)lba+count>c->sector_count) return fault(c,SD_ERR_CAPACITY);
    uint8_t *p=(uint8_t *)buffer;
    /* At 100 kHz, 64 sectors need 2.62144 s of wire payload alone. Use 16 sectors
     * (0.65536 s) so the same bounded polling deadline remains meaningful. */
    uint32_t chunk_limit=c->clock_hz==100000UL ? 16UL : SD_MAX_TRANSFER_SECTORS;
    while (count) {
        sd_progress();
        uint32_t chunk=count>chunk_limit ? chunk_limit : count;
        uint32_t start=DWT->CYCCNT;
        int result=transfer(c,lba,p,chunk,writing);
        uint32_t cycles=DWT->CYCCNT-start;
        sd_progress();
        if (writing) c->write_cycles+=cycles;
        else c->read_cycles+=cycles;
        if (result) return result;
        count-=chunk; lba+=chunk; p+=chunk*SD_SECTOR_BYTES;
    }
    return SD_OK;
}

#if SD_IDMA_READ
static int dma_read_request(sd_card_t *c,uint32_t lba,void *buffer,uint32_t count);
#endif
int sd_read_blocks(sd_card_t *c, uint32_t lba, void *buffer, uint32_t count)
{
#if SD_IDMA_READ
    return dma_read_request(c,lba,buffer,count);
#else
    return block_request(c,lba,buffer,count,0);
#endif
}

int sd_write_blocks(sd_card_t *c, uint32_t lba, const void *buffer, uint32_t count)
{
    return block_request(c,lba,(void *)buffer,count,1);
}

static int dma_source_checks(sd_card_t *c,uint32_t lba,const void *buffer,uint32_t count)
{
    if (!c || !buffer || !count) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    if (c->error) return (int)c->error;
    c->stage=SD_STAGE_WRITE;
    uintptr_t address=(uintptr_t)buffer;
    uint64_t end=(uint64_t)address+(uint64_t)count*SD_SECTOR_BYTES;
    /* The current platform contract is secure AXI SRAM1..6. No peripherals,
     * TCM, nonsecure aliases or external memories are accepted speculatively. */
    if ((address&3U) || address<0x34000000UL || end>0x34400000ULL)
        return fault(c,SD_ERR_ARGUMENT);
    if ((uint64_t)lba+count>c->sector_count) return fault(c,SD_ERR_CAPACITY);
    if (__get_IPSR() || (__get_CONTROL()&1U)) return fault(c,SD_ERR_STATE);
    if (SCB->CCR&SCB_CCR_DC_Msk) return fault(c,SD_ERR_CACHE);
    /* Do not probe a gated peripheral. RIMC is configured by the capture owner
     * just as for DCMIPP; this API cannot broaden any SRAM/RISAF permission. */
    if (!(R->AHB3ENR&RCC_AHB3ENR_RIFSCEN)) return fault(c,SD_ERR_SECURITY);
    uint32_t mask=RIFSC_RIMC_ATTRx_MCID|RIFSC_RIMC_ATTRx_MSEC|RIFSC_RIMC_ATTRx_MPRIV;
    uint32_t expected=(1UL<<RIFSC_RIMC_ATTRx_MCID_Pos)|
        RIFSC_RIMC_ATTRx_MSEC|RIFSC_RIMC_ATTRx_MPRIV;
    if ((RIFSC_S->RIMC_ATTRx[3]&mask)!=expected) return fault(c,SD_ERR_SECURITY);
    /* RM0486 6.3.4, table 22: secure guard RISUP54 overrides MSEC to
     * nonsecure when SDMMC2's configuration port is nonsecure. RISAF then
     * returns zeros for protected SRAM reads, without an SD/IDMA bus error.
     * Checking RIMC alone therefore cannot qualify the transfer source. */
    if (!(RIFSC_S->RISC_SECCFGRx[1]&(1UL<<22))) return fault(c,SD_ERR_SECURITY);
    return SD_OK;
}

#if SD_IDMA_READ
static int dma_destination_checks(sd_card_t *c,uint32_t lba,void *buffer,uint32_t count)
{
    if(!c || !buffer || !count) return SD_ERR_ARGUMENT;
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    if(!(R->AHB5ENR&RCC_AHB5ENR_SDMMC2EN)) return fault(c,SD_ERR_CLOCK);
    SD_HOST_GUARD(c);
    if(c->error) return (int)c->error;
    c->stage=SD_STAGE_READ;
    uintptr_t address=(uintptr_t)buffer;
    uint64_t end=(uint64_t)address+(uint64_t)count*SD_SECTOR_BYTES;
    if((address&3U) || address<0x34000000UL || end>0x34400000ULL)
        return fault(c,SD_ERR_ARGUMENT);
    if((uint64_t)lba+count>c->sector_count) return fault(c,SD_ERR_CAPACITY);
    if(__get_IPSR() || (__get_CONTROL()&1U)) return fault(c,SD_ERR_STATE);
    if(SCB->CCR&SCB_CCR_DC_Msk) return fault(c,SD_ERR_CACHE);
    if(!(R->AHB3ENR&RCC_AHB3ENR_RIFSCEN)) return fault(c,SD_ERR_SECURITY);
    const uint32_t mask=RIFSC_RIMC_ATTRx_MCID|RIFSC_RIMC_ATTRx_MSEC|RIFSC_RIMC_ATTRx_MPRIV;
    const uint32_t expected=(1UL<<RIFSC_RIMC_ATTRx_MCID_Pos)|
        RIFSC_RIMC_ATTRx_MSEC|RIFSC_RIMC_ATTRx_MPRIV;
    if((RIFSC_S->RIMC_ATTRx[3]&mask)!=expected ||
       !(RIFSC_S->RISC_SECCFGRx[1]&(1UL<<22))) return fault(c,SD_ERR_SECURITY);
    /* As with writes, the owner must enable SRAM/RISAF destination access.
     * This routine never broadens policy or touches another owner's buffer. */
    return SD_OK;
}

static int transfer_dma_read(sd_card_t *c,uint32_t lba,uint8_t *buffer,uint32_t count)
{
    CYCLE_MARK(SD_READ_LATEST_BEGIN);
    CYCLE_COUNT(SD_READ_TRANSFERS); CYCLE_COUNT(SD_IDMA_TRANSFERS);
    int result=ready(c);
    if(result) return result;
    if(X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    uint32_t start=DWT->CYCCNT,sta=0;
    c->media_idle=0; c->transfer_words=0; c->transfer_sta=0;
    X->DCTRL=0; X->ICR=DMA_FLAGS;
    X->DTIMER=c->clock_hz*2UL; X->DLEN=count*SD_SECTOR_BYTES;
    X->DCTRL=(9UL<<SDMMC_DCTRL_DBLOCKSIZE_Pos)|SDMMC_DCTRL_DTDIR;
    X->IDMABASER=(uint32_t)(uintptr_t)buffer;
    __DSB(); X->IDMACTRL=SDMMC_IDMA_IDMAEN;
    CYCLE_MARK(SD_READ_CMD_BEGIN_LATEST);
    result=command(c,count==1U?17U:18U,
        (c->ocr&(1UL<<30))?lba:lba*512UL,RESP_R1,1);
    if(!result) {
        CYCLE_MARK(SD_READ_CMD_DONE_LATEST);
        for(uint32_t i=0;i<POLL_LIMIT;i++) {
            sta=X->STA; c->last_sta=sta;
            if(sta&DMA_ERRORS) {
                result=fault(c,(sta&SDMMC_STA_IDMATE)?SD_ERR_DMA:SD_ERR_DATA); break;
            }
            /* RM0486 p1402: single-buffer DATAEND includes memory transfer.
             * Do not touch FIFO or consume destination bytes before this. */
            if((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) {
                CYCLE_MARK(SD_READ_DATAEND_LATEST); break;
            }
            if((uint32_t)(DWT->CYCCNT-start)>=READ_TIMEOUT_CYCLES) {
                result=fault(c,SD_ERR_DATA_TIMEOUT); break;
            }
            if(i==POLL_LIMIT-1U) result=fault(c,SD_ERR_TIMER);
            if(!(i&255U)) sd_progress();
        }
    }
    c->transfer_sta=sta; c->transfer_cycles=(uint32_t)(DWT->CYCCNT-start);
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if(!result && (!(sta&SDMMC_STA_DATAEND) ||
       (sta&(DMA_ERRORS|SDMMC_STA_DPSMACT)) || X->DCOUNT))
        result=fault(c,SD_ERR_LENGTH);
    if(result) {
        /* The same IDMA abort sequence applies to RX (RM 30.6.2): hardware
         * drains/discards its FIFO; CPU must not reset it or disable active DMA.
         * A failed abort retains ownership and the first read error. */
        abort_dma_write(c); return result;
    }
    X->IDMACTRL=0; __DSB();
    c->transfer_words=count*128UL;
    if(count>1U) result=command_checked(c,12,0,RESP_R1,0,
        (uint64_t)lba+count==c->sector_count);
    if(result) { abort_dma_write(c); return result; }
    result=ready_after_transfer(c);
    if(result) return result;
    X->DCTRL=0; X->ICR=DMA_FLAGS; __DSB();
    c->read_sectors+=count;
    CYCLE_MARK(SD_READ_LATEST_DONE);
    return SD_OK;
}

static int dma_read_request(sd_card_t *c,uint32_t lba,void *buffer,uint32_t count)
{
    int checked=dma_destination_checks(c,lba,buffer,count);
    if(checked) return checked;
#if SD_HIGH_SPEED
    if(c->clock_hz!=50000000UL || !sd_high_speed_proof.qualified)
#else
    if(c->clock_hz!=100000UL && c->clock_hz!=12500000UL && c->clock_hz!=25000000UL)
#endif
        return fault(c,SD_ERR_CLOCK);
    const uint32_t limit=c->clock_hz==100000UL?16U:512U;
    uint8_t *destination=(uint8_t *)buffer;
    while(count) {
        sd_progress();
        uint32_t chunk=count>limit?limit:count;
        uint32_t start=DWT->CYCCNT;
        int result=transfer_dma_read(c,lba,destination,chunk);
        c->read_cycles+=(uint32_t)(DWT->CYCCNT-start);
        sd_progress();
        if(result) return result;
        count-=chunk; lba+=chunk; destination+=chunk*SD_SECTOR_BYTES;
    }
    return SD_OK;
}
#endif

static int dma_request(sd_card_t *c, uint32_t lba, const void *buffer,
                        uint32_t count, sd_dma_wait_t *wait, uint32_t preerase)
{
    int checked=dma_source_checks(c,lba,buffer,count);
    if(checked) return checked;
    if (wait) {
        uint32_t context_faults=dma_wait_context();
        if (!wait->milliseconds) context_faults|=SD_WAIT_NO_CLOCK;
        if (context_faults) {
            wait->context_faults|=context_faults;
            return fault(c,SD_ERR_WAIT);
        }
    }
#if SD_HIGH_SPEED
    if(c->clock_hz!=50000000UL || !sd_high_speed_proof.qualified)
#else
    if (c->clock_hz!=100000UL && c->clock_hz!=12500000UL && c->clock_hz!=25000000UL)
#endif
        return fault(c,SD_ERR_CLOCK);
    if (preerase && (count<2 || count>SD_DMA_PREERASE_MAX_SECTORS))
        return fault(c,SD_ERR_ARGUMENT);
    /* 4096 sectors take 1.342 s of payload at 12.5 MHz, fitting both the
     * two-second SDMMC data timer and five-second software deadline. A slow
     * identification-clock transaction cannot satisfy those same bounds. */
    if (preerase && c->clock_hz==100000UL) return fault(c,SD_ERR_CLOCK);
    uint32_t limit=preerase ? SD_DMA_PREERASE_MAX_SECTORS :
        c->clock_hz==100000UL ? 16UL : SD_DMA_MAX_TRANSFER_SECTORS;
    const uint8_t *p=(const uint8_t *)buffer;
    while (count) {
        sd_progress();
        uint32_t chunk=count>limit ? limit : count;
        uint32_t start=DWT->CYCCNT;
        int result=transfer_dma_write(c,lba,p,chunk,wait,preerase);
        c->write_cycles+=(uint32_t)(DWT->CYCCNT-start);
        sd_progress();
        if (result) return result;
        count-=chunk; lba+=chunk; p+=chunk*SD_SECTOR_BYTES;
    }
    return SD_OK;
}

int sd_write_blocks_dma(sd_card_t *c, uint32_t lba, const void *buffer, uint32_t count)
{
    return dma_request(c,lba,buffer,count,NULL,0);
}

int sd_write_blocks_dma_preerase(sd_card_t *c, uint32_t lba,
                                 const void *buffer, uint32_t count)
{
    return dma_request(c,lba,buffer,count,NULL,1);
}

int sd_write_blocks_dma_wait(sd_card_t *c, uint32_t lba, const void *buffer,
                             uint32_t count, sd_dma_wait_t *wait)
{
    if (!wait) return SD_ERR_ARGUMENT;
    return dma_request(c,lba,buffer,count,wait,0);
}

#if SD_BUS_WIDTH == 4
static int read_scr_selected(sd_card_t *c,sd_scr_t *scr)
#else
int sd_read_scr(sd_card_t *c,sd_scr_t *scr)
#endif
{
#if SD_BUS_WIDTH == 1
    if(!c || !scr) return SD_ERR_ARGUMENT;
#endif
    scr->valid=0;scr->erased_byte=0;
    for(unsigned n=0;n<8;n++) scr->bytes[n]=0;
#if SD_BUS_WIDTH == 1
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    if(c->error) return (int)c->error;
#endif
    c->stage=SD_STAGE_SCR;
#if SD_STARTUP_OPT
    startup_scr_invalidate();
    ++sd_startup_proof.scr_reads;
#endif
    CYCLE_MARK(SD_SCR_LATEST_BEGIN);
    CYCLE_COUNT(SD_SCR_READS);
    int result=ready(c);
    if(result) return result;
    if(X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    c->media_idle=0;
    result=command(c,55,c->rca,RESP_R1,0);
    if(result) return result;
    if(!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    uint32_t start=DWT->CYCCNT,words=0,sta=0;
    X->DCTRL=0;X->ICR=DATA_FLAGS;X->DTIMER=c->clock_hz*2U;
    X->DLEN=8U;
    /* SCR always has an8-byte data block, independent of CMD16. Keeping the
     * normal512-byte card block length avoids changing subsequent SDSC I/O. */
    X->DCTRL=(3U<<SDMMC_DCTRL_DBLOCKSIZE_Pos)|SDMMC_DCTRL_DTDIR;
    result=command(c,51,0,RESP_R1,1);
    if(!result && !(c->last_r1&(1UL<<5))) result=fault(c,SD_ERR_UNSUPPORTED);
    if(!result) for(uint32_t i=0;i<POLL_LIMIT;i++) {
        sta=X->STA;c->last_sta=sta;
        if(sta&DATA_ERRORS) {result=fault(c,SD_ERR_DATA);break;}
        /* At most two owned words may remain in FIFO after DATAEND. Unlike
         * a speculative inactive-bank read, RXFIFOE proves received data. */
        if(words<2U && !(sta&SDMMC_STA_RXFIFOE)) {
            store_word(scr->bytes+words*4U,X->FIFO);words++;
        }
        if((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT) && words==2U) break;
        if((uint32_t)(DWT->CYCCNT-start)>=READ_TIMEOUT_CYCLES) {
            result=fault(c,SD_ERR_DATA_TIMEOUT);break;
        }
        if(i==POLL_LIMIT-1) result=fault(c,SD_ERR_TIMER);
        if(!(i&255U)) sd_progress();
    }
    c->transfer_words=words;c->transfer_sta=sta;c->transfer_cycles=DWT->CYCCNT-start;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if(!result && (words!=2U || !(sta&SDMMC_STA_DATAEND) || (sta&(DATA_ERRORS|SDMMC_STA_DPSMACT))))
        result=fault(c,SD_ERR_LENGTH);
    if(result) {abort_transfer(c,1);return result;}
    X->DCTRL=0;X->ICR=DATA_FLAGS;
    result=ready(c);if(result) return result;
    if(scr->bytes[0]>>4) return fault(c,SD_ERR_UNSUPPORTED);
    scr->erased_byte=(scr->bytes[1]&0x80U)?255U:0U;scr->valid=1U;
#if SD_STARTUP_OPT
    for(unsigned n=0;n<8;n++) startup_scr.bytes[n]=scr->bytes[n];
    startup_scr.erased_byte=scr->erased_byte;startup_scr.valid=1U;
    startup_scr_owner=c;sd_startup_proof.scr_valid=1U;
    sd_startup_proof.cache_owner=(uint32_t)(uintptr_t)c;
#endif
    CYCLE_MARK(SD_SCR_LATEST_DONE);
    return SD_OK;
}

#if SD_BUS_WIDTH == 4
int sd_read_scr(sd_card_t *c,sd_scr_t *scr)
{
    if(!c || !scr) return SD_ERR_ARGUMENT;
    scr->valid=0;scr->erased_byte=0;
    for(unsigned n=0;n<8;n++) scr->bytes[n]=0;
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    if(c->error) return (int)c->error;
#if SD_STARTUP_OPT
    if(startup_scr_owner==c && startup_scr.valid) {
        c->stage=SD_STAGE_SCR;
        for(unsigned n=0;n<8;n++) scr->bytes[n]=startup_scr.bytes[n];
        scr->erased_byte=startup_scr.erased_byte;scr->valid=1U;
        ++sd_startup_proof.scr_hits;
        return SD_OK;
    }
#endif
    return read_scr_selected(c,scr);
}
#if SD_STARTUP_OPT
int sd_read_scr_fresh(sd_card_t *c,sd_scr_t *scr)
{
    if(!c || !scr) return SD_ERR_ARGUMENT;
    startup_scr_invalidate();
    return sd_read_scr(c,scr);
}
#endif
#endif

int sd_erase_all(sd_card_t *c,uint32_t timeout_ms,sd_erase_t *proof)
{
    if(!c || !proof || timeout_ms<1000U || timeout_ms>600000U) return SD_ERR_ARGUMENT;
    volatile uint8_t *clear=(volatile uint8_t *)proof;
    for(unsigned i=0;i<sizeof(*proof);i++) clear[i]=0;
    proof->timeout_ms=timeout_ms;
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    if(c->error) return (int)c->error;
    c->stage=SD_STAGE_ERASE;
    if(!c->sector_count || c->sector_count>(1ULL<<32) ||
       (!(c->ocr&(1UL<<30)) && c->sector_count>(1ULL<<23))) return fault(c,SD_ERR_CAPACITY);
    uint32_t last=(uint32_t)(c->sector_count-1U);
    proof->last_lba=last;
    int result=ready(c);if(result) return result;
    if(X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    const uint32_t previous_hz=c->clock_hz,previous_clkcr=X->CLKCR;
    const uint32_t previous_timer=X->DTIMER;
#if SD_HIGH_SPEED
    if(previous_hz!=50000000U || !sd_high_speed_proof.qualified ||
#else
    if((previous_hz!=100000U && previous_hz!=12500000U && previous_hz!=25000000U) ||
#endif
       previous_clkcr!=((SD_KERNEL_HZ/(2U*previous_hz))|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|RUN_PHASE_BITS))
        return fault(c,SD_ERR_CLOCK);
    /* CMD38 returns R1b: its busy detector uses DTIMER even with CMDTRANS=0.
     * A previous SCR/read timer is only 2 s; timeout leaves DPSM stuck in Busy
     * awaiting CPSM Abort (RM0486 Table220). At 25 MHz, even UINT32_MAX cannot
     * represent 600 s. Use the qualified 100 kHz divider while idle and a
     * hardware bound 1 s beyond the software limit. Never rewrite it busy. */
    X->CLKCR=(SD_KERNEL_HZ/(2U*100000U))|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|RUN_PHASE_BITS;c->clock_hz=100000U;
    X->DCTRL=0;X->DLEN=0;X->ICR=DATA_FLAGS;
    X->DTIMER=(timeout_ms+1000U)*100U;
    if((result=delay_us(c,1000))) return result;
    uint32_t commands_before=c->command_count;
    c->media_idle=0;
    if((result=command(c,32,0,RESP_R1,0)) ||
       (result=command(c,33,(c->ocr&(1UL<<30))?last:last*512U,RESP_R1,0))) return result;
    /* Mark possible ownership before CMD38: even a lost response cannot prove
     * that the destructive operation did not start. No automatic retry. */
    proof->started=1U;
    result=command(c,38,0,RESP_R1,0);
    proof->command_count=c->command_count-commands_before;
    if(result) return result;
    uint32_t previous=DWT->CYCCNT;
    uint64_t elapsed=0;
    for(uint32_t i=0;i<600001U;i++) {
        sd_progress();
        result=command(c,13,c->rca,RESP_R1,0);
        uint32_t now=DWT->CYCCNT;elapsed+=(uint32_t)(now-previous);previous=now;
        proof->elapsed_ms=(uint32_t)(elapsed/400000ULL);
        proof->command_count=c->command_count-commands_before;
        proof->last_r1=c->last_r1;c->last_ready_r1=c->last_r1;c->gpioc_idr=C->IDR;
        if(result) return result;
        if((c->last_r1&0x1F00U)==0x900U && (c->gpioc_idr&DAT0) &&
           !(X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) && !X->IDMACTRL) {
            /* Restore only after both card and host are independently idle.
             * Uncertain/failed erase leaves the slow clock and ownership in
             * place; changing DTIMER in active DPSM would be illegal. */
            X->ICR=DATA_FLAGS;X->DTIMER=previous_timer;
            X->CLKCR=previous_clkcr;c->clock_hz=previous_hz;
            __DSB();
            c->media_idle=1U;proof->completed=1U;return SD_OK;
        }
        if(proof->elapsed_ms>=timeout_ms) break;
        if((result=delay_us(c,1000))) return result;
    }
    return fault(c,SD_ERR_NOT_READY);
}

static int stream_publish(sd_card_t *c,sd_stream_t *s,uint32_t bytes,uint32_t api_start)
{
    uint32_t available=0;s->publication_calls++;
    int result=s->publish(s->context,&available);
    if(result) {s->producer_error=(uint32_t)result;return fault(c,SD_ERR_PRODUCER);}
    /* A bounded camera fault check may take seconds. Recheck after it returns,
     * before accepting its new prefix or reading any more source/FIFO words. */
    if((uint32_t)(DWT->CYCCNT-api_start)>=1200000000U)
        return fault(c,SD_ERR_DATA_TIMEOUT);
    if(available>s->published_bytes && available<=bytes) {
        __DSB();s->published_bytes=available;
    } else if(available<s->published_bytes || available>bytes) {
        s->producer_error=0xFFFFFFFFU;return fault(c,SD_ERR_PRODUCER);
    }
    return SD_OK;
}

int sd_write_blocks_stream_preerase(sd_card_t *c,uint32_t lba,const void *buffer,
                                    uint32_t count,sd_stream_t *s)
{
    if(!s || !s->publish) return SD_ERR_ARGUMENT;
    s->mode=s->initial_available_bytes=s->published_bytes=s->queued_bytes=0;
    s->publication_calls=s->starved_polls=s->producer_error=0;
    s->producer_wait_cycles=s->max_wait_cycles=0;
    int result=dma_source_checks(c,lba,buffer,count);
    if(result) return result;
    if(count<2U || count>SD_DMA_PREERASE_MAX_SECTORS) return fault(c,SD_ERR_ARGUMENT);
#if SD_HIGH_SPEED
    if(c->clock_hz!=50000000UL || !sd_high_speed_proof.qualified) return fault(c,SD_ERR_CLOCK);
#else
    if(c->clock_hz!=12500000U && c->clock_hz!=25000000U) return fault(c,SD_ERR_CLOCK);
#endif
    const uint32_t flow_mask=SDMMC_CLKCR_HWFC_EN|SDMMC_CLKCR_BUSSPEED|
        SDMMC_CLKCR_SELCLKRX|SDMMC_CLKCR_DDR|SDMMC_CLKCR_WIDBUS|RUN_PHASE_MASK;
    if((X->CLKCR&flow_mask)!=(SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|RUN_PHASE_BITS)) return fault(c,SD_ERR_CLOCK);
    uint32_t api_start=DWT->CYCCNT,bytes=count*512U;
    CYCLE_MARK(SD_PRODUCER_WAIT_BEGIN);
    if((result=stream_publish(c,s,bytes,api_start))) return result;
    s->initial_available_bytes=s->published_bytes;
    for(uint32_t i=0;s->published_bytes<512U;i++) {
        sd_progress();s->starved_polls++;
        if((uint32_t)(DWT->CYCCNT-api_start)>=1200000000U) return fault(c,SD_ERR_DATA_TIMEOUT);
        if(i==POLL_LIMIT-1U) return fault(c,SD_ERR_TIMER);
        if((result=stream_publish(c,s,bytes,api_start))) return result;
    }
    s->producer_wait_cycles=DWT->CYCCNT-api_start;
    CYCLE_MARK(SD_PRODUCER_WAIT_DONE);
    s->max_wait_cycles=s->producer_wait_cycles;
    if(s->published_bytes==bytes) {
        s->mode=SD_STREAM_IDMA;
        CYCLE_MARK(SD_IDMA_SELECTED);
        result=sd_write_blocks_dma_preerase(c,lba,buffer,count);
        if(!result) s->queued_bytes=bytes;
        return result;
    }
    s->mode=SD_STREAM_PIO;
    CYCLE_MARK(SD_PIO_SELECTED);
    CYCLE_COUNT(SD_WRITE_TRANSFERS);
    CYCLE_COUNT(SD_PIO_TRANSFERS);
    CYCLE_MARK(SD_WRITE_READY_BEGIN);
    result=ready(c);if(result) return result;
    CYCLE_MARK(SD_WRITE_READY_DONE);
    if(X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    c->media_idle=0;
    if((result=preannounce(c,count))) return result;
    uint32_t start=DWT->CYCCNT,words=0,total=count*128U,sta=0;
    uint32_t waiting=0,wait_start=0;
    c->transfer_words=0;c->transfer_sta=0;
    CYCLE_MARK(SD_WRITE_SETUP_BEGIN);
    X->DCTRL=0;X->ICR=DATA_FLAGS;X->DTIMER=c->clock_hz*2U;X->DLEN=bytes;
    X->DCTRL=9U<<SDMMC_DCTRL_DBLOCKSIZE_Pos;
    CYCLE_MARK(SD_CMD25_BEGIN);
    CYCLE_COUNT(SD_CMD25_CALLS);
    result=command(c,25,(c->ocr&(1UL<<30))?lba:lba*512U,RESP_R1,1);
    if(!result) CYCLE_MARK(SD_CMD25_DONE);
    if(!result) for(uint32_t i=0;i<POLL_LIMIT;i++) {
        sta=X->STA;c->last_sta=sta;
        if(sta&DATA_ERRORS) {result=fault(c,SD_ERR_DATA);break;}
        if((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) {
            CYCLE_MARK(SD_DATAEND);
            break;
        }
        if(s->published_bytes<bytes) {
            sd_progress();
            if((result=stream_publish(c,s,bytes,api_start))) break;
            if((uint32_t)(DWT->CYCCNT-api_start)>=1200000000U) {
                result=fault(c,SD_ERR_DATA_TIMEOUT);break;
            }
        }
        uint32_t available_words=(s->published_bytes/512U)*128U;
        if(words>=available_words && words<total) {
            s->starved_polls++;
            if(!waiting) {waiting=1;wait_start=DWT->CYCCNT;}
        } else if(waiting) {
            uint32_t spent=DWT->CYCCNT-wait_start;
            s->producer_wait_cycles+=spent;
            if(spent>s->max_wait_cycles) s->max_wait_cycles=spent;
            waiting=0;
        }
        if((sta&SDMMC_STA_TXFIFOHE) && words<available_words) {
            for(uint32_t n=0;n<256U && words<available_words;n++) {
                uint32_t fifo_sta=X->STA;
                if((fifo_sta&(SDMMC_STA_TXFIFOF|DATA_ERRORS)) || !(fifo_sta&SDMMC_STA_DPSMACT)) break;
                X->FIFO=load_word((const uint8_t *)buffer+words*4U);words++;
            }
            s->queued_bytes=words*4U;
        }
        if((uint32_t)(DWT->CYCCNT-start)>=WRITE_TIMEOUT_CYCLES) {result=fault(c,SD_ERR_DATA_TIMEOUT);break;}
        if(i==POLL_LIMIT-1) result=fault(c,SD_ERR_TIMER);
        if(!(i&255U)) sd_progress();
    }
    if(waiting) {
        uint32_t spent=DWT->CYCCNT-wait_start;s->producer_wait_cycles+=spent;
        if(spent>s->max_wait_cycles) s->max_wait_cycles=spent;
    }
    c->transfer_words=words;c->transfer_sta=sta;c->transfer_cycles=DWT->CYCCNT-start;
    c->write_cycles+=c->transfer_cycles;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    if(!result && (words!=total || s->published_bytes!=bytes || !(sta&SDMMC_STA_DATAEND) ||
       (sta&(DATA_ERRORS|SDMMC_STA_DPSMACT)) || X->DCOUNT)) result=fault(c,SD_ERR_LENGTH);
    if(!result) {
        CYCLE_MARK(SD_WRITE_CLEANUP_BEGIN);
        CYCLE_MARK(SD_CMD12_BEGIN);
        CYCLE_COUNT(SD_CMD12_WRITE_CALLS);
        result=command(c,12,0,RESP_R1,0);
        if(!result) CYCLE_MARK(SD_CMD12_DONE);
    }
    if(result) {abort_transfer(c,0);return result;}
#if !SD_REVIEW_PROFILE
    X->DCTRL=0;X->ICR=DATA_FLAGS;
#endif
    CYCLE_MARK(SD_WRITE_FINAL_READY_BEGIN);
#if SD_REVIEW_PROFILE
    result=ready_after_transfer(c);
#else
    result=ready(c);
#endif
#if SD_REVIEW_PROFILE
    if(!result) { X->DCTRL=0;X->ICR=DATA_FLAGS; }
#endif
    if(!result) c->written_sectors+=count;
    if(!result) {
        CYCLE_MARK(SD_WRITE_FINAL_READY_DONE);
        CYCLE_MARK(SD_WRITE_DONE);
    }
    return result;
}

int sd_sync(sd_card_t *c)
{
    if (!c) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    c->stage=SD_STAGE_SYNC;
    CYCLE_MARK(SD_SYNC_LATEST_BEGIN);
    CYCLE_COUNT(SD_SYNC_CALLS);
    int result=ready(c);
    if (!result) CYCLE_MARK(SD_SYNC_LATEST_DONE);
    return result;
}

int sd_deinit(sd_card_t *c)
{
    if (!c) return SD_ERR_ARGUMENT;
#if SD_STARTUP_OPT
    startup_scr_invalidate();
#endif
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    SD_HOST_GUARD(c);
    CYCLE_MARK(SD_DEINIT_BEGIN);
    CYCLE_COUNT(SD_DEINIT_CALLS);
    int result=sd_sync(c);
    if (result) return result;
    c->stage=SD_STAGE_DEINIT;
    CYCLE_MARK(SD_DEINIT_RELEASE_BEGIN);
    X->MASK=0; X->DCTRL=0; X->CMD=0; X->IDMACTRL=0; X->POWER=0;
    R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
    R->AHB5ENCR=RCC_AHB5ENCR_SDMMC2ENC;
#if SD_HIGH_SPEED
    if(!sd_review_clock_release()) return fault(c,SD_ERR_CLOCK);
#else
    R->CCIPR8=(R->CCIPR8&~RCC_CCIPR8_SDMMC2SEL)|c->saved_sdmmc_mux;
#endif
    C->MODER&=~C_MASK;
    C->PUPDR=(C->PUPDR&~C_MASK)|(2UL<<4)|C_PULLS;
#if SD_BUS_WIDTH == 4
    E->MODER&=~(3UL<<8);
    E->PUPDR=(E->PUPDR&~(3UL<<8))|(1UL<<8);
#endif
    if (c->timer_owned) {
        DWT->CTRL=c->saved_dwt;
        CoreDebug->DEMCR=c->saved_demcr;
    }
    c->initialized=0; c->controller_owned=0; c->timer_owned=0;
    CYCLE_MARK(SD_DEINIT_DONE);
    return SD_OK;
}
