/* CMSIS-only native SDMMC2 storage driver, derived from the qualified read-only
 * smoke helper. PC2/3/4 AF11 = CLK/CMD/DAT0; PE4 = unused DAT3 input/pull-up.
 *
 * Sources: RM0486 Rev4 Table220 and section30.6.2; pinned CubeN6 HAL_SD_ReadBlocks,
 * HAL_SD_WriteBlocks and LL SDMMC_CmdStopTransfer. Open-ended CMD18/CMD25 use
 * DATAEND followed by CMD12/CMDSTOP, then an explicit ready/TRANSFER check.
 *
 * No hardcoded data/code RAM addresses, HAL tick dependency, DMA, interrupts,
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
#define R1_ERRORS 0xFDFFE008UL
#define C_MASK ((3UL<<4)|(3UL<<6)|(3UL<<8))
#define C_PINS ((1UL<<2)|(1UL<<3)|(1UL<<4))
#define DAT0 (1UL<<4)

_Static_assert(SDMMC2_BASE_S==0x58026800UL, "SDMMC2 address");
_Static_assert(offsetof(SDMMC_TypeDef,FIFO)==0x80, "FIFO offset");
_Static_assert(SD_MAX_TRANSFER_SECTORS*SD_SECTOR_BYTES<=0x1FFFFFFUL, "DLEN");

enum response { RESP_NONE, RESP_R1, RESP_R2, RESP_R3, RESP_R6, RESP_R7 };

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
            !(X->STA&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT))) {
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
            if ((sta&SDMMC_STA_TXFIFOHE) && total-words>=16UL) {
                for (uint32_t n=0;n<16;++n) {
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
    volatile uint8_t *p=(volatile uint8_t *)c;
    for (size_t i=0;i<sizeof(*c);++i) p[i]=0;
    c->stage=SD_STAGE_PREFLIGHT;
    if (max_hz!=100000UL && max_hz!=12500000UL && max_hz!=25000000UL)
        return fault(c,SD_ERR_ARGUMENT);
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
    if (P->SVMCR2&PWR_SVMCR2_VDDIO5VRSEL) return fault(c,SD_ERR_VOLTAGE);
    for (uint32_t pin=2;pin<=4;++pin) {
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
    C->BSRR=1UL<<(2+16);
    C->OTYPER&=~C_PINS;
    C->MODER&=~C_MASK;
    C->PUPDR=(C->PUPDR&~C_MASK)|(1UL<<6)|(1UL<<8);
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|C_MASK;
    E->MODER&=~(3UL<<8);
    E->PUPDR=(E->PUPDR&~(3UL<<8))|(1UL<<8);
    P->SVMCR2|=PWR_SVMCR2_VDDIO5SV;
    c->vddio5_control=P->SVMCR2;
    if ((result=delay_us(c,1000))) return result;
    c->gpioc_idr=C->IDR; c->gpioe_idr=E->IDR;
    if ((c->gpioc_idr&((1UL<<3)|DAT0))!=((1UL<<3)|DAT0) ||
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
    X->CLKCR=750UL;
    C->AFR[0]=(C->AFR[0]&~(0xFFFUL<<8))|(0xBBBUL<<8);
    C->MODER=(C->MODER&~C_MASK)|(2UL<<4)|(2UL<<6)|(2UL<<8);
    if ((C->MODER&C_MASK)!=((2UL<<4)|(2UL<<6)|(2UL<<8)) ||
        (C->AFR[0]&(0xFFFUL<<8))!=(0xBBBUL<<8) ||
        (E->MODER&(3UL<<8)) || (E->PUPDR&(3UL<<8))!=(1UL<<8))
        return fault(c,SD_ERR_GPIO);
    X->POWER=SDMMC_POWER_PWRCTRL;
    c->clock_hz=100000UL;
    if ((result=delay_us(c,10000)) || (result=identify(c))) return result;
    X->CLKCR=HCLK_HZ/(2*max_hz);
    c->clock_hz=max_hz;
    if ((result=delay_us(c,1000)) || (result=ready(c))) return result;
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
    C->PUPDR=(C->PUPDR&~C_MASK)|(2UL<<4)|(1UL<<6)|(1UL<<8);
    if (c->timer_owned) {
        DWT->CTRL=c->saved_dwt;
        CoreDebug->DEMCR=c->saved_demcr;
    }
    c->initialized=0; c->controller_owned=0; c->timer_owned=0;
    return SD_OK;
}
