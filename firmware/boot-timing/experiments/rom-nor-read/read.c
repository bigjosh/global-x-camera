/* RAM-only, read-only NOR experiment. Reuses the exact observed ROM XSPI1/P2
 * configuration. Does not initialize clocks, GPIOs, security, caches or flash.
 * Only FCR, DLR and AR are written; DR is consumed with byte reads. */
#include <stddef.h>
#include "stm32n657xx.h"

#ifndef NOR_READ_LENGTH
#define NOR_READ_LENGTH 16
#endif
_Static_assert(NOR_READ_LENGTH == 16 || NOR_READ_LENGTH == 64, "16 or 64 bytes only");
_Static_assert(XSPI1_BASE_S == 0x58025000UL, "XSPI1 secure base");
_Static_assert(XSPIM_BASE_S == 0x5802B400UL, "XSPIM secure base");
_Static_assert(RCC_BASE_S == 0x56028000UL, "RCC secure base");
_Static_assert(offsetof(XSPI_TypeDef, DLR) == 0x40, "DLR offset");
_Static_assert(offsetof(XSPI_TypeDef, AR) == 0x48, "AR offset");
_Static_assert(offsetof(XSPI_TypeDef, DR) == 0x50, "DR offset");
_Static_assert(offsetof(RCC_TypeDef, AHB5ENR) == 0x260, "clock readback offset");
_Static_assert(offsetof(RCC_TypeDef, AHB5RSTR) == 0x220, "reset readback offset");

#define POLL_LIMIT 1000000UL
#define DONE 0x444F4E45UL
#define RUNNING 0x52554E4EUL

/* Word indices are fixed for debugger readout; see README. */
enum { MAGIC, RESULT, LENGTH, READ_COUNT, POLLS, LAST_SR, CONTROL, IPSR,
       CPU_CCR, OLD_MSP, OLD_MSPLIM, AHB5ENR, AHB5RSTR, MUX_CR, CR,
       DCR1, DCR2, INITIAL_SR, CCR, TCR, IR, INITIAL_DLR, INITIAL_AR,
       STATUS_WORDS };
enum { OK=0, BAD_CACHE=1, BAD_CONTEXT=2, BAD_CLOCK=3, IN_RESET=4,
       BAD_MUX=5, BAD_CONFIGURATION=6, NOT_IDLE=7, TRANSFER_ERROR=8,
       SHORT_READ=9, TIMEOUT=10, EXTRA_DATA=11 };

__attribute__((noreturn)) void rom_nor_read(uint32_t old_msp, uint32_t old_msplim)
{
    volatile uint32_t *const s = (volatile uint32_t *)0x341A0400UL;
    volatile uint8_t *const data = (volatile uint8_t *)0x341A0500UL;
    XSPI_TypeDef *const x = (XSPI_TypeDef *)XSPI1_BASE_S;
    RCC_TypeDef *const rcc = (RCC_TypeDef *)RCC_BASE_S;
    const uint32_t required_clocks = 0x2020UL; /* XSPI1 + XSPIM */
    uint32_t result = BAD_CACHE;
    uint32_t count = 0, polls = 0, sr = 0;

    for (uint32_t i=0; i<STATUS_WORDS; ++i) s[i] = 0;
    s[MAGIC] = RUNNING;
    s[RESULT] = 0xFFFFFFFFUL;
    s[LENGTH] = NOR_READ_LENGTH;
    s[OLD_MSP] = old_msp;
    s[OLD_MSPLIM] = old_msplim;
    s[CPU_CCR] = SCB->CCR;
    /* If D-cache is enabled, debugger visibility of this record is not assured.
     * Do not attempt a cache transition in this NOR-only diagnostic. */
    if ((s[CPU_CCR] & SCB_CCR_DC_Msk) != 0) goto finish;
    s[CONTROL] = __get_CONTROL();
    s[IPSR] = __get_IPSR();
    result = BAD_CONTEXT;
    if (s[CONTROL] != 0 || s[IPSR] != 0) goto finish;
    s[AHB5ENR] = rcc->AHB5ENR;
    s[AHB5RSTR] = rcc->AHB5RSTR;
    result = BAD_CLOCK;
    if ((s[AHB5ENR] & required_clocks) != required_clocks) goto finish;
    result = IN_RESET;
    if ((s[AHB5RSTR] & required_clocks) != 0) goto finish;
    s[MUX_CR] = *(volatile uint32_t *)XSPIM_BASE_S;
    result = BAD_MUX;
    if (s[MUX_CR] != 2) goto finish;
    s[CR] = x->CR;
    s[DCR1] = x->DCR1;
    s[DCR2] = x->DCR2;
    s[INITIAL_SR] = x->SR;
    s[CCR] = x->CCR;
    s[TCR] = x->TCR;
    s[IR] = x->IR;
    s[INITIAL_DLR] = x->DLR;
    s[INITIAL_AR] = x->AR;
    result = BAD_CONFIGURATION;
    if (s[CR] != 0x10000001UL || s[DCR1] != 0x001F0000UL ||
        s[DCR2] != 1 || s[CCR] != 0x01002101UL || s[TCR] != 8 || s[IR] != 0x0B)
        goto finish;
    result = NOT_IDLE;
    if ((s[INITIAL_SR] & (XSPI_SR_BUSY | XSPI_SR_FLEVEL)) != 0) goto finish;
    for (uint32_t i=0; i<NOR_READ_LENGTH; ++i) data[i] = 0;

    /* RM0486 28.4.10: AR write triggers this addressed indirect-read command.
     * Finite DLR prevents an indefinite stream. IR/CCR/TCR/CR stay unchanged. */
    x->FCR = XSPI_FCR_CTCF | XSPI_FCR_CTEF;
    x->DLR = NOR_READ_LENGTH - 1;
    x->AR = 0;
    __DSB();
    while (count < NOR_READ_LENGTH && polls < POLL_LIMIT) {
        ++polls;
        sr = x->SR;
        if (sr & XSPI_SR_TEF) { result = TRANSFER_ERROR; goto finish; }
        if (sr & XSPI_SR_FLEVEL) {
            data[count++] = *(volatile uint8_t *)&x->DR;
        } else if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) {
            result = SHORT_READ; goto finish;
        }
    }
    result = TIMEOUT;
    if (count != NOR_READ_LENGTH) goto finish;
    while (polls < POLL_LIMIT) {
        ++polls;
        sr = x->SR;
        if (sr & XSPI_SR_TEF) { result = TRANSFER_ERROR; goto finish; }
        if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) {
            result = (sr & XSPI_SR_FLEVEL) ? EXTRA_DATA : OK;
            goto finish;
        }
    }
finish:
    s[READ_COUNT] = count;
    s[POLLS] = polls;
    s[LAST_SR] = sr;
    s[RESULT] = result;
    __DSB();
    s[MAGIC] = DONE;
    __DSB();
    __ISB();
    __asm volatile(".global rom_nor_read_ready\nrom_nor_read_ready:\n"
                   "nop\nb rom_nor_read_ready\n" ::: "memory");
    __builtin_unreachable();
}
