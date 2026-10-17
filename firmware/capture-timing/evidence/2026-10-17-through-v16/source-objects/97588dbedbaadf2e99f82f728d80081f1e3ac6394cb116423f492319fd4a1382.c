/* Bench-only early sensor release and read-only second-stage load.
 * The root controller alone owns hardware. This is a separate application
 * reader; frozen NOR maintenance helpers are not modified or reused as code.
 * Compile without FP/MVE instructions (-mfloat-abi=soft -mgeneral-regs-only).
 */
#include <stddef.h>
#include <stdint.h>
#include "stm32n657xx.h"

#ifndef STAGE2_BYTES
#error "Define the exact second-stage byte count"
#endif
#ifndef STAGE2_EXPECTED_CRC32
#error "Define the zlib/IEEE CRC32 of the exact second-stage raw bytes"
#endif
#ifndef STAGE2_FLASH_OFFSET
#define STAGE2_FLASH_OFFSET 0x2000U
#endif
#define STAGE2_LOAD_ADDRESS 0x34190000U
#define TRACE ((volatile uint32_t *)0x341F0000U)
#define EVENTS ((volatile uint32_t *)0x341F0100U)
#define STATUS ((volatile uint32_t *)0x341F3000U)
#define CPU_NOMINAL_HZ 400000000U
#define TRANSFER_TIMEOUT_CYCLES (CPU_NOMINAL_HZ / 10U)
#define POLL_LIMIT 10000000U

_Static_assert(STAGE2_BYTES >= 64U && STAGE2_BYTES <= 0x10000U, "stage-two code bound");
_Static_assert(STAGE2_FLASH_OFFSET >= 0x2000U, "stage-two must not overlap prefix");
_Static_assert(STAGE2_FLASH_OFFSET + STAGE2_BYTES <= 0x10000U, "first 64-KiB experiment only");
_Static_assert(XSPI1_BASE_S == 0x58025000U, "verified XSPI1 base");
_Static_assert(XSPIM_BASE_S == 0x5802B400U, "verified XSPIM base");
_Static_assert(offsetof(XSPI_TypeDef, DLR) == 0x40, "DLR offset");
_Static_assert(offsetof(XSPI_TypeDef, AR) == 0x48, "AR offset");
_Static_assert(offsetof(XSPI_TypeDef, DR) == 0x50, "DR offset");

enum { S_MAGIC, S_RESULT, S_BYTES, S_COUNT, S_POLLS, S_LAST_SR, S_CONTROL,
       S_IPSR, S_CCR, S_AHB5ENR, S_AHB5RSTR, S_MUX, S_CR, S_DCR1, S_DCR2,
       S_XCCR, S_TCR, S_IR, S_DLR, S_AR, S_CRC, S_EXPECTED_CRC, S_MSP,
       S_ENTRY, S_START_CYCLES, S_END_CYCLES, S_CFSR, S_HFSR, S_WORDS };
enum { BAD_CONTEXT=1, BAD_CLOCK=2, BAD_CACHE=3, BAD_XSPI_CLOCK=4,
       BAD_XSPI_RESET=5, BAD_MUX=6, BAD_XSPI_CONFIG=7, NOT_IDLE=8,
       TRANSFER_ERROR=9, SHORT_READ=10, TIMEOUT=11, EXTRA_DATA=12,
       BAD_CRC=13, BAD_VECTOR=14, FAULT=15 };

extern void stage1_jump(uint32_t vector) __attribute__((noreturn));

static void event(uint32_t id)
{
    uint32_t n = TRACE[2];
    if (n < 200U) {
        EVENTS[n*4U] = id;
        EVENTS[n*4U+1U] = DWT->CYCCNT;
        EVENTS[n*4U+2U] = 0; /* HAL tick does not exist in stage one. */
        EVENTS[n*4U+3U] = CPU_NOMINAL_HZ;
        TRACE[2] = n + 1U;
    }
    TRACE[1] = id;
    GPIOE->ODR ^= 1U;
    __DMB();
}

__attribute__((noreturn)) static void fail(uint32_t code)
{
    STATUS[S_RESULT] = code;
    STATUS[S_CFSR] = SCB->CFSR;
    STATUS[S_HFSR] = SCB->HFSR;
    STATUS[S_MAGIC] = 0x53314552U; /* S1ER */
    TRACE[3] = code;
    event(0xE1000000U | code);
    __DSB();
    for (;;) __NOP(); /* No WFI, BKPT, reset, retry or NOR abort. */
}

void stage1_fault(void) { fail(FAULT); }

/* Reflected IEEE CRC32, zlib-compatible; 64-byte nibble table keeps each byte
 * cheap enough to process while the single-line SPI stream is arriving. */
static uint32_t crc_byte(uint32_t crc, uint8_t value)
{
    static const uint32_t table[16] = {
        0x00000000U,0x1DB71064U,0x3B6E20C8U,0x26D930ACU,
        0x76DC4190U,0x6B6B51F4U,0x4DB26158U,0x5005713CU,
        0xEDB88320U,0xF00F9344U,0xD6D6A3E8U,0xCB61B38CU,
        0x9B64C2B0U,0x86D3D2D4U,0xA00AE278U,0xBDBDF21CU
    };
    crc ^= value;
    crc = (crc >> 4U) ^ table[crc & 15U];
    return (crc >> 4U) ^ table[crc & 15U];
}

__attribute__((noreturn)) void stage1_main(void)
{
    /* Same volatile debug opening as the verified awake marker. No OTP or
     * lifecycle write. No peripheral/global clock reset is performed. */
    RCC->APB4ENSR2 = RCC_APB4ENSR2_BSECENS;
    (void)RCC->APB4ENR2;
    BSEC->DBGCR = 0xB451B400U;
    BSEC->AP_UNLOCK = 0xB4U;
    RCC->MISCENSR = RCC_MISCENSR_DBGENS;
    RCC->MISCLPENSR = RCC_MISCLPENSR_DBGLPENS;
    (void)RCC->MISCENR;
    DBGMCU->CR |= DBGMCU_CR_DBGCLKEN | DBGMCU_CR_DBG_SLEEP;
    RCC->AHB4ENSR = RCC_AHB4ENSR_GPIODENS | RCC_AHB4ENSR_GPIOEENS;
    (void)RCC->AHB4ENR;
    GPIOD->MODER = (GPIOD->MODER & ~3U) | 1U;
    GPIOE->MODER = (GPIOE->MODER & ~3U) | 1U;
    GPIOE->BSRR = 1U << 16U;
    GPIOD->BSRR = 1U;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    for (uint32_t i=0; i<64U; ++i) TRACE[i]=0;
    for (uint32_t i=0; i<S_WORDS; ++i) STATUS[i]=0;
    TRACE[0] = 0x43545031U; /* Same CTP1 schema as stage two. */
    TRACE[16] = RCC->CFGR1;
    TRACE[17] = RCC->CFGR2;
    TRACE[18] = SCB->CCR;
    TRACE[19] = BSEC->DBGCR;
    TRACE[20] = BSEC->AP_UNLOCK;
    STATUS[S_MAGIC] = 0x5331524EU; /* S1RN */
    STATUS[S_RESULT] = 0xFFFFFFFFU;
    STATUS[S_BYTES] = STAGE2_BYTES;
    STATUS[S_EXPECTED_CRC] = STAGE2_EXPECTED_CRC32;
    event(200);

    STATUS[S_CONTROL] = __get_CONTROL();
    STATUS[S_IPSR] = __get_IPSR();
    STATUS[S_CCR] = SCB->CCR;
    if (STATUS[S_CONTROL] || STATUS[S_IPSR]) fail(BAD_CONTEXT);
    if (STATUS[S_CCR] & SCB_CCR_DC_Msk) fail(BAD_CACHE);
    /* Exact qualified nominal ROM profile; never silently guess DWT timing. */
    if (RCC->CFGR1 != 0x33330000U || RCC->CFGR2 != 0x00100000U ||
        RCC->PLL1CFGR1 != 0x00404B00U || RCC->PLL1CFGR2 != 0 ||
        RCC->PLL1CFGR3 != 0x49000005U ||
        (RCC->IC1CFGR & (RCC_IC1CFGR_IC1SEL | RCC_IC1CFGR_IC1INT)) !=
        (2U << RCC_IC1CFGR_IC1INT_Pos) ||
        (RCC->HSICFGR & RCC_HSICFGR_HSIDIV)) fail(BAD_CLOCK);

    /* The mounted module is already supplied by board rails. This enables the
     * MCU I/O domain and holds XSHUTDOWN low; it does not switch module power. */
    RCC->AHB4ENSR = RCC_AHB4ENSR_PWRENS | RCC_AHB4ENSR_GPIOOENS;
    (void)RCC->AHB4ENR;
    PWR->SVMCR3 |= PWR_SVMCR3_VDDIO2SV;
    (void)PWR->SVMCR3;
    GPIOO->BSRR = 1U << (5U+16U); /* Low before output mode avoids a high glitch. */
    GPIOO->OTYPER &= ~(1U << 5U);
    GPIOO->PUPDR &= ~(3U << 10U);
    GPIOO->OSPEEDR = (GPIOO->OSPEEDR & ~(3U << 10U)) | (3U << 10U);
    GPIOO->MODER = (GPIOO->MODER & ~(3U << 10U)) | (1U << 10U);
    event(201);
    uint32_t reset_start = DWT->CYCCNT;
    /* 102 nominal us preserves >=100 us through a +2% source-clock allowance. */
    while ((uint32_t)(DWT->CYCCNT-reset_start) < 40800U) __NOP();
    GPIOO->BSRR = 1U << 5U;
    event(202);

    XSPI_TypeDef *const x = (XSPI_TypeDef *)XSPI1_BASE_S;
    volatile uint8_t *const data = (volatile uint8_t *)STAGE2_LOAD_ADDRESS;
    STATUS[S_AHB5ENR]=RCC->AHB5ENR;
    STATUS[S_AHB5RSTR]=RCC->AHB5RSTR;
    if ((STATUS[S_AHB5ENR] & 0x2020U) != 0x2020U) fail(BAD_XSPI_CLOCK);
    if (STATUS[S_AHB5RSTR] & 0x2020U) fail(BAD_XSPI_RESET);
    STATUS[S_MUX]=*(volatile uint32_t *)XSPIM_BASE_S;
    if (STATUS[S_MUX] != 2U) fail(BAD_MUX);
    STATUS[S_CR]=x->CR; STATUS[S_DCR1]=x->DCR1; STATUS[S_DCR2]=x->DCR2;
    STATUS[S_XCCR]=x->CCR; STATUS[S_TCR]=x->TCR; STATUS[S_IR]=x->IR;
    STATUS[S_DLR]=x->DLR; STATUS[S_AR]=x->AR;
    if (STATUS[S_CR] != 0x10000001U || STATUS[S_DCR1] != 0x001F0000U ||
        STATUS[S_DCR2] != 1U || STATUS[S_XCCR] != 0x01002101U ||
        STATUS[S_TCR] != 8U || STATUS[S_IR] != 0x0BU) fail(BAD_XSPI_CONFIG);
    if (x->SR & (XSPI_SR_BUSY | XSPI_SR_FLEVEL)) fail(NOT_IDLE);

    uint32_t count=0, polls=0, sr=0, crc=0xFFFFFFFFU;
    uint32_t began=DWT->CYCCNT;
    STATUS[S_START_CYCLES]=began;
    event(203);
    x->FCR=XSPI_FCR_CTCF | XSPI_FCR_CTEF;
    x->DLR=STAGE2_BYTES-1U;
    x->AR=STAGE2_FLASH_OFFSET; /* Starts a finite indirect READ, opcode unchanged. */
    __DSB();
    while (count < STAGE2_BYTES) {
        sr=x->SR;
        STATUS[S_LAST_SR]=sr;
        if (sr & XSPI_SR_TEF) fail(TRANSFER_ERROR);
        if (sr & XSPI_SR_FLEVEL) {
            uint8_t value=*(volatile uint8_t *)&x->DR;
            data[count++]=value;
            crc=crc_byte(crc,value);
            STATUS[S_COUNT]=count;
        } else if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) fail(SHORT_READ);
        STATUS[S_POLLS]=++polls;
        if (polls >= POLL_LIMIT || (uint32_t)(DWT->CYCCNT-began) >= TRANSFER_TIMEOUT_CYCLES)
            fail(TIMEOUT);
    }
    for (;;) {
        sr=x->SR; STATUS[S_LAST_SR]=sr;
        if (sr & XSPI_SR_TEF) fail(TRANSFER_ERROR);
        if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) break;
        STATUS[S_POLLS]=++polls;
        if (polls >= POLL_LIMIT || (uint32_t)(DWT->CYCCNT-began) >= TRANSFER_TIMEOUT_CYCLES)
            fail(TIMEOUT);
    }
    if (sr & XSPI_SR_FLEVEL) fail(EXTRA_DATA);
    STATUS[S_END_CYCLES]=DWT->CYCCNT;
    event(204);
    crc ^= 0xFFFFFFFFU;
    STATUS[S_CRC]=crc;
    if (crc != STAGE2_EXPECTED_CRC32) fail(BAD_CRC);
    event(205);

    uint32_t sp=*(volatile uint32_t *)STAGE2_LOAD_ADDRESS;
    uint32_t entry=*(volatile uint32_t *)(STAGE2_LOAD_ADDRESS+4U);
    STATUS[S_MSP]=sp; STATUS[S_ENTRY]=entry;
    if ((sp & 7U) || sp <= STAGE2_LOAD_ADDRESS+STAGE2_BYTES || sp > 0x341B0000U ||
        !(entry & 1U) || (entry & ~1U) < STAGE2_LOAD_ADDRESS ||
        (entry & ~1U) >= STAGE2_LOAD_ADDRESS+STAGE2_BYTES) fail(BAD_VECTOR);
    /* Do not restore AR: writing it would start another NOR transaction.
     * Leave the completed finite read's DLR/AR/status inspectable, like the
     * reviewed ROM reader. Remaining routing/configuration is unchanged. */
    __DSB();
    SCB_InvalidateICache(); /* Stage two is freshly written executable SRAM. */
    __DSB(); __ISB();
    STATUS[S_RESULT]=0;
    STATUS[S_MAGIC]=0x53314F4BU; /* S1OK */
    event(206);
    stage1_jump(STAGE2_LOAD_ADDRESS);
}
