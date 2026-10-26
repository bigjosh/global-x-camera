/* A failure terminal that is independent of the SD driver and late loader.
 * The owner first attempts bounded normal SD cleanup when that is possible.
 * This last resort deliberately abandons the current transaction. Resetting
 * the host is NOT evidence that the card is ready, and no success/idle report
 * is written here. Existing photos/power-loss behavior remain unqualified.
 *
 * This entire implementation is in the ROM-loaded .error_text region: no
 * data/BSS, function-pointer tables, HAL, libc or high SRAM dependencies.
 */
#include "error_signal.h"

#ifdef ERROR_SIGNAL_HOST_TEST
extern int error_platform_begin(void);
extern void error_platform_led(uint32_t on);
extern int error_platform_delay(uint32_t ms);
extern void error_platform_end(void) __attribute__((noreturn));
#else
#include "stm32n657xx.h"

#define INLINE static inline __attribute__((always_inline))
#define RED (1UL << 10)
#define LEDS (RED | (1UL << 8) | 1UL)
#define LED_MODES ((3UL << 20) | (3UL << 16) | 3UL)
#define GPIO_CLOCKS (RCC_AHB4ENR_GPIOBEN | RCC_AHB4ENR_GPIOCEN | \
    RCC_AHB4ENR_GPIOEEN | RCC_AHB4ENR_GPIOGEN | RCC_AHB4ENR_GPIONEN | RCC_AHB4ENR_GPIOOEN)
#define GPIO_RESETS (RCC_AHB4RSTR_GPIOBRST | RCC_AHB4RSTR_GPIOCRST | \
    RCC_AHB4RSTR_GPIOERST | RCC_AHB4RSTR_GPIOGRST | RCC_AHB4RSTR_GPIONRST | RCC_AHB4RSTR_GPIOORST)
#define SD_PIN_MODES ((3UL << 0) | (3UL << 4) | (3UL << 6) | (3UL << 8) | (3UL << 10))
#define NOR_PIN_MODES ((3UL << 4) | (3UL << 6) | (3UL << 12))

INLINE void error_platform_led(uint32_t on)
{
    /* The entry has already enabled and checked GPIOG; no port reset. */
    GPIOG->BSRR = on ? ((LEDS & ~RED) | (RED << 16)) : LEDS;
    __DSB();
}

INLINE int error_platform_begin(void)
{
    __disable_irq();
    SysTick->CTRL=0U; SysTick->VAL=0U;
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
    SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk | SCB_SCR_SLEEPONEXIT_Msk | SCB_SCR_SEVONPEND_Msk);
    /* Stop DMA/receiver activity through RCC aliases only. Never dereference
     * CSI/DCMIPP/SDMMC/I2C/XSPI, even when their clocks happen to be enabled. */
    RCC->APB5RSTSR=RCC_APB5RSTSR_CSIRSTS | RCC_APB5RSTSR_DCMIPPRSTS;
    RCC->AHB5RSTSR=RCC_AHB5RSTSR_SDMMC2RSTS;
    RCC->APB1RSTSR1=RCC_APB1RSTSR1_I2C2RSTS;
    __DSB();
    RCC->APB5ENCR=RCC_APB5ENCR_CSIENC | RCC_APB5ENCR_DCMIPPENC;
    RCC->DIVENCR=RCC_DIVENCR_IC17ENC | RCC_DIVENCR_IC18ENC;
    RCC->AHB5ENCR=RCC_AHB5ENCR_SDMMC2ENC;
    RCC->APB1ENCR1=RCC_APB1ENCR1_I2C2ENC;
    RCC->AHB4ENSR=GPIO_CLOCKS;
    __DSB();
    if ((RCC->AHB4ENR & GPIO_CLOCKS)!=GPIO_CLOCKS || (RCC->AHB4RSTR & GPIO_RESETS))
        return 0;
    GPIOG->BSRR=LEDS;
    GPIOG->OTYPER &= ~LEDS;
    GPIOG->PUPDR &= ~LED_MODES;
    GPIOG->MODER=(GPIOG->MODER & ~LED_MODES) | (LED_MODES/3U);
    /* Reset the sensor and release I2C/SD lines without retaining pulls into
     * the rails that turn off in Standby. PE6 (UART recovery) is untouched. */
    GPIOO->BSRR=1UL << 21;
    GPIOO->OTYPER &= ~(1UL << 5);
    GPIOO->PUPDR &= ~(3UL << 10);
    GPIOO->MODER=(GPIOO->MODER & ~(3UL << 10)) | (1UL << 10);
    GPIOB->MODER |= (3UL << 20) | (3UL << 22);
    GPIOB->PUPDR &= ~((3UL << 20) | (3UL << 22));
    GPIOC->MODER |= SD_PIN_MODES;
    GPIOC->PUPDR &= ~SD_PIN_MODES;
    GPIOE->MODER |= 3UL << 8;
    GPIOE->PUPDR &= ~(3UL << 8);
    /* Deselect NOR before resetting its host; never send deep-power-down.
     * The ROM must read it before the UART guard can run on the next reset. */
    GPION->BSRR=1UL << 1;
    GPION->OTYPER &= ~(1UL << 1);
    GPION->MODER=(GPION->MODER & ~(3UL << 2)) | (1UL << 2);
    __DSB();
    RCC->AHB5RSTSR=RCC_AHB5RSTSR_XSPI1RSTS;
    __DSB();
    RCC->AHB5ENCR=RCC_AHB5ENCR_XSPI1ENC | RCC_AHB5ENCR_XSPIMENC;
    GPION->MODER |= NOR_PIN_MODES;
    GPION->PUPDR &= ~(NOR_PIN_MODES | (3UL << 2));
    __DSB();
    /* The timing claim is conditional on the same checked 400 MHz profile
     * used by stage1. No guessed software delay after a clock failure. */
    if (__get_IPSR() || __get_FAULTMASK() || (__get_CONTROL() & 3U) ||
        (SCB->CCR & SCB_CCR_DC_Msk) ||
        RCC->CFGR1!=0x33330000U || RCC->CFGR2!=0x00100000U ||
        RCC->PLL1CFGR1!=0x00404B00U || RCC->PLL1CFGR2 ||
        RCC->PLL1CFGR3!=0x49000005U ||
        (RCC->IC1CFGR & (RCC_IC1CFGR_IC1SEL | RCC_IC1CFGR_IC1INT))!=
            (2U << RCC_IC1CFGR_IC1INT_Pos) ||
        (RCC->HSICFGR & RCC_HSICFGR_HSIDIV)) return 0;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    return (DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk)!=0U;
}

INLINE int error_platform_delay(uint32_t ms)
{
    uint32_t start=DWT->CYCCNT,previous=start,stalled=0U;
    uint32_t cycles=ms*400000U;
    while ((uint32_t)(DWT->CYCCNT-start)<cycles) {
        uint32_t now=DWT->CYCCNT;
        /* A stopped counter must not leave the LED on forever. */
        stalled=(now==previous)?stalled+1U:0U;
        if (stalled==100000U) return 0;
        previous=now;
    }
    return 1;
}

INLINE __attribute__((noreturn)) void error_platform_end(void)
{
    /* GPIOG may itself be inaccessible after a platform fault. */
    if ((RCC->AHB4ENR & RCC_AHB4ENR_GPIOGEN) && !(RCC->AHB4RSTR & RCC_AHB4RSTR_GPIOGRST))
        error_platform_led(0U);
    __disable_irq();
    unsigned banks=(ICB->ICTR & ICB_ICTR_INTLINESNUM_Msk)+1U;
    for (unsigned i=0;i<banks;i++) { NVIC->ICER[i]=~0U; NVIC->ICPR[i]=~0U; }
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
    SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk | SCB_SCR_SLEEPONEXIT_Msk | SCB_SCR_SEVONPEND_Msk);
    RCC->APB4ENSR2=RCC_APB4ENSR2_BSECENS;
    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS;
    __DSB();
    if (__get_IPSR() || __get_FAULTMASK() || (__get_CONTROL() & 3U) ||
        (SCB->CCR & SCB_CCR_DC_Msk) || (FPU->FPCCR & FPU_FPCCR_LSPACT_Msk) ||
        !(RCC->APB4ENR2 & RCC_APB4ENR2_BSECEN) ||
        !(RCC->AHB4ENR & RCC_AHB4ENR_PWREN) || (RCC->AHB4RSTR & RCC_AHB4RSTR_PWRRST) ||
        !(RCC->MISCENR & RCC_MISCENR_DBGEN) || (RCC->MISCRSTR & RCC_MISCRSTR_DBGRST)) goto shallow;
    /* Existing shadows only: never OTP load/program or backup-domain writes. */
    if (!(BSEC->SFSRx[3] & (1UL << 28)) || !(BSEC->OTPVLDRx[3] & (1UL << 28)) ||
        (BSEC->FVRw[124] & ((1UL << 11) | 1U))) goto shallow;
    DBGMCU->CR &= ~(DBGMCU_CR_DBG_SLEEP | DBGMCU_CR_DBG_STOP | DBGMCU_CR_DBG_STANDBY);
    if (DBGMCU->CR & (DBGMCU_CR_DBG_SLEEP | DBGMCU_CR_DBG_STOP | DBGMCU_CR_DBG_STANDBY)) goto shallow;
    SCB_DisableICache();
    EXTI->IMR1=0; EXTI->IMR2=0; EXTI->IMR3=0;
    EXTI->EMR1=0; EXTI->EMR2=0; EXTI->EMR3=0;
    EXTI->RTSR1=0; EXTI->RTSR2=0; EXTI->RTSR3=0;
    EXTI->FTSR1=0; EXTI->FTSR2=0; EXTI->FTSR3=0;
    EXTI->RPR1=EXTI->RPR1; EXTI->RPR2=EXTI->RPR2; EXTI->RPR3=EXTI->RPR3;
    EXTI->FPR1=EXTI->FPR1; EXTI->FPR2=EXTI->FPR2; EXTI->FPR3=EXTI->FPR3;
    PWR->WKUPEPR &= ~PWR_WKUPEPR_WKUPEN;
    PWR->WKUPCR=PWR_WKUPCR_WKUPC;
    RCC->STOPCCR=RCC_STOPCCR_HSISTOPENC | RCC_STOPCCR_MSISTOPENC;
    PWR->CR4 &= ~(PWR_CR4_TCMRBSEN | PWR_CR4_TCMFLXRBSEN);
    PWR->CPUCR=(PWR->CPUCR & ~PWR_CPUCR_SVOS) | PWR_CPUCR_PDDS | PWR_CPUCR_CSSF;
    __DSB();
    if ((PWR->CPUCR & (PWR_CPUCR_PDDS | PWR_CPUCR_SVOS))!=PWR_CPUCR_PDDS ||
        (PWR->WKUPEPR & PWR_WKUPEPR_WKUPEN) || PWR->WKUPSR ||
        EXTI->IMR1 || EXTI->IMR2 || EXTI->IMR3 ||
        EXTI->EMR1 || EXTI->EMR2 || EXTI->EMR3 ||
        EXTI->RPR1 || EXTI->RPR2 || EXTI->RPR3 ||
        EXTI->FPR1 || EXTI->FPR2 || EXTI->FPR3 ||
        (RCC->STOPCR & (RCC_STOPCR_HSISTOPEN | RCC_STOPCR_MSISTOPEN))) goto shallow;
    for (unsigned i=0;i<banks;i++)
        if (NVIC->ISER[i] || NVIC->ISPR[i]) goto shallow;
    SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;
    __DSB(); __ISB(); __WFI();
    /* An unexpected return must not start another capture or reset loop. */
shallow:
    SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;
    for (;;) { __DSB(); __WFI(); }
}
#endif

__attribute__((noreturn,noinline,noclone,used,section(".error_text")))
void error_signal_shutdown(uint32_t code)
{
    if (code<1U || code>ERROR_SIGNAL_INTERNAL) code=ERROR_SIGNAL_INTERNAL;
    if (error_platform_begin()) {
        for (unsigned set=0;set<ERROR_SIGNAL_SETS;set++) {
            for (unsigned blink=0;blink<code;blink++) {
                error_platform_led(1U);
                if (!error_platform_delay(ERROR_SIGNAL_ON_MS)) goto done;
                error_platform_led(0U);
                uint32_t dark=(blink+1U<code || set+1U==ERROR_SIGNAL_SETS)?
                    ERROR_SIGNAL_OFF_MS:ERROR_SIGNAL_SET_GAP_MS;
                if (!error_platform_delay(dark)) goto done;
            }
        }
    }
done:
    error_platform_end();
}
