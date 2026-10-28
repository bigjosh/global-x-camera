/* Bounded bench helper, not production firmware. Reuses the observed ROM
 * SPI-SDR controller/clock/mux state. INFO never sends a NOR write command.
 * WRITE is restricted to changed 4 KiB sectors in flash [0, 65536).
 * No clocks, GPIOs, caches, reset, option bytes or security settings changed. */
#include <stddef.h>
#include "stm32n657xx.h"

_Static_assert(SRAM2_AXI_BASE_S == 0x34100000UL, "AXISRAM2 base");
_Static_assert(0x341F0000UL <= SRAM2_AXI_BASE_S + 0x100000UL, "RAM bounds");
_Static_assert(XSPI1_BASE_S == 0x58025000UL, "XSPI1 base");
_Static_assert(XSPIM_BASE_S == 0x5802B400UL, "XSPIM base");
_Static_assert(RCC_BASE_S == 0x56028000UL, "RCC base");
#define CHECK(t, f, o) _Static_assert(offsetof(t, f) == o, #f " offset")
CHECK(XSPI_TypeDef, CR, 0); CHECK(XSPI_TypeDef, DCR1, 8);
CHECK(XSPI_TypeDef, DCR2, 0xC); CHECK(XSPI_TypeDef, SR, 0x20);
CHECK(XSPI_TypeDef, FCR, 0x24); CHECK(XSPI_TypeDef, DLR, 0x40);
CHECK(XSPI_TypeDef, AR, 0x48); CHECK(XSPI_TypeDef, DR, 0x50);
CHECK(XSPI_TypeDef, CCR, 0x100); CHECK(XSPI_TypeDef, TCR, 0x108);
CHECK(XSPI_TypeDef, IR, 0x110); CHECK(RCC_TypeDef, AHB5ENR, 0x260);
CHECK(RCC_TypeDef, AHB5RSTR, 0x220); CHECK(RCC_TypeDef, CFGR1, 0x20);
CHECK(RCC_TypeDef, CFGR2, 0x24); CHECK(RCC_TypeDef, PLL1CFGR1, 0x80);
CHECK(RCC_TypeDef, PLL1CFGR2, 0x84); CHECK(RCC_TypeDef, PLL1CFGR3, 0x88);

#define CMD ((volatile uint32_t *)0x341B4000UL)
#define S ((volatile uint32_t *)0x341B4100UL)
#define INPUT ((volatile uint8_t *)0x341C0000UL)
#define OUTPUT ((volatile uint8_t *)0x341D0000UL)
#define X ((XSPI_TypeDef *)XSPI1_BASE_S)
#define DONE 0x444F4E45UL
#define RUNNING 0x52554E4EUL
#define CYCLES_PER_US 400UL
#define TRANSFER_POLLS 8000000UL

/* This word-index schema is exported by build.py. All status is volatile RAM. */
enum { MAGIC, RESULT, SEQUENCE, COMMAND, STAGE, ADDRESS, TRANSFER_COUNT,
       POLLS, LAST_SR, NOR_STATUS, NOR_SECURITY, JEDEC_ID, CHANGED_MASK,
       ERASED_MASK, COMPLETED_MASK, PAGES_PROGRAMMED, CURRENT_CRC, INPUT_CRC,
       FINAL_CRC, EXPECTED_CURRENT_CRC, EXPECTED_INPUT_CRC, FLAGS, FAILURE_STAGE,
       FAILURE_ADDRESS, FAILURE_OPCODE, LAST_OPCODE, CONTROL, IPSR, CPU_CCR,
       OLD_MSP, OLD_MSPLIM, AHB5ENR, AHB5RSTR, MUX_CR, ORIGINAL_CR,
       ORIGINAL_DCR1, ORIGINAL_DCR2, ORIGINAL_SR, ORIGINAL_CCR, ORIGINAL_TCR,
       ORIGINAL_IR, ORIGINAL_DLR, ORIGINAL_AR, CFGR1, CFGR2, PLL1CFGR1,
       PLL1CFGR2, PLL1CFGR3, DWT_INITIAL, DWT_FINAL, DWT_ADVANCE, CLEANUP_RESULT,
       FIRST_MISMATCH, WREN_COUNT, TRANSACTION_COUNT, MAX_WIP_CYCLES, STATUS_WORDS };
enum { OK=0, BAD_COMMAND=1, BAD_CONTEXT=2, BAD_CACHE=3, BAD_CLOCK=4,
       BAD_MUX=5, BAD_CONFIG=6, NOT_IDLE=7, NO_TIMER=8, TRANSFER_ERROR=9,
       TRANSFER_TIMEOUT=10, SHORT_TRANSFER=11, EXTRA_DATA=12, BAD_ID=13,
       PROTECTED_OR_FAILED=14, NOR_BUSY=15, WEL_FAILURE=16, INPUT_CHANGED=17,
       CURRENT_CHANGED=18, ERASE_VERIFY=19, PAGE_VERIFY=20, FINAL_VERIFY=21,
       TIMER_STOPPED=22 };
enum { ST_PREFLIGHT=1, ST_INFO=2, ST_CHECK_INPUT=3, ST_READ_CURRENT=4,
       ST_PLAN=5, ST_ERASE=6, ST_ERASE_CHECK=7, ST_PROGRAM=8,
       ST_PAGE_CHECK=9, ST_FINAL_CHECK=10, ST_CLEANUP=11, ST_FINISHED=12 };
/* flags: controller idle, flash confirmed idle, ROM configuration restored,
 * WREN attempted, flash/controller state uncertain, DWT restored. */
enum { F_CONTROLLER_IDLE=1, F_FLASH_IDLE=2, F_RESTORED=4, F_WRITE_ATTEMPTED=8,
       F_UNCERTAIN=16, F_DWT_RESTORED=32 };
struct context {
    uint32_t result, old_demcr, old_dwt, last_end;
    uint32_t timer_on, configured, write_attempted, uncertain, flash_known;
};

static void fail(struct context *c, uint32_t result)
{
    if (c->result == OK) {
        c->result = result;
        S[FAILURE_STAGE] = S[STAGE]; S[FAILURE_ADDRESS] = S[ADDRESS];
        S[FAILURE_OPCODE] = S[LAST_OPCODE];
    }
}

static int gap(struct context *c)
{
    for (uint32_t i=0; i<100000UL; ++i) {
        if ((uint32_t)(DWT->CYCCNT-c->last_end) >= CYCLES_PER_US) return 1;
    }
    c->uncertain=1;
    fail(c, TIMER_STOPPED); return 0;
}

/* HAL_XSPI's command/config ordering: configure in indirect-write mode;
 * a read then switches mode and retriggers IR (no address) or AR (address).
 * Data writes start only when DR receives bytes; no-data writes start at IR/AR.
 * Every transfer must finish TCF + !BUSY + empty FIFO before the next command. */
static int transfer(struct context *c, uint32_t op, int addressed,
                    uint32_t address, uint32_t n, int receive,
                    volatile uint8_t *data)
{
    uint32_t count=0, sr=0, start, budget=(n>256 ? 100000UL : 10000UL)*CYCLES_PER_US;
    S[LAST_OPCODE]=op; S[TRANSFER_COUNT]=0;
    if (!gap(c)) return 0;
    if (X->SR & (XSPI_SR_BUSY | XSPI_SR_FLEVEL)) {
        c->uncertain=1; fail(c, NOT_IDLE); return 0;
    }
    X->CR=S[ORIGINAL_CR] & ~XSPI_CR_FMODE;
    X->CCR=1UL | (addressed ? 0x2100UL : 0) | (n ? 0x01000000UL : 0);
    X->TCR=(op==0x0B ? 8UL : 0UL);
    if (n) X->DLR=n-1;
    X->FCR=XSPI_FCR_CTCF | XSPI_FCR_CTEF;
    start=DWT->CYCCNT;
    X->IR=op;
    if (addressed) X->AR=address;
    if (receive) {
        X->CR=(S[ORIGINAL_CR] & ~XSPI_CR_FMODE) | XSPI_CR_FMODE_0;
        if (addressed) X->AR=address; else X->IR=op;
    }
    __DSB();
    ++S[TRANSACTION_COUNT];
    for (uint32_t p=0; p<TRANSFER_POLLS; ++p) {
        ++S[POLLS]; sr=X->SR; S[LAST_SR]=sr;
        if (sr & XSPI_SR_TEF) { fail(c, TRANSFER_ERROR); break; }
        if (count<n) {
            if (receive) {
                if (sr & XSPI_SR_FLEVEL) data[count++]=*(volatile uint8_t *)&X->DR;
                else if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) {
                    fail(c, SHORT_TRANSFER); break;
                }
            } else if (((sr & XSPI_SR_FLEVEL)>>8)<64UL) {
                *(volatile uint8_t *)&X->DR=data[count++];
            }
        } else if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) {
            S[TRANSFER_COUNT]=count;
            c->last_end=DWT->CYCCNT;
            if (sr & XSPI_SR_FLEVEL) { fail(c, EXTRA_DATA); break; }
            return 1;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=budget) {
            fail(c, TRANSFER_TIMEOUT); break;
        }
    }
    S[TRANSFER_COUNT]=count;
    fail(c, TRANSFER_TIMEOUT);
    c->uncertain=1; /* No further SPI commands on a failed controller transfer. */
    return 0;
}

static int status(struct context *c)
{
    uint8_t v=0;
    if (!transfer(c, 0x05, 0, 0, 1, 1, &v)) return 0;
    S[NOR_STATUS]=v; c->flash_known=1;
    return 1;
}

static int security(struct context *c)
{
    uint8_t v=0;
    if (!transfer(c, 0x2B, 0, 0, 1, 1, &v)) return 0;
    S[NOR_SECURITY]=v;
    return 1;
}

static int healthy(struct context *c)
{
    if ((S[NOR_STATUS]&0x3CUL) || (S[NOR_SECURITY]&0xECUL)) {
        fail(c, PROTECTED_OR_FAILED); return 0;
    }
    return 1; /* Security bit0 is factory OTP-lock information, not OTP mode. */
}

static int wait_idle(struct context *c, uint32_t us)
{
    uint32_t start=DWT->CYCCNT;
    for (uint32_t i=0; i<1000000UL; ++i) {
        if (!status(c)) return 0;
        if (!(S[NOR_STATUS]&1UL)) {
            uint32_t elapsed=(uint32_t)(DWT->CYCCNT-start);
            if (elapsed>S[MAX_WIP_CYCLES]) S[MAX_WIP_CYCLES]=elapsed;
            return 1;
        }
        if ((uint32_t)(DWT->CYCCNT-start)>=us*CYCLES_PER_US) break;
    }
    fail(c, NOR_BUSY); return 0;
}

static int write_enable(struct context *c)
{
    if (!status(c)) return 0;
    if (S[NOR_STATUS]&3UL) { fail(c, NOR_BUSY); return 0; }
    if (!security(c) || !healthy(c)) return 0;
    c->write_attempted=1;
    ++S[WREN_COUNT];
    if (!transfer(c, 0x06, 0, 0, 0, 0, 0) || !status(c)) return 0;
    if ((S[NOR_STATUS]&3UL)!=2) { fail(c, WEL_FAILURE); return 0; }
    return 1;
}

static int write_finished(struct context *c, uint32_t us)
{
    if (!wait_idle(c, us) || !security(c) || !healthy(c)) return 0;
    if (S[NOR_STATUS]&2UL) { fail(c, WEL_FAILURE); return 0; }
    return 1;
}

static uint32_t crc32_bytes(volatile const uint8_t *data, uint32_t n)
{
    uint32_t crc=0xFFFFFFFFUL;
    for (uint32_t i=0; i<n; ++i) {
        crc^=data[i];
        for (uint32_t bit=0; bit<8; ++bit)
            crc=(crc>>1) ^ (0xEDB88320UL & (0UL-(crc&1UL)));
    }
    return ~crc;
}

static int compare(uint32_t start, uint32_t length, int erased)
{
    for (uint32_t i=start; i<start+length; ++i) {
        if (OUTPUT[i] != (erased ? 0xFF : INPUT[i])) {
            S[FIRST_MISMATCH]=i; return 0;
        }
    }
    return 1;
}

static int preflight(struct context *c)
{
    S[CONTROL]=__get_CONTROL(); S[IPSR]=__get_IPSR(); S[CPU_CCR]=SCB->CCR;
    if (S[CONTROL] || S[IPSR]) { fail(c, BAD_CONTEXT); return 0; }
    if (S[CPU_CCR]&SCB_CCR_DC_Msk) { fail(c, BAD_CACHE); return 0; }
    S[AHB5ENR]=RCC_S->AHB5ENR; S[AHB5RSTR]=RCC_S->AHB5RSTR;
    S[CFGR1]=RCC_S->CFGR1; S[CFGR2]=RCC_S->CFGR2;
    S[PLL1CFGR1]=RCC_S->PLL1CFGR1; S[PLL1CFGR2]=RCC_S->PLL1CFGR2;
    S[PLL1CFGR3]=RCC_S->PLL1CFGR3;
    if ((S[AHB5ENR]&0x2020)!=0x2020 || (S[AHB5RSTR]&0x2020) ||
        S[CFGR1]!=0x33330000UL || S[CFGR2]!=0x00100000UL ||
        S[PLL1CFGR1]!=0x00404B00UL || S[PLL1CFGR2]!=0 ||
        S[PLL1CFGR3]!=0x49000005UL) { fail(c, BAD_CLOCK); return 0; }
    S[MUX_CR]=*(volatile uint32_t *)XSPIM_BASE_S;
    if (S[MUX_CR]!=2) { fail(c, BAD_MUX); return 0; }
    S[ORIGINAL_CR]=X->CR; S[ORIGINAL_DCR1]=X->DCR1; S[ORIGINAL_DCR2]=X->DCR2;
    S[ORIGINAL_SR]=X->SR; S[ORIGINAL_CCR]=X->CCR; S[ORIGINAL_TCR]=X->TCR;
    S[ORIGINAL_IR]=X->IR; S[ORIGINAL_DLR]=X->DLR; S[ORIGINAL_AR]=X->AR;
    if (S[ORIGINAL_CR]!=0x10000001UL || S[ORIGINAL_DCR1]!=0x001F0000UL ||
        S[ORIGINAL_DCR2]!=1 || S[ORIGINAL_CCR]!=0x01002101UL ||
        S[ORIGINAL_TCR]!=8 || S[ORIGINAL_IR]!=0x0B) { fail(c, BAD_CONFIG); return 0; }
    if (S[ORIGINAL_SR]&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) { fail(c, NOT_IDLE); return 0; }
    c->old_demcr=CoreDebug->DEMCR; c->old_dwt=DWT->CTRL;
    if (c->old_dwt&DWT_CTRL_NOCYCCNT_Msk) { fail(c, NO_TIMER); return 0; }
    CoreDebug->DEMCR=c->old_demcr|CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL=c->old_dwt|DWT_CTRL_CYCCNTENA_Msk;
    c->timer_on=1; __DSB(); __ISB();
    S[DWT_INITIAL]=DWT->CYCCNT;
    for (uint32_t i=0; i<10000; ++i) {
        S[DWT_ADVANCE]=(uint32_t)(DWT->CYCCNT-S[DWT_INITIAL]);
        if (S[DWT_ADVANCE]) { c->last_end=DWT->CYCCNT; c->configured=1; return 1; }
    }
    fail(c, NO_TIMER); return 0;
}

static void execute(struct context *c)
{
    uint8_t id[3];
    S[STAGE]=ST_INFO;
    if (!status(c)) return;
    if (S[NOR_STATUS]&3UL) { fail(c, NOR_BUSY); return; }
    if (!security(c) || !healthy(c)) return;
    if (!transfer(c, 0x9F, 0, 0, 3, 1, id)) return;
    S[JEDEC_ID]=((uint32_t)id[0]<<16)|((uint32_t)id[1]<<8)|id[2];
    if (S[JEDEC_ID]!=0xC2803AUL) { fail(c, BAD_ID); return; }
    if (S[COMMAND]==2) return;
    S[STAGE]=ST_CHECK_INPUT;
    S[INPUT_CRC]=crc32_bytes(INPUT, 65536);
    if (S[INPUT_CRC]!=S[EXPECTED_INPUT_CRC]) { fail(c, INPUT_CHANGED); return; }
    S[STAGE]=ST_READ_CURRENT;
    if (!transfer(c, 0x0B, 1, 0, 65536, 1, OUTPUT)) return;
    S[CURRENT_CRC]=crc32_bytes(OUTPUT, 65536);
    if (S[CURRENT_CRC]!=S[EXPECTED_CURRENT_CRC]) { fail(c, CURRENT_CHANGED); return; }
    S[STAGE]=ST_PLAN;
    for (uint32_t sector=0; sector<16; ++sector) {
        if (!compare(sector*4096, 4096, 0)) S[CHANGED_MASK]|=1UL<<sector;
    }
    S[FIRST_MISMATCH]=0xFFFFFFFFUL;
    for (uint32_t sector=0; sector<16; ++sector) {
        uint32_t base=sector*4096, mask=1UL<<sector;
        if (!(S[CHANGED_MASK]&mask)) continue;
        S[ADDRESS]=base; S[STAGE]=ST_ERASE;
        if (!write_enable(c) || !transfer(c, 0x20, 1, base, 0, 0, 0) ||
            !write_finished(c, 1000000)) return;
        S[ERASED_MASK]|=mask; S[STAGE]=ST_ERASE_CHECK;
        if (!transfer(c, 0x0B, 1, base, 4096, 1, OUTPUT+base)) return;
        if (!compare(base, 4096, 1)) { fail(c, ERASE_VERIFY); return; }
        for (uint32_t page=base; page<base+4096; page+=256) {
            uint32_t non_ff=0;
            for (uint32_t i=0; i<256; ++i) if (INPUT[page+i]!=0xFF) non_ff=1;
            if (!non_ff) continue;
            S[ADDRESS]=page; S[STAGE]=ST_PROGRAM;
            if (!write_enable(c) || !transfer(c, 0x02, 1, page, 256, 0, INPUT+page) ||
                !write_finished(c, 10000)) return;
            ++S[PAGES_PROGRAMMED]; S[STAGE]=ST_PAGE_CHECK;
            if (!transfer(c, 0x0B, 1, page, 256, 1, OUTPUT+page)) return;
            if (!compare(page, 256, 0)) { fail(c, PAGE_VERIFY); return; }
        }
        S[COMPLETED_MASK]|=mask;
    }
    S[ADDRESS]=0; S[STAGE]=ST_FINAL_CHECK;
    if (!transfer(c, 0x0B, 1, 0, 65536, 1, OUTPUT)) return;
    S[FINAL_CRC]=crc32_bytes(OUTPUT, 65536);
    if (S[FINAL_CRC]!=S[EXPECTED_INPUT_CRC] || !compare(0, 65536, 0))
        fail(c, FINAL_VERIFY);
}

/* Do not issue security/WRDI or restore transaction registers while the NOR
 * might still be executing a write. A failed controller transfer makes its
 * flash state unknown: leave it untouched for diagnosis. A WIP timeout gets
 * one additional bounded status-only wait, then DONE with uncertainty flags. */
static void finish(struct context *c)
{
    uint32_t original_result=c->result;
    uint32_t original_stage=S[FAILURE_STAGE], original_address=S[FAILURE_ADDRESS];
    uint32_t original_opcode=S[FAILURE_OPCODE];
    /* Preserve the primary error, but also report any independent cleanup
     * failure. A preceding failure must not suppress cleanup diagnostics. */
    c->result=OK;
    S[STAGE]=ST_CLEANUP;
    if (c->configured && !c->uncertain && c->write_attempted) {
        if (wait_idle(c, 1000000)) {
            if (transfer(c, 0x04, 0, 0, 0, 0, 0) && status(c)) {
                if (S[NOR_STATUS]&3UL) fail(c, WEL_FAILURE);
            }
        }
    }
    if (c->write_attempted) S[FLAGS]|=F_WRITE_ATTEMPTED;
    if (c->configured) {
        if (!(X->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL))) S[FLAGS]|=F_CONTROLLER_IDLE;
        if (c->flash_known && !c->uncertain && !(S[NOR_STATUS]&1UL)) S[FLAGS]|=F_FLASH_IDLE;
        if (!c->uncertain && (S[FLAGS]&(F_CONTROLLER_IDLE|F_FLASH_IDLE))==3) {
            /* Restore addressed ROM-read config without writing its AR trigger. */
            X->CR=S[ORIGINAL_CR]&~XSPI_CR_FMODE;
            X->CCR=S[ORIGINAL_CCR]; X->TCR=S[ORIGINAL_TCR]; X->DLR=S[ORIGINAL_DLR];
            X->IR=S[ORIGINAL_IR]; X->CR=S[ORIGINAL_CR];
            X->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
            S[FLAGS]|=F_RESTORED;
        } else S[FLAGS]|=F_UNCERTAIN;
    }
    if (c->timer_on) {
        S[DWT_FINAL]=DWT->CYCCNT;
        DWT->CTRL=c->old_dwt; CoreDebug->DEMCR=c->old_demcr;
        S[FLAGS]|=F_DWT_RESTORED;
    }
    S[CLEANUP_RESULT]=c->result;
    if (original_result!=OK) {
        c->result=original_result;
        S[FAILURE_STAGE]=original_stage; S[FAILURE_ADDRESS]=original_address;
        S[FAILURE_OPCODE]=original_opcode;
    }
    S[RESULT]=c->result; S[STAGE]=ST_FINISHED;
    __DSB(); S[MAGIC]=DONE; __DSB(); __ISB();
}

__attribute__((noreturn)) void rom_nor_programmer(uint32_t old_msp, uint32_t old_msplim)
{
    struct context c;
    for (uint32_t i=0; i<sizeof(c); ++i) ((volatile uint8_t *)&c)[i]=0;
    /* Clear MAGIC first so host cannot mistake a prior DONE for this command. */
    S[MAGIC]=RUNNING; __DSB();
    for (uint32_t i=1; i<STATUS_WORDS; ++i) S[i]=0;
    S[SEQUENCE]=CMD[1]; S[COMMAND]=CMD[2]; S[RESULT]=0xFFFFFFFFUL;
    S[STAGE]=ST_PREFLIGHT; S[OLD_MSP]=old_msp; S[OLD_MSPLIM]=old_msplim;
    S[FIRST_MISMATCH]=0xFFFFFFFFUL;
    S[EXPECTED_CURRENT_CRC]=CMD[6]; S[EXPECTED_INPUT_CRC]=CMD[7];
    if (CMD[0]!=0x4E4F5244UL ||
        !((S[COMMAND]==2 && CMD[3]==0 && CMD[4]==0 && CMD[5]==0) ||
          (S[COMMAND]==3 && CMD[3]==65536 && CMD[4]==0 && CMD[5]==0x57524954UL)))
        fail(&c, BAD_COMMAND);
    else if (preflight(&c)) execute(&c);
    finish(&c);
    __asm volatile(".global rom_nor_programmer_ready\nrom_nor_programmer_ready:\n"
                   "nop\nb rom_nor_programmer_ready\n" ::: "memory");
    __builtin_unreachable();
}
