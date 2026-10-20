/* Read-only bench helper: no flash writes, card writes, filesystem changes,
 * DMA, interrupts, 1.8 V switch, or wide-bus command. Native SDMMC2, one bit.
 * Requires a verified, awake, uncached early recovery park and idle storage.
 * CPU/PLL/XSPI clocks and the recovery-prefix bytes are never modified.
 */
#include <stddef.h>
#include "stm32n657xx.h"

#define S ((volatile uint32_t *)0x341B4100UL)
#define REQUEST ((volatile uint32_t *)0x341B4000UL)
#define RECORDS ((volatile uint32_t *)0x341B4400UL)
#define DATA ((volatile uint32_t *)0x341C0000UL)
#define X SDMMC2_S
#define R RCC_S
#define C GPIOC_S
#define E GPIOE_S
#define P PWR_S
#define CPU_HZ 400000000UL
#define HCLK_HZ 150000000UL
#define CMD_FLAGS (SDMMC_STA_CCRCFAIL | SDMMC_STA_CTIMEOUT | SDMMC_STA_CMDREND | SDMMC_STA_CMDSENT | SDMMC_STA_BUSYD0END)
#define DATA_ERRORS (SDMMC_STA_DCRCFAIL | SDMMC_STA_DTIMEOUT | SDMMC_STA_RXOVERR)
#define DATA_FLAGS (DATA_ERRORS | SDMMC_STA_DATAEND | SDMMC_STA_DBCKEND | SDMMC_STA_DABORT)
#define R1_ERRORS 0xFDFFE008UL
#define C_MASK ((3UL << 4) | (3UL << 6) | (3UL << 8))
#define C_PINS ((1UL << 2) | (1UL << 3) | (1UL << 4))
#define RECORD_WORDS 12UL
#define RECORD_COUNT 64UL

_Static_assert(SDMMC2_BASE_S == 0x58026800UL, "SDMMC2 address");
_Static_assert(offsetof(SDMMC_TypeDef, FIFO) == 0x80, "FIFO offset");

enum { MAGIC, SCHEMA, WORDS, RESULT, STAGE, OLD_MSP, OLD_MSPLIM,
       CONTROL, IPSR, CPU_CCR, CFGR1, CFGR2, PLL1CFGR1, PLL1CFGR2, PLL1CFGR3,
       IC1CFGR, IC2CFGR, DIVENR, AHB4ENR, AHB5ENR, AHB5RSTR, CCIPR8,
       PWR_SVMCR2_BEFORE, PWR_SVMCR2_AFTER, GPIOC_MODER_BEFORE, GPIOC_IDR_BEFORE,
       GPIOE_MODER_BEFORE, GPIOE_IDR_BEFORE, GPIOC_IDR_SETTLED, GPIOE_IDR_SETTLED,
       GPIOC_MODER_AF, GPIOC_AFR0, GPIOC_PUPDR, GPIOE_MODER_INPUT, GPIOE_PUPDR,
       DWT_BEGIN, DWT_END, REQUEST_MAX_HZ, KERNEL_HZ, CURRENT_SD_HZ, CLKCR,
       LAST_COMMAND, LAST_ARGUMENT, LAST_STA, LAST_RESPCMD, LAST_R1, COMMAND_COUNT,
       RECORDS_USED, RECORDS_DROPPED, OCR, RCA, CID0, CID1, CID2, CID3,
       CSD0, CSD1, CSD2, CSD3, CSD_VERSION, SECTOR_COUNT_LOW, SECTOR_COUNT_HIGH,
       READ_COUNT, READ_WORDS, READ_CYCLES, READ_STA, READ_CRC0, READ_CRC1,
       READ_CRC2, READ_CRC3, READ_CRC4, READ_CRC5, READ_MATCH_MASK, CARD_STATUS,
       FAIL_STAGE, FAIL_COMMAND, FAIL_STA, CLEANUP, STATUS_WORDS };
enum { RUNNING=0x52554E4EUL, DONE=0, BAD_REQUEST=1, BAD_CONTEXT=2,
       BAD_CACHE=3, BAD_CLOCK=4, SD_ALREADY_OWNED=5, BAD_VDDIO5_RANGE=6,
       BAD_GPIO_OWNER=7, NO_TIMER=8, TIMER_STOPPED=9, BAD_GPIO_READBACK=10,
       CMD_TIMEOUT=11, CMD_CRC=12, CMD_INDEX=13, CARD_ERROR=14,
       BAD_CMD8=15, CARD_NOT_READY=16, BAD_RCA=17, BAD_CSD=18,
       READ_ERROR=19, READ_TIMEOUT=20, SHORT_READ=21, READ_MISMATCH=22,
       LINES_NOT_HIGH=23 };
enum { PREFLIGHT=1, GPIO_SETUP=2, POWERUP=3, IDENTIFY=4, SELECT=5,
       READ_SLOW=6, READ_MEDIUM=7, READ_FAST=8, FINISH=9 };
enum response { NONE, R1, R2, R3, R6, R7 };
struct context { uint32_t result, configured, timer, old_demcr, old_dwt; };

/* GCC may lower zero-initialized stack aggregates to memset in freestanding
 * code. This local implementation has no runtime/library dependency. */
void *memset(void *destination, int value, size_t length)
{
    volatile unsigned char *p=destination;
    while (length--) *p++=(unsigned char)value;
    return destination;
}

static void fail(struct context *c, uint32_t code)
{
    if (c->result == DONE) {
        c->result=code; S[FAIL_STAGE]=S[STAGE];
        S[FAIL_COMMAND]=S[LAST_COMMAND]; S[FAIL_STA]=S[LAST_STA];
    }
}

static int wait_us(struct context *c, uint32_t us)
{
    uint32_t start=DWT->CYCCNT;
    for (uint32_t n=0; n<8000000UL; ++n) {
        if ((uint32_t)(DWT->CYCCNT-start) >= us*400UL) return 1;
    }
    fail(c,TIMER_STOPPED); return 0;
}

static void record(uint32_t index, uint32_t argument, uint32_t sta, uint32_t begin)
{
    S[LAST_STA]=sta; S[LAST_RESPCMD]=X->RESPCMD; S[LAST_R1]=X->RESP1;
    S[COMMAND_COUNT]++;
    uint32_t n=S[RECORDS_USED];
    if (n < RECORD_COUNT) {
        volatile uint32_t *p=RECORDS+n*RECORD_WORDS;
        p[0]=S[STAGE]; p[1]=index; p[2]=argument; p[3]=sta;
        p[4]=X->RESPCMD; p[5]=X->RESP1; p[6]=X->RESP2;
        p[7]=X->RESP3; p[8]=X->RESP4;
        p[9]=DWT->CYCCNT-begin; p[10]=C->IDR; p[11]=E->IDR;
        S[RECORDS_USED]=n+1;
    } else S[RECORDS_DROPPED]++;
}

/* The full executable's only command indices are the read/identification
 * whitelist below. No generic host-provided card opcode is accepted. */
static int allowed(uint32_t index)
{
    return index==0 || index==2 || index==3 || index==7 || index==8 ||
           index==9 || index==13 || index==16 || index==17 ||
           index==41 || index==55;
}

static int command(struct context *c, uint32_t index, uint32_t argument,
                   enum response response, int data)
{
    uint32_t begin=DWT->CYCCNT, sta=0;
    S[LAST_COMMAND]=index; S[LAST_ARGUMENT]=argument;
    if (!allowed(index) || (data && index!=17)) {
        fail(c,BAD_REQUEST); return 0;
    }
    X->ICR=CMD_FLAGS;
    X->ARG=argument;
    X->CMD=index | SDMMC_CMD_CPSMEN | (data ? SDMMC_CMD_CMDTRANS : 0) |
           (response==R2 ? SDMMC_CMD_WAITRESP :
            response==NONE ? 0 : SDMMC_CMD_WAITRESP_0);
    for (uint32_t n=0; n<8000000UL; ++n) {
        sta=X->STA;
        uint32_t terminal=response==NONE ? SDMMC_STA_CMDSENT :
            SDMMC_STA_CMDREND|SDMMC_STA_CCRCFAIL|SDMMC_STA_CTIMEOUT;
        if ((sta&terminal) && !(sta&SDMMC_STA_CPSMACT)) break;
        if ((uint32_t)(DWT->CYCCNT-begin) >= 100000UL*400UL) {
            record(index,argument,sta,begin); fail(c,CMD_TIMEOUT); return 0;
        }
        if (n==7999999UL) {
            record(index,argument,sta,begin); fail(c,TIMER_STOPPED); return 0;
        }
    }
    record(index,argument,sta,begin);
    X->ICR=CMD_FLAGS;
    if (sta&SDMMC_STA_CTIMEOUT) { fail(c,CMD_TIMEOUT); return 0; }
    if ((sta&SDMMC_STA_CCRCFAIL) && response!=R3) { fail(c,CMD_CRC); return 0; }
    if ((response==R1 || response==R6 || response==R7) &&
        (X->RESPCMD & 63UL)!=index) { fail(c,CMD_INDEX); return 0; }
    if (response==R1 && (X->RESP1&R1_ERRORS)) { fail(c,CARD_ERROR); return 0; }
    if (response==R6 && (X->RESP1&0xE000UL)) { fail(c,CARD_ERROR); return 0; }
    return 1;
}

static int ready(struct context *c)
{
    uint32_t begin=DWT->CYCCNT;
    for (uint32_t i=0; i<1000; ++i) {
        if (!command(c,13,S[RCA],R1,0)) return 0;
        S[CARD_STATUS]=X->RESP1;
        if ((S[CARD_STATUS]&0x1F00UL)==0x900UL && (C->IDR&(1UL<<4))) return 1;
        if ((uint32_t)(DWT->CYCCNT-begin)>400000000UL) break;
        if (!wait_us(c,1000)) return 0;
    }
    fail(c,CARD_NOT_READY); return 0;
}

static uint32_t crc32(volatile uint32_t *p)
{
    volatile uint8_t *bytes=(volatile uint8_t *)p;
    uint32_t crc=0xFFFFFFFFUL;
    for (uint32_t i=0;i<512;++i) {
        crc^=bytes[i];
        for (uint32_t j=0;j<8;++j) crc=(crc>>1)^((crc&1) ? 0xEDB88320UL : 0);
    }
    return ~crc;
}

static int read_sector(struct context *c, uint32_t sector, uint32_t buffer)
{
    uint32_t count=0, sta=0, begin=DWT->CYCCNT;
    volatile uint32_t *out=DATA+128UL*buffer;
    for (uint32_t i=0;i<128;++i) out[i]=0xCCCCCCCCUL;
    S[READ_WORDS]=0;
    X->DCTRL=0; X->ICR=DATA_FLAGS;
    X->DTIMER=S[CURRENT_SD_HZ]; /* One second in SD clocks; DWT backstop too. */
    X->DLEN=512;
    X->DCTRL=(9UL<<SDMMC_DCTRL_DBLOCKSIZE_Pos)|SDMMC_DCTRL_DTDIR;
    if (!command(c,17,(S[OCR]&(1UL<<30)) ? sector : sector*512UL,R1,1)) return 0;
    for (uint32_t n=0;n<8000000UL;++n) {
        sta=X->STA;
        S[LAST_STA]=sta;
        if (sta&DATA_ERRORS) { fail(c,READ_ERROR); break; }
        /* RM0486 Table 220: RX DATAEND is the complete, CRC-good transfer
         * with DATACOUNT=0 and FIFO empty (Wait_R -> Idle). DBCKEND is for
         * nonfinal RWSTART suspension; it is not a final CMD17 requirement.
         * Test completion before reading FIFO: its idle flags need not
         * retain the RXFIFOE indication observed during an active transfer. */
        if ((sta&SDMMC_STA_DATAEND) && !(sta&SDMMC_STA_DPSMACT)) break;
        if (!(sta&SDMMC_STA_RXFIFOE) && count<128) out[count++]=X->FIFO;
        if ((uint32_t)(DWT->CYCCNT-begin)>=400000000UL) { fail(c,READ_TIMEOUT); break; }
        if (n==7999999UL) fail(c,TIMER_STOPPED);
    }
    S[READ_WORDS]=count; S[READ_STA]=sta;
    S[READ_CYCLES]=DWT->CYCCNT-begin;
    X->CMD&=~SDMMC_CMD_CMDTRANS;
    X->DCTRL=0;
    X->ICR=DATA_FLAGS;
    if (c->result!=DONE) return 0;
    if (count!=128 || !(sta&SDMMC_STA_DATAEND) ||
        (sta&SDMMC_STA_DPSMACT) || (sta&DATA_ERRORS)) {
        fail(c,SHORT_READ); return 0;
    }
    S[READ_CRC0+buffer]=crc32(out);
    S[READ_COUNT]++;
    if (buffer>=2) {
        volatile uint32_t *baseline=DATA+128UL*(buffer&1UL);
        for (uint32_t i=0;i<128;++i) {
            if (out[i]!=baseline[i]) { fail(c,READ_MISMATCH); return 0; }
        }
        S[READ_MATCH_MASK]|=1UL<<buffer;
    }
    return ready(c);
}

static int preflight(struct context *c)
{
    S[CONTROL]=__get_CONTROL(); S[IPSR]=__get_IPSR(); S[CPU_CCR]=SCB->CCR;
    if (S[CONTROL] || S[IPSR]) { fail(c,BAD_CONTEXT); return 0; }
    if (S[CPU_CCR]&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) { fail(c,BAD_CACHE); return 0; }
    S[CFGR1]=R->CFGR1; S[CFGR2]=R->CFGR2;
    S[PLL1CFGR1]=R->PLL1CFGR1; S[PLL1CFGR2]=R->PLL1CFGR2; S[PLL1CFGR3]=R->PLL1CFGR3;
    S[IC1CFGR]=R->IC1CFGR; S[IC2CFGR]=R->IC2CFGR; S[DIVENR]=R->DIVENR;
    if (S[CFGR1]!=0x33330000UL || S[CFGR2]!=0x00100000UL ||
        S[PLL1CFGR1]!=0x00404B00UL || S[PLL1CFGR2] ||
        S[PLL1CFGR3]!=0x49000005UL ||
        (S[IC1CFGR]&(RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))!=0x20000UL ||
        (S[IC2CFGR]&(RCC_IC2CFGR_IC2INT|RCC_IC2CFGR_IC2SEL))!=0x30000UL ||
        !(S[DIVENR]&RCC_DIVENR_IC2EN) || (R->HSICFGR&RCC_HSICFGR_HSIDIV)) {
        fail(c,BAD_CLOCK); return 0;
    }
    S[KERNEL_HZ]=HCLK_HZ;
    S[AHB4ENR]=R->AHB4ENR; S[AHB5ENR]=R->AHB5ENR; S[AHB5RSTR]=R->AHB5RSTR;
    S[CCIPR8]=R->CCIPR8;
    if (S[AHB5ENR]&RCC_AHB5ENR_SDMMC2EN) { fail(c,SD_ALREADY_OWNED); return 0; }
    R->AHB4ENSR=RCC_AHB4ENSR_PWRENS|RCC_AHB4ENSR_GPIOCENS|RCC_AHB4ENSR_GPIOEENS;
    (void)R->AHB4ENR;
    S[PWR_SVMCR2_BEFORE]=P->SVMCR2;
    if (P->SVMCR2&PWR_SVMCR2_VDDIO5VRSEL) { fail(c,BAD_VDDIO5_RANGE); return 0; }
    S[GPIOC_MODER_BEFORE]=C->MODER; S[GPIOC_IDR_BEFORE]=C->IDR;
    S[GPIOE_MODER_BEFORE]=E->MODER; S[GPIOE_IDR_BEFORE]=E->IDR;
    for (uint32_t pin=2;pin<=4;++pin) {
        uint32_t mode=(C->MODER>>(2*pin))&3UL;
        if (mode==1 || mode==2) { fail(c,BAD_GPIO_OWNER); return 0; }
    }
    uint32_t mode=(E->MODER>>8)&3UL;
    if (mode==1 || mode==2) { fail(c,BAD_GPIO_OWNER); return 0; }
    c->old_demcr=CoreDebug->DEMCR; c->old_dwt=DWT->CTRL;
    if (c->old_dwt&DWT_CTRL_NOCYCCNT_Msk) { fail(c,NO_TIMER); return 0; }
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
    __DSB(); __ISB(); c->timer=1;
    S[DWT_BEGIN]=DWT->CYCCNT;
    return wait_us(c,1);
}

static int setup(struct context *c)
{
    S[STAGE]=GPIO_SETUP;
    /* Preload only CLK low. CMD/DAT pins initially inputs with pull-ups. */
    C->BSRR=1UL<<(2+16);
    C->OTYPER&=~C_PINS;
    C->MODER&=~C_MASK;
    C->PUPDR=(C->PUPDR&~C_MASK)|(1UL<<6)|(1UL<<8);
    C->OSPEEDR=(C->OSPEEDR&~C_MASK)|C_MASK;
    E->MODER&=~(3UL<<8);
    E->PUPDR=(E->PUPDR&~(3UL<<8))|(1UL<<8);
    P->SVMCR2|=PWR_SVMCR2_VDDIO5SV; /* Board explicitly remains 3.3 V. */
    S[PWR_SVMCR2_AFTER]=P->SVMCR2;
    if (!wait_us(c,1000)) return 0;
    S[GPIOC_IDR_SETTLED]=C->IDR; S[GPIOE_IDR_SETTLED]=E->IDR;
    if ((C->IDR&((1UL<<3)|(1UL<<4)))!=((1UL<<3)|(1UL<<4)) ||
        !(E->IDR&(1UL<<4))) { fail(c,LINES_NOT_HIGH); return 0; }
    /* Select only SDMMC2's local kernel mux, never change a source clock. */
    R->CCIPR8&=~RCC_CCIPR8_SDMMC2SEL; /* HCLK = 150 MHz. */
    R->AHB5ENSR=RCC_AHB5ENSR_SDMMC2ENS;
    (void)R->AHB5ENR;
    R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
    __DSB();
    c->configured=1;
    X->MASK=0; X->POWER=0; X->DCTRL=0; X->IDMACTRL=0; X->CMD=0;
    X->CLKCR=750UL; /* 150 MHz / (2 * 750) = 100 kHz; one bit, rising edge. */
    C->AFR[0]=(C->AFR[0]&~(0xFFFUL<<8))|(0xBBBUL<<8);
    C->MODER=(C->MODER&~C_MASK)|(2UL<<4)|(2UL<<6)|(2UL<<8);
    S[GPIOC_MODER_AF]=C->MODER; S[GPIOC_AFR0]=C->AFR[0];
    S[GPIOC_PUPDR]=C->PUPDR; S[GPIOE_MODER_INPUT]=E->MODER; S[GPIOE_PUPDR]=E->PUPDR;
    if ((C->MODER&C_MASK)!=((2UL<<4)|(2UL<<6)|(2UL<<8)) ||
        (C->AFR[0]&(0xFFFUL<<8))!=(0xBBBUL<<8) ||
        (E->MODER&(3UL<<8)) || (E->PUPDR&(3UL<<8))!=(1UL<<8)) {
        fail(c,BAD_GPIO_READBACK); return 0;
    }
    S[STAGE]=POWERUP;
    X->POWER=SDMMC_POWER_PWRCTRL;
    S[CURRENT_SD_HZ]=100000UL; S[CLKCR]=X->CLKCR;
    return wait_us(c,10000); /* >=74 identification clocks and rail settling. */
}

static int identify(struct context *c)
{
    S[STAGE]=IDENTIFY;
    if (!command(c,0,0,NONE,0) || !command(c,8,0x1AAUL,R7,0)) return 0;
    if ((X->RESP1&0xFFFUL)!=0x1AAUL) { fail(c,BAD_CMD8); return 0; }
    uint32_t begin=DWT->CYCCNT;
    for (uint32_t i=0;i<2000;++i) {
        if (!command(c,55,0,R1,0)) return 0;
        if (!(X->RESP1&(1UL<<5))) { fail(c,CARD_ERROR); return 0; }
        /* HCS and 3.2–3.4 V windows; no S18R or XPC request. */
        if (!command(c,41,0x40300000UL,R3,0)) return 0;
        S[OCR]=X->RESP1;
        if (S[OCR]&(1UL<<31)) break;
        if ((uint32_t)(DWT->CYCCNT-begin)>=600000000UL || i==1999) {
            fail(c,CARD_NOT_READY); return 0;
        }
        if (!wait_us(c,1000)) return 0;
    }
    if (!command(c,2,0,R2,0)) return 0;
    S[CID0]=X->RESP1; S[CID1]=X->RESP2; S[CID2]=X->RESP3; S[CID3]=X->RESP4;
    if (!command(c,3,0,R6,0)) return 0;
    S[RCA]=X->RESP1&0xFFFF0000UL;
    if (!S[RCA]) { fail(c,BAD_RCA); return 0; }
    if (!command(c,9,S[RCA],R2,0)) return 0;
    S[CSD0]=X->RESP1; S[CSD1]=X->RESP2; S[CSD2]=X->RESP3; S[CSD3]=X->RESP4;
    S[CSD_VERSION]=S[CSD0]>>30;
    if (S[CSD_VERSION]==1 && (S[OCR]&(1UL<<30))) {
        uint32_t csize=((S[CSD1]&63UL)<<16)|(S[CSD2]>>16);
        uint32_t count=csize+1;
        S[SECTOR_COUNT_LOW]=count<<10; S[SECTOR_COUNT_HIGH]=count>>22;
    } else if (S[CSD_VERSION]==0 && !(S[OCR]&(1UL<<30))) {
        uint32_t csize=((S[CSD1]&1023UL)<<2)|(S[CSD2]>>30);
        uint32_t mult=(S[CSD2]>>15)&7UL, readlen=(S[CSD1]>>16)&15UL;
        if (readlen<9 || readlen>11) { fail(c,BAD_CSD); return 0; }
        S[SECTOR_COUNT_LOW]=(csize+1)<<(mult+2+readlen-9);
    } else { fail(c,BAD_CSD); return 0; }
    S[STAGE]=SELECT;
    if (!command(c,7,S[RCA],R1,0) || !ready(c)) return 0;
    if (!(S[OCR]&(1UL<<30)) && !command(c,16,512,R1,0)) return 0;
    return 1;
}

static void execute(struct context *c)
{
    if (!preflight(c) || !setup(c) || !identify(c)) return;
    for (uint32_t speed=0;speed<3;++speed) {
        uint32_t hz=speed==0 ? 100000UL : speed==1 ? 12500000UL : 25000000UL;
        if (hz>S[REQUEST_MAX_HZ]) break;
        S[STAGE]=READ_SLOW+speed;
        if (!ready(c)) return;
        X->CLKCR=HCLK_HZ/(2*hz);
        S[CURRENT_SD_HZ]=hz; S[CLKCR]=X->CLKCR;
        if (!wait_us(c,1000) ||
            !read_sector(c,0,2*speed) || !read_sector(c,1,2*speed+1)) return;
    }
}

void __attribute__((noreturn)) sd_read_smoke(uint32_t old_msp, uint32_t old_msplim)
{
    for (uint32_t i=0;i<STATUS_WORDS;++i) S[i]=0;
    struct context c={0};
    S[MAGIC]=0x53445231UL; S[SCHEMA]=1; S[WORDS]=STATUS_WORDS;
    S[RESULT]=RUNNING; S[STAGE]=PREFLIGHT;
    S[OLD_MSP]=old_msp; S[OLD_MSPLIM]=old_msplim;
    S[REQUEST_MAX_HZ]=REQUEST[1];
    if (REQUEST[0]!=0x53445244UL ||
        (REQUEST[1]!=100000 && REQUEST[1]!=12500000 && REQUEST[1]!=25000000) ||
        REQUEST[2] || REQUEST[3]) fail(&c,BAD_REQUEST);
    else execute(&c);
    if (c.configured) {
        /* Host input-only park. Card storage contents are untouched.
         * Local SDMMC reset clears an incomplete read without sending a write. */
        S[LAST_STA]=X->STA;
        X->MASK=0; X->DCTRL=0; X->CMD=0; X->IDMACTRL=0; X->POWER=0;
        R->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
        R->AHB5RSTCR=RCC_AHB5RSTCR_SDMMC2RSTC;
        R->AHB5ENCR=RCC_AHB5ENCR_SDMMC2ENC;
        R->CCIPR8=(R->CCIPR8&~RCC_CCIPR8_SDMMC2SEL)|(S[CCIPR8]&RCC_CCIPR8_SDMMC2SEL);
        C->MODER&=~C_MASK;
        C->PUPDR=(C->PUPDR&~C_MASK)|(2UL<<4)|(1UL<<6)|(1UL<<8);
        S[CLEANUP]=1;
    }
    if (c.timer) {
        S[DWT_END]=DWT->CYCCNT;
        DWT->CTRL=c.old_dwt; CoreDebug->DEMCR=c.old_demcr;
        S[CLEANUP]|=2;
    }
    S[RESULT]=c.result; S[STAGE]=FINISH; __DSB(); __ISB();
    __asm volatile(".global sd_smoke_park\nsd_smoke_park:\n1: b.n 1b");
    __builtin_unreachable();
}
