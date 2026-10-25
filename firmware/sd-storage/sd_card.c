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

#define X SDMMC2_S
#define R RCC_S
#define C GPIOC_S
#define E GPIOE_S
#define P PWR_S
#define CPU_CYCLES_US 400UL
#define HCLK_HZ 150000000UL
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

#if SD_GPIO_SPEED == 0
volatile sd_gpio_proof_t sd_gpio_proof;
_Static_assert(sizeof(sd_gpio_proof_t)==32U,"GPIO speed proof ABI");
#endif
#if SD_FIXED_COMPENSATION
volatile sd_compensation_proof_t sd_compensation_proof;
_Static_assert(sizeof(sd_compensation_proof_t)==32U,"compensation proof ABI");
#endif

__attribute__((weak)) void sd_progress(void)
{
}

static int fault(sd_card_t *c, uint32_t error)
{
    if (!c->error) {
        c->error=error;
        c->error_stage=c->stage;
        c->error_command=c->last_command;
        c->error_sta=c->last_sta;
    }
    return (int)error;
}

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

static int command(sd_card_t *c, uint32_t index, uint32_t argument,
                   enum response response, uint32_t data)
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
    if (index==12) errors&=~(1UL<<31);
    if (response==RESP_R1 && (X->RESP1&errors)) return fault(c,SD_ERR_CARD);
    if (response==RESP_R6 && (X->RESP1&0xE000UL)) return fault(c,SD_ERR_CARD);
    return SD_OK;
}

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
            for (uint32_t n=0;n<64;++n) {
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
    result=command(c,index,(c->ocr&(1UL<<30)) ? lba : lba*512UL,RESP_R1,1);
    if (result) {
        abort_transfer(c,!writing);
        return result;
    }
    for (uint32_t i=0;i<POLL_LIMIT;++i) {
        sta=X->STA;
        c->last_sta=sta;
        if (sta&DATA_ERRORS) { result=fault(c,SD_ERR_DATA); break; }
        /* Table220: DATAEND is final complete/CRC-good; TX also includes the
         * last block's busy completion. DBCKEND is not required at final end.
         * Do not read an inactive FIFO merely because RXFIFOE has deasserted. */
        if ((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) break;
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
    if (!result && count>1) result=command(c,12,0,RESP_R1,0);
    if (result) {
        abort_transfer(c,!writing);
        return result;
    }
    X->DCTRL=0;
    X->ICR=DATA_FLAGS;
    result=ready(c);
    if (result) return result;
    if (writing) c->written_sectors+=count;
    else c->read_sectors+=count;
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
    int result=command(c,55,c->rca,RESP_R1,0);
    if(result) return result;
    if(!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    result=command(c,23,count,RESP_R1,0);
    if(result) return result;
    if(!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    return SD_OK;
}

static int transfer_dma_write(sd_card_t *c, uint32_t lba,
                              const uint8_t *buffer, uint32_t count, sd_dma_wait_t *wait,
                              uint32_t preerase)
{
    int result=ready(c);
    if (result) return result;
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
    X->DCTRL=0;
    X->ICR=DMA_FLAGS;
    X->DTIMER=c->clock_hz*2UL;
    X->DLEN=count*SD_SECTOR_BYTES;
    X->DCTRL=9UL<<SDMMC_DCTRL_DBLOCKSIZE_Pos;
    X->IDMABASER=(uint32_t)(uintptr_t)buffer;
    /* No CPU writes or dirty cache lines may remain unpublished before DMA. */
    __DSB();
    X->IDMACTRL=SDMMC_IDMA_IDMAEN;
    result=command(c,count==1 ? 24UL : 25UL,
                   (c->ocr&(1UL<<30)) ? lba : lba*512UL,RESP_R1,1);
    if (!result) {
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
            if ((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) break;
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
    /* DPSM is inactive: release DMA ownership before any subsequent command. */
    X->IDMACTRL=0;
    __DSB();
    c->transfer_words=count*128UL;
    if (count>1) result=command(c,12,0,RESP_R1,0);
    if (result) {
        abort_dma_write(c);
        return result;
    }
    X->DCTRL=0;
    X->ICR=DMA_FLAGS;
    result=ready(c);
    if (!result) c->written_sectors+=count;
    return result;
}

static int identify(sd_card_t *c)
{
    int result;
    c->stage=SD_STAGE_IDENTIFY;
    if ((result=command(c,0,0,RESP_NONE,0)) ||
        (result=command(c,8,0x1AAUL,RESP_R7,0))) return result;
    if ((X->RESP1&0xFFFUL)!=0x1AAUL) return fault(c,SD_ERR_UNSUPPORTED);
    uint32_t start=DWT->CYCCNT;
    for (uint32_t i=0;i<2000;++i) {
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
    c->stage=SD_STAGE_SELECT;
    if ((result=command(c,7,c->rca,RESP_R1,0)) || (result=ready(c))) return result;
    if (!(c->ocr&(1UL<<30)) && (result=command(c,16,512,RESP_R1,0))) return result;
    return SD_OK;
}

int sd_init(sd_card_t *c, uint32_t max_hz)
{
    if (!c) return SD_ERR_ARGUMENT;
    if (c->initialized || c->controller_owned) return SD_ERR_STATE;
#if SD_BUS_WIDTH == 4
    volatile uint8_t *width_clear=(volatile uint8_t *)&sd_bus_width_proof;
    for (size_t i=0;i<sizeof(sd_bus_width_proof);++i) width_clear[i]=0;
    sd_bus_width_proof.requested_width=4U;
#endif
#if SD_GPIO_SPEED == 0
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
    if (max_hz!=100000UL && max_hz!=12500000UL && max_hz!=25000000UL)
        return fault(c,SD_ERR_ARGUMENT);
#if SD_FIXED_COMPENSATION
    if (max_hz!=25000000UL) return fault(c,SD_ERR_ARGUMENT);
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
#if SD_GPIO_SPEED == 0
    sd_gpio_proof.c_before=C->OSPEEDR;
    sd_gpio_proof.e_before=E->OSPEEDR;
#endif
    C->BSRR=1UL<<(2+16);
    C->OTYPER&=~C_PINS;
    C->MODER&=~C_MASK;
    C->PUPDR=(C->PUPDR&~C_MASK)|C_PULLS;
#if SD_GPIO_SPEED == 3
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|C_MASK;
#else
    C->OSPEEDR&=~C_MASK;
    sd_gpio_proof.c_after=C->OSPEEDR;
    if ((sd_gpio_proof.c_after&C_MASK) ||
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
    if ((result=delay_us(c,1000))) return result;
    c->gpioc_idr=C->IDR; c->gpioe_idr=E->IDR;
    if ((c->gpioc_idr&C_IDLE_PINS)!=C_IDLE_PINS ||
        !(c->gpioe_idr&(1UL<<4))) return fault(c,SD_ERR_GPIO);
    c->saved_sdmmc_mux=R->CCIPR8&RCC_CCIPR8_SDMMC2SEL;
    R->CCIPR8&=~RCC_CCIPR8_SDMMC2SEL;
    R->AHB5ENSR=RCC_AHB5ENSR_SDMMC2ENS;
    (void)R->AHB5ENR;
    R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
    __DSB();
    c->controller_owned=1;
    X->MASK=0; X->POWER=0; X->DCTRL=0; X->IDMACTRL=0; X->CMD=0;
    X->CLKCR=750UL|SDMMC_CLKCR_HWFC_EN;
    C->AFR[0]=(C->AFR[0]&~C_AF_MASK)|C_AF_BITS;
    C->MODER=(C->MODER&~C_MASK)|C_MODES;
    if ((C->MODER&C_MASK)!=C_MODES ||
        (C->AFR[0]&C_AF_MASK)!=C_AF_BITS ||
        (E->MODER&(3UL<<8)) || (E->PUPDR&(3UL<<8))!=(1UL<<8))
        return fault(c,SD_ERR_GPIO);
    X->POWER=SDMMC_POWER_PWRCTRL;
    c->clock_hz=100000UL;
    if ((result=delay_us(c,10000)) || (result=identify(c))) return result;
    X->CLKCR=(HCLK_HZ/(2*max_hz))|SDMMC_CLKCR_HWFC_EN;
    c->clock_hz=max_hz;
    if ((result=delay_us(c,1000)) || (result=ready(c))) return result;
#if SD_BUS_WIDTH == 4
    /* SCR data is still received on DAT0. Require both mandatory one-bit and
     * requested four-bit capability; never silently run a four-bit build in
     * one-bit mode. CMD6 here is ACMD6 (argument2), not high-speed CMD6. */
    sd_scr_t scr;
    if ((result=read_scr_selected(c,&scr))) return result;
    c->stage=SD_STAGE_BUS_WIDTH;
    sd_bus_width_proof.scr_widths=scr.bytes[1]&15U;
    if ((scr.bytes[1]&5U)!=5U) return fault(c,SD_ERR_UNSUPPORTED);
    c->media_idle=0;
    if ((result=command(c,55,c->rca,RESP_R1,0))) return result;
    if (!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    result=command(c,6,2,RESP_R1,0);
    sd_bus_width_proof.acmd6_r1=c->last_r1;
    if (result) return result;
    if (!(c->last_r1&(1UL<<5))) return fault(c,SD_ERR_UNSUPPORTED);
    sd_bus_width_proof.acmd6_accepted=1U;
    if ((X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)) || X->IDMACTRL)
        return fault(c,SD_ERR_CONTROLLER_BUSY);
    /* An uncertain ACMD6 response retains ownership and does not guess which
     * width the card selected. Only successful negotiation reaches this. */
    E->OTYPER&=~(1UL<<4);
#if SD_GPIO_SPEED == 3
    E->OSPEEDR=(E->OSPEEDR&~(3UL<<8))|(3UL<<8);
#else
    E->OSPEEDR&=~(3UL<<8);
    sd_gpio_proof.e_after=E->OSPEEDR;
    if ((sd_gpio_proof.e_after&(3UL<<8)) ||
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
#endif
#if SD_GPIO_SPEED == 0
    sd_gpio_proof.c_after=C->OSPEEDR; sd_gpio_proof.e_after=E->OSPEEDR;
    if ((sd_gpio_proof.c_after&sd_gpio_proof.c_mask) ||
            (sd_gpio_proof.e_after&sd_gpio_proof.e_mask) ||
            ((sd_gpio_proof.c_before^sd_gpio_proof.c_after)&~sd_gpio_proof.c_mask) ||
            ((sd_gpio_proof.e_before^sd_gpio_proof.e_after)&~sd_gpio_proof.e_mask))
        return fault(c,SD_ERR_GPIO);
    sd_gpio_proof.applied=1U;
#endif
    c->initialized=1;
    c->init_cycles=DWT->CYCCNT-start;
    return SD_OK;
}

static int block_request(sd_card_t *c, uint32_t lba, void *buffer,
                         uint32_t count, uint32_t writing)
{
    if (!c || !buffer || !count) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
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

int sd_read_blocks(sd_card_t *c, uint32_t lba, void *buffer, uint32_t count)
{
    return block_request(c,lba,buffer,count,0);
}

int sd_write_blocks(sd_card_t *c, uint32_t lba, const void *buffer, uint32_t count)
{
    return block_request(c,lba,(void *)buffer,count,1);
}

static int dma_source_checks(sd_card_t *c,uint32_t lba,const void *buffer,uint32_t count)
{
    if (!c || !buffer || !count) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
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
    if (c->clock_hz!=100000UL && c->clock_hz!=12500000UL && c->clock_hz!=25000000UL)
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
    if(c->error) return (int)c->error;
#endif
    c->stage=SD_STAGE_SCR;
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
    return SD_OK;
}

#if SD_BUS_WIDTH == 4
int sd_read_scr(sd_card_t *c,sd_scr_t *scr)
{
    if(!c || !scr) return SD_ERR_ARGUMENT;
    scr->valid=0;scr->erased_byte=0;
    for(unsigned n=0;n<8;n++) scr->bytes[n]=0;
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    if(c->error) return (int)c->error;
    return read_scr_selected(c,scr);
}
#endif

int sd_erase_all(sd_card_t *c,uint32_t timeout_ms,sd_erase_t *proof)
{
    if(!c || !proof || timeout_ms<1000U || timeout_ms>600000U) return SD_ERR_ARGUMENT;
    volatile uint8_t *clear=(volatile uint8_t *)proof;
    for(unsigned i=0;i<sizeof(*proof);i++) clear[i]=0;
    proof->timeout_ms=timeout_ms;
    if(!c->initialized || !c->controller_owned) return SD_ERR_STATE;
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
    if((previous_hz!=100000U && previous_hz!=12500000U && previous_hz!=25000000U) ||
       previous_clkcr!=((HCLK_HZ/(2U*previous_hz))|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS))
        return fault(c,SD_ERR_CLOCK);
    /* CMD38 returns R1b: its busy detector uses DTIMER even with CMDTRANS=0.
     * A previous SCR/read timer is only 2 s; timeout leaves DPSM stuck in Busy
     * awaiting CPSM Abort (RM0486 Table220). At 25 MHz, even UINT32_MAX cannot
     * represent 600 s. Use the qualified 100 kHz divider while idle and a
     * hardware bound 1 s beyond the software limit. Never rewrite it busy. */
    X->CLKCR=750U|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS;c->clock_hz=100000U;
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
    if(c->clock_hz!=12500000U && c->clock_hz!=25000000U) return fault(c,SD_ERR_CLOCK);
    const uint32_t flow_mask=SDMMC_CLKCR_HWFC_EN|SDMMC_CLKCR_BUSSPEED|
        SDMMC_CLKCR_SELCLKRX|SDMMC_CLKCR_DDR|SDMMC_CLKCR_WIDBUS;
    if((X->CLKCR&flow_mask)!=(SDMMC_CLKCR_HWFC_EN|WIDTH_BITS)) return fault(c,SD_ERR_CLOCK);
    uint32_t api_start=DWT->CYCCNT,bytes=count*512U;
    if((result=stream_publish(c,s,bytes,api_start))) return result;
    s->initial_available_bytes=s->published_bytes;
    for(uint32_t i=0;s->published_bytes<512U;i++) {
        sd_progress();s->starved_polls++;
        if((uint32_t)(DWT->CYCCNT-api_start)>=1200000000U) return fault(c,SD_ERR_DATA_TIMEOUT);
        if(i==POLL_LIMIT-1U) return fault(c,SD_ERR_TIMER);
        if((result=stream_publish(c,s,bytes,api_start))) return result;
    }
    s->producer_wait_cycles=DWT->CYCCNT-api_start;
    s->max_wait_cycles=s->producer_wait_cycles;
    if(s->published_bytes==bytes) {
        s->mode=SD_STREAM_IDMA;
        result=sd_write_blocks_dma_preerase(c,lba,buffer,count);
        if(!result) s->queued_bytes=bytes;
        return result;
    }
    s->mode=SD_STREAM_PIO;
    result=ready(c);if(result) return result;
    if(X->IDMACTRL) return fault(c,SD_ERR_CONTROLLER_BUSY);
    c->media_idle=0;
    if((result=preannounce(c,count))) return result;
    uint32_t start=DWT->CYCCNT,words=0,total=count*128U,sta=0;
    uint32_t waiting=0,wait_start=0;
    c->transfer_words=0;c->transfer_sta=0;
    X->DCTRL=0;X->ICR=DATA_FLAGS;X->DTIMER=c->clock_hz*2U;X->DLEN=bytes;
    X->DCTRL=9U<<SDMMC_DCTRL_DBLOCKSIZE_Pos;
    result=command(c,25,(c->ocr&(1UL<<30))?lba:lba*512U,RESP_R1,1);
    if(!result) for(uint32_t i=0;i<POLL_LIMIT;i++) {
        sta=X->STA;c->last_sta=sta;
        if(sta&DATA_ERRORS) {result=fault(c,SD_ERR_DATA);break;}
        if((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) break;
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
    if(!result) result=command(c,12,0,RESP_R1,0);
    if(result) {abort_transfer(c,0);return result;}
    X->DCTRL=0;X->ICR=DATA_FLAGS;
    result=ready(c);if(!result) c->written_sectors+=count;
    return result;
}

int sd_sync(sd_card_t *c)
{
    if (!c) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    c->stage=SD_STAGE_SYNC;
    return ready(c);
}

int sd_deinit(sd_card_t *c)
{
    if (!c) return SD_ERR_ARGUMENT;
    if (!c->initialized || !c->controller_owned) return SD_ERR_STATE;
    int result=sd_sync(c);
    if (result) return result;
    c->stage=SD_STAGE_DEINIT;
    X->MASK=0; X->DCTRL=0; X->CMD=0; X->IDMACTRL=0; X->POWER=0;
    R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
    R->AHB5ENCR=RCC_AHB5ENCR_SDMMC2ENC;
    R->CCIPR8=(R->CCIPR8&~RCC_CCIPR8_SDMMC2SEL)|c->saved_sdmmc_mux;
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
    return SD_OK;
}
