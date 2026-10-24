/* Small early-resident thunk: bulk teardown code is read only after SAVE.
 * No card or NOR write command; no target reset or retry on failure.
 */
#include "stm32n6xx.h"
#include "status_leds.h"
#include "save_protocol.h"
#include "save_module_config.h"
#include "late_config.h"

#define LATE_PROOF ((volatile uint32_t *)0x343F9B00U)
#define SAVE_PROOF ((volatile const uint32_t *)0x343F9E00U)
#define SAVE_DONE ((volatile const uint32_t *)SAVE_REPORT_ADDRESS)
_Static_assert(LATE_FLASH_OFFSET == 0xE000U, "Reserved late NOR range");
_Static_assert(LATE_LOAD_ADDRESS == 0x343C0000U, "Reserved late SRAM range");
_Static_assert(LATE_ENTRY_ADDRESS == (LATE_LOAD_ADDRESS | 1U), "Thumb entry");
_Static_assert(LATE_BYTES && LATE_BYTES <= 8192U && LATE_BYTES % 4U == 0,
               "Bounded aligned late image");
_Static_assert(SAVE_FLASH_OFFSET + SAVE_BYTES <= LATE_FLASH_OFFSET,
               "Save/late images overlap");

static uint32_t update_crc(uint32_t crc, uint32_t value)
{
    for (unsigned byte=0; byte<4U; ++byte) {
        crc ^= value & 255U; value >>= 8;
        for (unsigned bit=0; bit<8U; ++bit)
            crc=(crc>>1)^((0U-(crc&1U))&0xEDB88320U);
    }
    return crc;
}

__attribute__((noreturn,noinline)) static void late_fail(unsigned error)
{
    LATE_PROOF[15]=0U;
    LATE_PROOF[3]=error; LATE_PROOF[2]=3U; LATE_PROOF[5]=DWT->CYCCNT;
    status_led_set(STATUS_LED_ERROR);
    __DSB();
    __asm volatile(".global late_completion_failure_idle\n"
                   "late_completion_failure_idle:\n"
                   "b.n late_completion_failure_idle\n");
    __builtin_unreachable();
}

__attribute__((noreturn,noinline,used)) void status_led_complete_sleep(void)
{
    /* Ownership was announced before capture event40/SAVE. Never hide it. */
    for (unsigned i=1; i<16U; ++i) LATE_PROOF[i]=0;
    LATE_PROOF[0]=0x4C504C31U; /* LPL1 */
    LATE_PROOF[1]=1U; LATE_PROOF[2]=1U; LATE_PROOF[4]=DWT->CYCCNT;
    LATE_PROOF[10]=LATE_ENTRY_ADDRESS; LATE_PROOF[11]=SAVE_PROOF[11];
    LATE_PROOF[12]=SCB->CCR; LATE_PROOF[13]=__get_CONTROL();
    LATE_PROOF[14]=FPU->FPCCR;
    if ((SCB->CCR & (SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) ||
        (__get_CONTROL() & ~0x0CU) || __get_IPSR() ||
        __get_PRIMASK()!=1U || __get_FAULTMASK() ||
        (FPU->FPCCR & FPU_FPCCR_LSPACT_Msk)) late_fail(1);
    /* These are fresh automatic-operation proofs. The late peripheral module
     * independently validates the complete card/FS/capture success snapshots. */
    if (SAVE_DONE[P_MAGIC]!=SAVE_REPORT_MAGIC ||
        SAVE_DONE[P_SCHEMA]!=SAVE_REPORT_SCHEMA ||
        SAVE_DONE[P_PROFILE]!=CAPTURE_DIAGNOSTICS ||
        SAVE_DONE[P_CHECKS_PERFORMED]!=(CAPTURE_DIAGNOSTICS ?
            SAVE_CHECKS_DIAGNOSTIC : SAVE_CHECKS_NORMAL) ||
        SAVE_DONE[P_WORDS]!=128U || SAVE_DONE[P_TERMINAL]!=0x444F4E45U ||
        SAVE_DONE[P_STATE]!=2U || SAVE_DONE[P_OP]!=SAVE_OP_SAVE ||
        SAVE_DONE[P_RESULT] || SAVE_DONE[P_NONCE] ||
        SAVE_DONE[P_MEDIA_IDLE]!=1U || SAVE_PROOF[0]!=0x534C4431U ||
        SAVE_PROOF[7]!=SAVE_CRC32 || SAVE_PROOF[8]!=SAVE_BYTES ||
        SAVE_PROOF[10] || !SAVE_PROOF[11]) late_fail(2);
    if ((RCC->AHB5ENR&0x2020U)!=0x2020U ||
        (RCC->AHB5RSTR&0x2020U)) late_fail(3);
    XSPI_TypeDef *x=(XSPI_TypeDef *)XSPI1_BASE_S;
    LATE_PROOF[6]=x->SR;
    if (x->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) late_fail(4);
    if (x->CR!=0x10000001U || x->DCR1!=0x001F0000U ||
        x->DCR2!=1U || x->CCR!=0x01002101U || x->TCR!=8U ||
        x->IR!=0x0BU || *(volatile uint32_t *)XSPIM_BASE_S!=2U) late_fail(5);
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    x->DLR=LATE_BYTES-1U; x->AR=LATE_FLASH_OFFSET;
    __DSB();
    uint32_t start=DWT->CYCCNT, count=0, crc=0xFFFFFFFFU, polls=0;
    volatile uint32_t *output=(volatile uint32_t *)LATE_LOAD_ADDRESS;
    while (count<LATE_BYTES) {
        uint32_t sr=x->SR;
        if (sr&XSPI_SR_TEF) late_fail(6);
        if (((sr&XSPI_SR_FLEVEL)>>XSPI_SR_FLEVEL_Pos)>=4U) {
            uint32_t value=x->DR;
            *output++=value; crc=update_crc(crc,value); count+=4U;
        } else if ((sr&XSPI_SR_TCF) && !(sr&XSPI_SR_BUSY)) late_fail(7);
        if (++polls>10000000U ||
            (uint32_t)(DWT->CYCCNT-start)>40000000U) late_fail(8);
    }
    while ((x->SR&XSPI_SR_BUSY) || !(x->SR&XSPI_SR_TCF)) {
        if (x->SR&XSPI_SR_TEF) late_fail(9);
        if (++polls>10000000U ||
            (uint32_t)(DWT->CYCCNT-start)>40000000U) late_fail(10);
    }
    uint32_t terminal=x->SR;
    LATE_PROOF[7]=terminal;
    if ((terminal&(XSPI_SR_BUSY|XSPI_SR_FLEVEL|XSPI_SR_TEF)) ||
        !(terminal&XSPI_SR_TCF)) late_fail(11);
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    LATE_PROOF[8]=count; LATE_PROOF[9]=crc^0xFFFFFFFFU;
    LATE_PROOF[5]=DWT->CYCCNT;
    if (LATE_PROOF[9]!=LATE_CRC32) late_fail(12);
    LATE_PROOF[2]=2U;
    __DSB();
    LATE_PROOF[15]=0x4C504C44U; /* LPLD: verified load, before entry. */
    __DSB(); __ISB();
    ((void (*)(void))LATE_ENTRY_ADDRESS)();
    late_fail(13); /* The completion entry is terminal. */
}
