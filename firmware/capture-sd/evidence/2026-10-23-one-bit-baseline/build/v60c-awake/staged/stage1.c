/* Bench-only early sensor release and read-only second-stage load.
 * The root controller alone owns hardware. This is a separate application
 * reader; frozen NOR maintenance helpers are not modified or reused as code.
 * Compile without FP/MVE instructions (-mfloat-abi=soft -mgeneral-regs-only).
 */
#include <stddef.h>
#include <stdint.h>
#include "stm32n657xx.h"
#include "recovery_gpio.h"
#include "status_leds.h"

#ifndef STAGE2_BYTES
#error "Define the exact second-stage byte count"
#endif
#ifndef STAGE2_EXPECTED_CRC32
#error "Define the zlib/IEEE CRC32 of the exact second-stage raw bytes"
#endif
#ifndef STAGE2_FLASH_OFFSET
#define STAGE2_FLASH_OFFSET 0x2000U
#endif
#ifndef STAGE1_SKIP_SENSOR_RESET
#define STAGE1_SKIP_SENSOR_RESET 0
#endif
#ifndef STAGE1_WORD_READS
#define STAGE1_WORD_READS 0
#endif
#ifndef STAGE1_EARLY_SENSOR
#define STAGE1_EARLY_SENSOR 0
#endif
#ifndef STAGE1_XSPI_64MHZ
#define STAGE1_XSPI_64MHZ 0
#endif
#ifndef STAGE1_ENABLE_ICACHE
#define STAGE1_ENABLE_ICACHE 0
#endif
#ifndef STAGE1_INLINE_CRC
#define STAGE1_INLINE_CRC 0
#endif
_Static_assert(STAGE1_SKIP_SENSOR_RESET == 0 || STAGE1_SKIP_SENSOR_RESET == 1,
               "skip-reset is an explicit cold-only experiment");
_Static_assert(STAGE1_WORD_READS == 0 || STAGE1_WORD_READS == 1,
               "word-read path must be explicitly selected");
_Static_assert(STAGE1_EARLY_SENSOR == 0 || STAGE1_EARLY_SENSOR == 1,
               "early sensor initialization must be explicitly selected");
_Static_assert(STAGE1_XSPI_64MHZ == 0 || STAGE1_XSPI_64MHZ == 1,
               "64-MHz read is an explicit CRC-gated bench experiment");
_Static_assert(!STAGE1_XSPI_64MHZ || STAGE1_WORD_READS,
               "64-MHz experiment requires word FIFO reads");
_Static_assert(STAGE1_ENABLE_ICACHE == 0 || STAGE1_ENABLE_ICACHE == 1,
               "prefix instruction cache must be explicitly selected");
_Static_assert(STAGE1_INLINE_CRC == 0 || STAGE1_INLINE_CRC == 1,
               "CRC inlining must be explicitly selected");
#define STAGE2_LOAD_ADDRESS 0x34300000U
#define TRACE ((volatile uint32_t *)0x343F0000U)
#define EVENTS ((volatile uint32_t *)0x343F0100U)
#define STATUS ((volatile uint32_t *)0x343F3000U)
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
       S_ENTRY, S_START_CYCLES, S_END_CYCLES, S_CFSR, S_HFSR,
       S_RESET_POLICY, S_INITIAL_MODER, S_INITIAL_PUPDR, S_INITIAL_ODR,
       S_INITIAL_IDR, S_INITIAL_OTYPER, S_INITIAL_SVMCR3,
       S_FINAL_MODER, S_FINAL_ODR, S_FINAL_IDR, S_READ_WIDTH,
       S_EARLY_SENSOR_RESULT, S_XSPI_CCIPR6, S_XSPI_CCIPR7,
       S_XSPI_HSICFGR, S_XSPI_RCC_SR, S_N_MODER, S_N_OSPEEDR,
       S_N_OTYPER, S_N_AFRL, S_XSPI_SVMCR3, S_APPLIED_DCR2,
       S_RESTORED_DCR2, S_CACHE_BEFORE, S_CACHE_AFTER, S_WORDS };
enum { BAD_CONTEXT=1, BAD_CLOCK=2, BAD_CACHE=3, BAD_XSPI_CLOCK=4,
       BAD_XSPI_RESET=5, BAD_MUX=6, BAD_XSPI_CONFIG=7, NOT_IDLE=8,
       TRANSFER_ERROR=9, SHORT_READ=10, TIMEOUT=11, EXTRA_DATA=12,
       BAD_CRC=13, BAD_VECTOR=14, FAULT=15, BAD_INITIAL_PO5=16,
       EARLY_SENSOR_FAILURE=17, BAD_XSPI_SOURCE=18, BAD_XSPI_PADS=19,
       BAD_PRESCALER=20 };

extern void stage1_jump(uint32_t vector) __attribute__((noreturn));
#if STAGE1_EARLY_SENSOR
extern int stage1_sensor_start(void);
#endif

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

extern void raw10_memory_init(void);
extern void raw10_memory_fault(uint32_t reason) __attribute__((noreturn));
void stage1_fault(void) { raw10_memory_fault(0xF0U); }

/* Reflected IEEE CRC32, zlib-compatible; 64-byte nibble table keeps each byte
 * cheap enough to process while the single-line SPI stream is arriving. */
#if STAGE1_INLINE_CRC
static __attribute__((always_inline)) inline
#else
static
#endif
uint32_t crc_byte(uint32_t crc, uint8_t value)
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
    status_led_boot_begin();
    recovery_gpio_begin();
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
    recovery_gpio_check();
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    raw10_memory_init();
    recovery_gpio_publish();
    status_led_proof_init();
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
    STATUS[S_READ_WIDTH] = STAGE1_WORD_READS ? 4U : 1U;
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
#if STAGE1_SKIP_SENSOR_RESET
    /* Cold-only experiment: fitted P-board R17 pulls sensor XSDN to VDDIO.
     * Do not restart a sensor which may have booted during the MCU ROM phase.
     * Record host pin state before changing the latch or removing isolation.
     * Analog/isolated IDR is not proof of the physical XSDN voltage. */
    STATUS[S_RESET_POLICY] = 1U;
    STATUS[S_INITIAL_MODER] = GPIOO->MODER;
    STATUS[S_INITIAL_PUPDR] = GPIOO->PUPDR;
    STATUS[S_INITIAL_ODR] = GPIOO->ODR;
    STATUS[S_INITIAL_IDR] = GPIOO->IDR;
    STATUS[S_INITIAL_OTYPER] = GPIOO->OTYPER;
    STATUS[S_INITIAL_SVMCR3] = PWR->SVMCR3;
    event(208); /* Initial pin snapshot, NOT a sensor reset edge. */
    uint32_t initial_mode = (STATUS[S_INITIAL_MODER] >> 10U) & 3U;
    if ((initial_mode != 0U && initial_mode != 3U) ||
        (STATUS[S_INITIAL_PUPDR] & (3U << 10U))) fail(BAD_INITIAL_PO5);
    /* Preload HIGH while the pin remains input/analog. Setting MODER or
     * unisolating an output with the reset ODR=0 would create a reset pulse.
     * Frozen stage two later configures this pin as OUTPUT and preserves ODR. */
    GPIOO->BSRR = 1U << 5U;
    GPIOO->OTYPER &= ~(1U << 5U);
    GPIOO->PUPDR &= ~(3U << 10U);
    GPIOO->OSPEEDR = (GPIOO->OSPEEDR & ~(3U << 10U)) | (3U << 10U);
    __DSB();
    PWR->SVMCR3 |= PWR_SVMCR3_VDDIO2SV;
    (void)PWR->SVMCR3;
    GPIOO->MODER = (GPIOO->MODER & ~(3U << 10U)) | (1U << 10U);
    __DSB();
    STATUS[S_FINAL_MODER] = GPIOO->MODER;
    STATUS[S_FINAL_ODR] = GPIOO->ODR;
    STATUS[S_FINAL_IDR] = GPIOO->IDR;
    event(209); /* Host HIGH enabled; actual sensor release may be earlier. */
#else
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
#endif

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

#if STAGE1_XSPI_64MHZ
    /* UM3234 Tables 24/26: ROM kernel is CLKP=HSI64. Prove the actual muxes
     * and pin settings before changing only the read prescaler. Macronix
     * PM2183 Rev1.6 permits 0B/24-bit/8-dummy reads up to 133 MHz at 1.8 V.
     * This bench trial does NOT establish PCB load/compensation margin when
     * VDDIO3VRSEL=0; DS14791 Table70 is load-dependent in degraded mode. */
    STATUS[S_XSPI_CCIPR6]=RCC->CCIPR6;
    STATUS[S_XSPI_CCIPR7]=RCC->CCIPR7;
    STATUS[S_XSPI_HSICFGR]=RCC->HSICFGR;
    STATUS[S_XSPI_RCC_SR]=RCC->SR;
    if ((RCC->CCIPR6 & RCC_CCIPR6_XSPI1SEL) != RCC_CCIPR6_XSPI1SEL_0 ||
        (RCC->CCIPR7 & RCC_CCIPR7_PERSEL) ||
        (RCC->HSICFGR & RCC_HSICFGR_HSIDIV) ||
        !(RCC->SR & RCC_SR_HSIRDY)) fail(BAD_XSPI_SOURCE);
    if (!(RCC->AHB4ENR & RCC_AHB4ENR_GPIONEN)) fail(BAD_XSPI_PADS);
    STATUS[S_N_MODER]=GPION->MODER;
    STATUS[S_N_OSPEEDR]=GPION->OSPEEDR;
    STATUS[S_N_OTYPER]=GPION->OTYPER;
    STATUS[S_N_AFRL]=GPION->AFR[0];
    STATUS[S_XSPI_SVMCR3]=PWR->SVMCR3;
    /* PN1=NCS, PN2=MOSI, PN3=MISO, PN6=CLK, all AF9/highest speed. */
    const uint32_t pin_mask=(1U<<1U)|(1U<<2U)|(1U<<3U)|(1U<<6U);
    const uint32_t mode_mask=(3U<<2U)|(3U<<4U)|(3U<<6U)|(3U<<12U);
    const uint32_t mode_af=(2U<<2U)|(2U<<4U)|(2U<<6U)|(2U<<12U);
    const uint32_t af_mask=(15U<<4U)|(15U<<8U)|(15U<<12U)|(15U<<24U);
    const uint32_t af9=(9U<<4U)|(9U<<8U)|(9U<<12U)|(9U<<24U);
    if ((GPION->MODER & mode_mask) != mode_af ||
        (GPION->OSPEEDR & mode_mask) != mode_mask ||
        (GPION->OTYPER & pin_mask) || (GPION->AFR[0] & af_mask) != af9 ||
        !(PWR->SVMCR3 & PWR_SVMCR3_VDDIO3SV)) fail(BAD_XSPI_PADS);
#endif

#if STAGE1_ENABLE_ICACHE
    /* The cold-ROM-loaded prefix is immutable for this whole execution.
     * D-cache remains disabled by the guard above. Stage-two code receives
     * a separate full I-cache invalidation after its CRC-checked RAM copy. */
    STATUS[S_CACHE_BEFORE]=SCB->CCR;
    SCB_EnableICache();
    __DSB(); __ISB();
    STATUS[S_CACHE_AFTER]=SCB->CCR;
    if (!(SCB->CCR & SCB_CCR_IC_Msk) || (SCB->CCR & SCB_CCR_DC_Msk)) fail(BAD_CACHE);
#endif

#if STAGE1_EARLY_SENSOR
    /* Separately reviewed, bounded sensor setup may hide the subsequent NOR
     * load within START-to-exposure latency. No data transfer is active yet. */
    int sensor_result = stage1_sensor_start();
    STATUS[S_EARLY_SENSOR_RESULT]=(uint32_t)sensor_result;
    if (sensor_result != 0) fail(EARLY_SENSOR_FAILURE);
    if (x->SR & (XSPI_SR_BUSY | XSPI_SR_FLEVEL)) fail(NOT_IDLE);
#endif

#if STAGE1_XSPI_64MHZ
    /* RM0486 28.7.3 allows DCR2 changes only while idle. 0 bypasses the
     * prescaler; no command, dummy cycle, memory mode or pad setting changes. */
    x->DCR2=0U;
    __DSB();
    STATUS[S_APPLIED_DCR2]=x->DCR2;
    if (x->DCR2 != 0U) fail(BAD_PRESCALER);
#endif

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
#if STAGE1_WORD_READS
        /* RM0486 28.7.10: word reads pop four FIFO bytes. Requiring FLEVEL>=4
         * prevents a stalled peripheral access from hiding our own timeout. */
        uint32_t available = (sr & XSPI_SR_FLEVEL) >> XSPI_SR_FLEVEL_Pos;
        if (sr & XSPI_SR_TEF) { STATUS[S_LAST_SR]=sr; fail(TRANSFER_ERROR); }
        if (STAGE2_BYTES-count >= 4U && available >= 4U) {
            uint32_t value=x->DR;
            *(volatile uint32_t *)(data+count)=value;
            count+=4U;
            crc=crc_byte(crc,(uint8_t)value);
            crc=crc_byte(crc,(uint8_t)(value>>8U));
            crc=crc_byte(crc,(uint8_t)(value>>16U));
            crc=crc_byte(crc,(uint8_t)(value>>24U));
        } else if (STAGE2_BYTES-count < 4U && available) {
            uint8_t value=*(volatile uint8_t *)&x->DR;
            data[count++]=value;
            crc=crc_byte(crc,value);
        } else if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) {
            STATUS[S_LAST_SR]=sr; STATUS[S_COUNT]=count; fail(SHORT_READ);
        }
        ++polls;
        /* Only sparse progress snapshots; per-byte status stores previously
         * extended the transfer beyond the nominal serial-wire time. */
        if (!(polls & 255U)) {
            STATUS[S_LAST_SR]=sr; STATUS[S_COUNT]=count; STATUS[S_POLLS]=polls;
        }
        if (polls >= POLL_LIMIT || (uint32_t)(DWT->CYCCNT-began) >= TRANSFER_TIMEOUT_CYCLES) {
            STATUS[S_LAST_SR]=sr; STATUS[S_COUNT]=count; STATUS[S_POLLS]=polls;
            fail(TIMEOUT);
        }
#else
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
#endif
    }
    STATUS[S_COUNT]=count; STATUS[S_POLLS]=polls;
    for (;;) {
        sr=x->SR; STATUS[S_LAST_SR]=sr;
        if (sr & XSPI_SR_TEF) fail(TRANSFER_ERROR);
        if ((sr & XSPI_SR_TCF) && !(sr & XSPI_SR_BUSY)) break;
        STATUS[S_POLLS]=++polls;
        if (polls >= POLL_LIMIT || (uint32_t)(DWT->CYCCNT-began) >= TRANSFER_TIMEOUT_CYCLES)
            fail(TIMEOUT);
    }
    if (sr & XSPI_SR_FLEVEL) fail(EXTRA_DATA);
#if STAGE1_XSPI_64MHZ
    /* Completed transfer, FIFO empty, BUSY=0: restore the exact ROM speed
     * before CRC/vector checks and every successful handoff. A stuck/error
     * transfer instead remains awake for inspection; never abort or retry. */
    x->DCR2=1U;
    __DSB();
    STATUS[S_RESTORED_DCR2]=x->DCR2;
    if (x->DCR2 != 1U) fail(BAD_PRESCALER);
#endif
    STATUS[S_END_CYCLES]=DWT->CYCCNT;
    event(204);
    crc ^= 0xFFFFFFFFU;
    STATUS[S_CRC]=crc;
    if (crc != STAGE2_EXPECTED_CRC32) fail(BAD_CRC);
    event(205);

    uint32_t sp=*(volatile uint32_t *)STAGE2_LOAD_ADDRESS;
    uint32_t entry=*(volatile uint32_t *)(STAGE2_LOAD_ADDRESS+4U);
    STATUS[S_MSP]=sp; STATUS[S_ENTRY]=entry;
    if ((sp & 7U) || sp <= STAGE2_LOAD_ADDRESS+STAGE2_BYTES || sp > 0x343B0000U ||
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
