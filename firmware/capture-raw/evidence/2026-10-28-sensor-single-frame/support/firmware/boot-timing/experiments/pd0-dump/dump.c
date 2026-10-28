/* Offline-built diagnostic fallback, entered only after the original markers.
 * No runtime initialization, interrupts, timer writes, OTP or flash writes.
 * PD0 transmits a self-clocked packet stream; PE0 stays high.
 */
#include <stdint.h>
#include <stddef.h>
#include "stm32n657xx.h"

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define RCC_ADDR 0x56028000u
#define BSEC_ADDR 0x56009000u
#define DBG_ADDR 0x54001000u
#define PD_BSRR 0x56020C18u

_Static_assert(RCC_BASE_S == RCC_ADDR, "RCC address");
_Static_assert(GPIOD_BASE_S + offsetof(GPIO_TypeDef, BSRR) == PD_BSRR, "PD0 BSRR");
_Static_assert(TIM2_BASE_S == 0x50000000u, "TIM2 address");
_Static_assert(offsetof(TIM_TypeDef, CNT) == 0x24, "TIM2 CNT");
_Static_assert(offsetof(TIM_TypeDef, PSC) == 0x28, "TIM2 PSC");
_Static_assert(offsetof(RCC_TypeDef, APB1ENR1) == 0x264, "TIM2 clock register");
_Static_assert(RCC_APB1ENR1_TIM2EN == 1, "TIM2 clock bit");
_Static_assert(BSEC_BASE_S == BSEC_ADDR, "BSEC address");
_Static_assert(offsetof(BSEC_TypeDef, DBGCR) == 0xE8C, "DBGCR");
_Static_assert(offsetof(BSEC_TypeDef, AP_UNLOCK) == 0xE90, "AP_UNLOCK");
_Static_assert(offsetof(BSEC_TypeDef, HDPLSR) == 0xE94, "HDPLSR readback");
_Static_assert(offsetof(BSEC_TypeDef, SR) == 0xE40, "BSEC SR readback");
_Static_assert(DBGMCU_BASE_S == DBG_ADDR, "DBGMCU address");
_Static_assert(offsetof(DBGMCU_TypeDef, CR) == 4, "DBGMCU CR");
_Static_assert(DBGMCU_CR_DBGCLKEN == 0x100000, "DBGCLKEN");
_Static_assert(DBGMCU_CR_DBG_SLEEP == 1, "DBG_SLEEP");
_Static_assert(offsetof(RCC_TypeDef, APB4ENSR2) == 0xA78, "BSEC clock set");
_Static_assert(offsetof(RCC_TypeDef, APB4ENR2) == 0x278, "BSEC clock readback");
_Static_assert(RCC_APB4ENSR2_BSECENS == 2, "BSEC clock bit");
_Static_assert(offsetof(RCC_TypeDef, MISCENSR) == 0xA48, "DBG clock set");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENSR) == 0xA88, "DBG sleep clock set");
_Static_assert(offsetof(RCC_TypeDef, MISCENR) == 0x248, "DBG clock readback");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENR) == 0x288, "DBG sleep clock readback");
_Static_assert(offsetof(RCC_TypeDef, RDCR) == 0x44C, "RDCR readback");

static void barriers(void) { __asm volatile("dsb sy\n isb sy" ::: "memory"); }

/* Loop counts, not wall-clock timing. Decoder derives its unit from each sync.
 * Approximately tens of microseconds/unit at the observed ROM clocks.
 */
__attribute__((noinline)) static void delay_units(uint32_t units)
{
    while (units--) {
        uint32_t count = 5000;
        __asm volatile("1: subs %0, %0, #1\n bne 1b" : "+r"(count) :: "cc");
    }
}

static void line(uint32_t high) { REG32(PD_BSRR) = high ? 1u : 0x10000u; }

static void tx_byte(uint8_t value)
{
    for (uint32_t bit = 0; bit < 8; ++bit) {
        line(0);
        delay_units((value & 1u) ? 3u : 1u);
        line(1);
        delay_units(1);
        value >>= 1;
    }
}

static uint32_t crc_byte(uint32_t crc, uint8_t value)
{
    crc ^= value;
    for (uint32_t bit = 0; bit < 8; ++bit)
        crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xEDB88320u);
    return crc;
}

static void tx_checked(uint8_t value, uint32_t *crc)
{
    *crc = crc_byte(*crc, value);
    tx_byte(value);
}

/* Header: BTD1, type:u8, sequence:u16 LE, address:u32 LE, length:u16 LE.
 * Payload follows, then standard CRC32 (header + payload), uint32 little endian.
 */
static void packet(uint32_t *seq, uint8_t type, uint32_t address,
                   const uint8_t *data, uint32_t length)
{
    uint32_t crc = 0xFFFFFFFFu;
    line(1); delay_units(8);
    line(0); delay_units(12);
    line(1); delay_units(4);
    tx_checked('B', &crc); tx_checked('T', &crc);
    tx_checked('D', &crc); tx_checked('1', &crc);
    tx_checked(type, &crc);
    tx_checked((uint8_t)*seq, &crc); tx_checked((uint8_t)(*seq >> 8), &crc);
    ++*seq;
    for (uint32_t i = 0; i < 4; ++i) tx_checked((uint8_t)(address >> (8*i)), &crc);
    tx_checked((uint8_t)length, &crc); tx_checked((uint8_t)(length >> 8), &crc);
    for (uint32_t i = 0; i < length; ++i) tx_checked(data[i], &crc);
    crc = ~crc;
    for (uint32_t i = 0; i < 4; ++i) tx_byte((uint8_t)(crc >> (8*i)));
    line(1); delay_units(8);
}

static void checkpoint(uint32_t *seq, uint32_t stage)
{
    packet(seq, 1, stage, (const uint8_t *)0, 0);
}

static void readback(uint32_t *seq, uint32_t address)
{
    uint32_t value;
    packet(seq, 3, address, (const uint8_t *)0, 0);
    value = REG32(address);
    packet(seq, 5, address, (const uint8_t *)&value, sizeof value);
}

static void trace(uint32_t *seq, uint8_t type, uint32_t base)
{
    uint32_t data[16];
    for (uint32_t offset = 0; offset < 2048; offset += sizeof data) {
        /* A complete pending packet survives even if the following read faults.
         * No fault recovery is attempted. Missing CRC/chunks are never success.
         */
        packet(seq, 3, base + offset, (const uint8_t *)0, 0);
        for (uint32_t i = 0; i < 16; ++i)
            data[i] = REG32(base + offset + 4*i);
        packet(seq, type, base + offset, (const uint8_t *)data, sizeof data);
    }
}

__attribute__((noreturn)) void fallback_dump(uint32_t tim_enable,
                                           uint32_t tim_cnt, uint32_t tim_psc,
                                           uint32_t control)
{
    uint32_t seq = 0;
    uint32_t timer[4] = {tim_enable, tim_cnt, tim_psc, control};
    uint32_t status[7];
    /* Preserve a long initial PD0 high marker before sending any serial edge. */
    delay_units(8192);
    packet(&seq, 2, 0x50000000u, (const uint8_t *)timer, sizeof timer);
    /* Preserve both ROM traces before touching debug-control registers. */
    trace(&seq, 0x10, 0x341037F0u);
    trace(&seq, 0x11, 0x241077F0u);
    checkpoint(&seq, 0x100); /* Both trace buffers transmitted. */
    checkpoint(&seq, 1);  /* Before BSEC clock enable. */
    REG32(RCC_ADDR + 0xA78) = 2;
    (void)REG32(RCC_ADDR + 0x278);
    barriers();
    readback(&seq, BSEC_ADDR + 0xE94);
    readback(&seq, BSEC_ADDR + 0xE40);
    readback(&seq, BSEC_ADDR + 0xE8C);
    readback(&seq, BSEC_ADDR + 0xE90);
    checkpoint(&seq, 2);  /* Before BSEC_DBGCR write. */
    REG32(BSEC_ADDR + 0xE8C) = 0xB451B400u;
    barriers();
    readback(&seq, BSEC_ADDR + 0xE8C);
    checkpoint(&seq, 3);  /* Before BSEC_AP_UNLOCK write. */
    REG32(BSEC_ADDR + 0xE90) = 0xB4;
    barriers();
    readback(&seq, BSEC_ADDR + 0xE90);
    readback(&seq, BSEC_ADDR + 0xE94);
    readback(&seq, BSEC_ADDR + 0xE40);
    checkpoint(&seq, 4);  /* Before RCC/DBGMCU debug clock configuration. */
    REG32(RCC_ADDR + 0xA48) = 1;
    REG32(RCC_ADDR + 0xA88) = 1;
    (void)REG32(RCC_ADDR + 0x248);
    barriers();
    REG32(DBG_ADDR + 4) |= 0x100001;
    barriers();
    checkpoint(&seq, 5);  /* Before diagnostic register readback. */
    status[0] = REG32(BSEC_ADDR + 0xE8C);
    status[1] = REG32(BSEC_ADDR + 0xE90);
    status[2] = REG32(RCC_ADDR + 0x44C);
    status[3] = 0x44424733u;
    status[4] = REG32(DBG_ADDR + 4);
    status[5] = REG32(RCC_ADDR + 0x248);
    status[6] = REG32(RCC_ADDR + 0x288);
    packet(&seq, 4, 0, (const uint8_t *)status, sizeof status);
    checkpoint(&seq, 0xFFFFFFFFu); /* Complete; both traces have been sent. */
    line(1);
    for (;;) __asm volatile("nop");
}
