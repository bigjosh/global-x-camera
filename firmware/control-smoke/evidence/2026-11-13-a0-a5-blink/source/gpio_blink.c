/* Standalone header isolation test. Disconnect pots and HOLD before use.
 * Entered after the byte-preserved 400 MHz UART recovery guard. No HAL,
 * ADC, camera, storage, USB, interrupts or sleep; all six outputs are 2 Hz.
 */
#include "stm32n6xx.h"

#define PROOF ((volatile uint32_t *)0x34183000U)
#define HALF_CYCLES 100000000U
#define MASK_A (1U << 2)
#define MASK_C ((1U << 10) | (1U << 12))
#define MASK_F ((1U << 5) | (1U << 6))
#define MASK_H (1U << 2)

void blink_fault(void) __attribute__((noreturn, used));
void blink_main(void) __attribute__((noreturn, used, section(".text.entry")));

static void outputs(GPIO_TypeDef *g, uint32_t pins, uint32_t modes)
{
    g->BSRR = pins << 16; /* Preload LOW before connecting output drivers. */
    g->OTYPER &= ~pins;
    g->PUPDR &= ~(modes * 3U);
    g->OSPEEDR &= ~(modes * 3U);
    g->MODER = (g->MODER & ~(modes * 3U)) | modes;
}

static uint32_t packed(unsigned input)
{
    uint32_t a = input ? GPIOA->IDR : GPIOA->ODR;
    uint32_t c = input ? GPIOC->IDR : GPIOC->ODR;
    uint32_t f = input ? GPIOF->IDR : GPIOF->ODR;
    uint32_t h = input ? GPIOH->IDR : GPIOH->ODR;
    return ((f >> 5) & 1U) | (((c >> 10) & 1U) << 1)
        | (((f >> 6) & 1U) << 2) | (((a >> 2) & 1U) << 3)
        | (((c >> 12) & 1U) << 4) | (((h >> 2) & 1U) << 5);
}

void blink_fault(void)
{
    PROOF[19] = 0xF000U | __get_IPSR();
    PROOF[9] = SCB->CFSR;
    PROOF[10] = SCB->HFSR;
    __DSB();
    for (;;) __NOP();
}

void blink_main(void)
{
    __disable_irq();
    for (unsigned i = 0; i < 32; ++i) PROOF[i] = 0;
    PROOF[0] = 0x4B4E4C42U; /* BLNK */
    PROOF[1] = 1;
    PROOF[17] = HALF_CYCLES;
    RCC->AHB4ENSR = RCC_AHB4ENR_GPIOAEN | RCC_AHB4ENR_GPIOCEN |
        RCC_AHB4ENR_GPIOFEN | RCC_AHB4ENR_GPIOGEN | RCC_AHB4ENR_GPIOHEN |
        RCC_AHB4ENR_PWREN;
    __DSB();
    PROOF[12] = RCC->AHB4ENR;
    /* A1/PC10, A4/PC12 and A5/PH2 use stock 3.3 V VDDIO4. */
    if (PWR->SVMCR1 & PWR_SVMCR1_VDDIO4VRSEL) {
        PROOF[19] = 1;
        for (;;) __NOP();
    }
    PWR->SVMCR1 |= PWR_SVMCR1_VDDIO4SV;
    __DSB();
    PROOF[11] = PWR->SVMCR1;

    /* Buffered analog companions must not drive the onboard op-amps. */
    const uint32_t analog_a = (3U << 16) | (3U << 18) | (3U << 20) | (3U << 24);
    GPIOA->MODER |= analog_a; GPIOA->PUPDR &= ~analog_a;
    GPIOF->MODER |= 3U << 6; GPIOF->PUPDR &= ~(3U << 6);
    GPIOG->MODER |= 3U << 30; GPIOG->PUPDR &= ~(3U << 30);
    outputs(GPIOA, MASK_A, 1U << 4);
    outputs(GPIOC, MASK_C, (1U << 20) | (1U << 24));
    outputs(GPIOF, MASK_F, (1U << 10) | (1U << 12));
    outputs(GPIOH, MASK_H, 1U << 4);
    __DSB();
    PROOF[20] = GPIOA->MODER; PROOF[21] = GPIOC->MODER;
    PROOF[22] = GPIOF->MODER; PROOF[23] = GPIOH->MODER;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    uint32_t edge = DWT->CYCCNT, level = 0;
    PROOF[18] = edge;
    for (;;) {
        /* Delay the input sample 10 us after each edge for pad settling. */
        while ((uint32_t)(DWT->CYCCNT - edge) < 4000U) __NOP();
        PROOF[2]++;
        PROOF[3]++;
        PROOF[4] = level;
        PROOF[5] = edge;
        PROOF[7] = packed(1);
        PROOF[8] = packed(0);
        PROOF[level ? 14 : 13] = PROOF[7];
        PROOF[level ? 16 : 15]++;
        __DSB();
        PROOF[2]++;
        while ((uint32_t)(DWT->CYCCNT - edge) < HALF_CYCLES) __NOP();
        level ^= 1U;
        unsigned shift = level ? 0U : 16U;
        GPIOA->BSRR = MASK_A << shift;
        GPIOC->BSRR = MASK_C << shift;
        GPIOF->BSRR = MASK_F << shift;
        GPIOH->BSRR = MASK_H << shift;
        __DSB();
        uint32_t now = DWT->CYCCNT;
        PROOF[6] = now - edge;
        edge = now;
    }
}
