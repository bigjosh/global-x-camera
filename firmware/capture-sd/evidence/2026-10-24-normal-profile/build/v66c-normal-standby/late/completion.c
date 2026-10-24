/* Reset-only experimental completion. No reset, power switch, OTP write, or
 * retry is issued here. The unchanged first-stage PE1/PE6 guard is the recovery
 * path after an independently verified reset/cold cycle.
 *
 * References: RM0486 rev4 Â§Â§13.7.3â€“13.7.7,14.5.4,78.12.20;
 * ES0620 rev5 Â§Â§2.2.2,2.2.18,2.2.22. Debug access while asleep is not promised.
 */
#include "completion.h"
#include "peripherals.h"
#include "status_leds.h"
#include "phase_gpio.h"

#ifndef LOW_POWER_MODE
#error LOW_POWER_MODE must be selected explicitly: 0=off/awake,1=sleep,2=stop,3=standby
#endif
#if LOW_POWER_MODE < 0 || LOW_POWER_MODE > 3
#error Invalid LOW_POWER_MODE
#endif
#ifndef LOW_POWER_ENTRY_DELAY_US
#define LOW_POWER_ENTRY_DELAY_US 0U
#endif
#if LOW_POWER_ENTRY_DELAY_US > 1000000U
#error Diagnostic entry delay must not exceed one second
#endif
#define LP ((volatile uint32_t *)LOW_POWER_PROOF_ADDRESS)
#define NOMINAL_CPU_HZ 400000000U
#define OTP_HCONF1 124U
#define OTP_HCONF1_BIT (1UL << (OTP_HCONF1 % 32U))
#define DEBUG_EMULATION (DBGMCU_CR_DBG_SLEEP | DBGMCU_CR_DBG_STOP | DBGMCU_CR_DBG_STANDBY)
_Static_assert(sizeof(camera_peripheral_proof_t)<=256U, "Peripheral proof overlaps loader");

static void publish(uint32_t state)
{
    LP[LPC_TERMINAL]=0U;
    LP[LPC_STATE]=state;
    uint32_t hash=2166136261U;
    for (unsigned word=1U; word<LPC_CHECKSUM; ++word) {
        uint32_t value=LP[word];
        for (unsigned byte=0U; byte<4U; ++byte) {
            hash=(hash ^ (value & 255U))*16777619U;
            value >>= 8U;
        }
    }
    LP[LPC_CHECKSUM]=hash;
    __DMB();
    LP[LPC_TERMINAL]=LOW_POWER_PROOF_TERMINAL;
    __DSB();
}

__attribute__((noreturn,noinline,used)) static void refused(uint32_t error)
{
    LP[LPC_ERROR]=error;
    status_led_set(STATUS_LED_ERROR);
    publish(LPC_STATE_REFUSED);
    __asm volatile(".global low_power_failure_idle\n"
                   "low_power_failure_idle:\n"
                   "b.n low_power_failure_idle\n");
    __builtin_unreachable();
}

static void mask_cpu_interrupts(void)
{
    __disable_irq();
    SysTick->CTRL=0U;
    SysTick->VAL=0U;
    unsigned banks=(ICB->ICTR & ICB_ICTR_INTLINESNUM_Msk)+1U;
    for (unsigned i=0U; i<banks; ++i) {
        NVIC->ICER[i]=0xFFFFFFFFU;
        NVIC->ICPR[i]=0xFFFFFFFFU;
    }
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
    __DSB(); __ISB();
    uint32_t enabled=0U,pending=0U;
    for (unsigned i=0U; i<banks; ++i) {
        enabled |= NVIC->ISER[i];
        pending |= NVIC->ISPR[i];
    }
    LP[LPC_NVIC_ENABLE_OR]=enabled;
    LP[LPC_NVIC_PENDING_OR]=pending;
    LP[LPC_SYSTICK_CTRL]=SysTick->CTRL;
    LP[LPC_PRIMASK]=__get_PRIMASK();
    LP[LPC_ICSR]=SCB->ICSR;
    if (enabled || pending) refused(LPC_ERROR_PENDING_SOURCE);
}

static void prepare_mode(void)
{
    /* BSEC clock must remain enabled even for ordinary Sleep: ES0620 Â§2.2.2.
     * Set aliases only; never touch a broad clock-enable register mask. */
    RCC->APB4ENSR2=RCC_APB4ENSR2_BSECENS;
    LP[LPC_RCC_APB4ENR2]=RCC->APB4ENR2;
    if (!(LP[LPC_RCC_APB4ENR2] & RCC_APB4ENR2_BSECEN))
        refused(LPC_ERROR_BSEC_CLOCK);
    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS;
    LP[LPC_RCC_AHB4ENR]=RCC->AHB4ENR;
    if (!(LP[LPC_RCC_AHB4ENR] & RCC_AHB4ENR_PWREN) ||
        (RCC->AHB4RSTR & RCC_AHB4RSTR_PWRRST))
        refused(LPC_ERROR_PWR_ACCESS);
    LP[LPC_PWR_CPUCR_BEFORE]=PWR->CPUCR;
    LP[LPC_PWR_CR1]=PWR->CR1;
    LP[LPC_RCC_RSR]=RCC->RSR;
    LP[LPC_CCR]=SCB->CCR;
    if (__get_IPSR() || (SCB->CCR & (SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)))
        refused(LPC_ERROR_CPU_CONTEXT);

#if LOW_POWER_MODE != 0
    /* Read only while debug bus is clocked and released. Retain bus clocks and
     * DBGCLKEN; clear only emulation bits so these cannot fake low-power entry. */
    if (!(RCC->MISCENR & RCC_MISCENR_DBGEN) ||
        (RCC->MISCRSTR & RCC_MISCRSTR_DBGRST))
        refused(LPC_ERROR_DEBUG_ACCESS);
    LP[LPC_DBG_CR_BEFORE]=DBGMCU->CR;
    DBGMCU->CR &= ~DEBUG_EMULATION;
    LP[LPC_DBG_CR_AFTER]=DBGMCU->CR;
    if (LP[LPC_DBG_CR_AFTER] & DEBUG_EMULATION)
        refused(LPC_ERROR_DEBUG_EMULATION);
#endif
    SCB->SCR &= ~(SCB_SCR_SLEEPDEEP_Msk | SCB_SCR_SLEEPONEXIT_Msk |
                  SCB_SCR_SEVONPEND_Msk);

#if LOW_POWER_MODE >= 2
    /* Read existing shadows only; no fuse load/program or backup-domain write.
     * Unknown shadow state cannot safely be interpreted as option bits zero. */
    LP[LPC_OTP124_SHADOWED]=BSEC->SFSRx[OTP_HCONF1/32U] & OTP_HCONF1_BIT;
    LP[LPC_OTP124_VALID]=BSEC->OTPVLDRx[OTP_HCONF1/32U] & OTP_HCONF1_BIT;
    if (!LP[LPC_OTP124_SHADOWED] || !LP[LPC_OTP124_VALID])
        refused(LPC_ERROR_OTP_UNKNOWN);
    LP[LPC_OTP124_VALUE]=BSEC->FVRw[OTP_HCONF1];
    const uint32_t reset_option=(LOW_POWER_MODE==2) ? (1U<<10U) : (1U<<11U);
    if (LP[LPC_OTP124_VALUE] & reset_option) refused(LPC_ERROR_LOWPOWER_RESET_OPTION);
    if (LP[LPC_OTP124_VALUE] & 1U) refused(LPC_ERROR_HARDWARE_IWDG);

    /* This terminal mode supports NRST/cold restart only. An RTC/WKUP Standby
     * wake uses retained INITSVTOR; it must not vector into powered-off SRAM.
     * Mask all EXTI paths, stop edge generation and clear observed pending bits.
     * Preserve security configuration and reserved bits. */
    EXTI->IMR1=0U; EXTI->IMR2=0U; EXTI->IMR3=0U;
    EXTI->EMR1=0U; EXTI->EMR2=0U; EXTI->EMR3=0U;
    EXTI->RTSR1=0U; EXTI->RTSR2=0U; EXTI->RTSR3=0U;
    EXTI->FTSR1=0U; EXTI->FTSR2=0U; EXTI->FTSR3=0U;
    EXTI->RPR1=EXTI->RPR1; EXTI->RPR2=EXTI->RPR2; EXTI->RPR3=EXTI->RPR3;
    EXTI->FPR1=EXTI->FPR1; EXTI->FPR2=EXTI->FPR2; EXTI->FPR3=EXTI->FPR3;
    PWR->WKUPEPR &= ~PWR_WKUPEPR_WKUPEN;
    PWR->WKUPCR=PWR_WKUPCR_WKUPC;
    RCC->STOPCCR=RCC_STOPCCR_HSISTOPENC | RCC_STOPCCR_MSISTOPENC;
    uint32_t cpucr=PWR->CPUCR & ~(PWR_CPUCR_PDDS | PWR_CPUCR_SVOS);
#if LOW_POWER_MODE == 2
    /* RM0486 §13.4.3: bypass/external VCORE permits SVOS high only.
     * Nucleo uses an external regulator. Internal SMPS permits SVOS low. */
    if (!(PWR->CR1 & PWR_CR1_SDEN)) cpucr |= PWR_CPUCR_SVOS;
#endif
#if LOW_POWER_MODE == 3
    cpucr |= PWR_CPUCR_PDDS;
    /* No retained executable path is used. No VBAT/RTC/backup SRAM changes. */
    PWR->CR4 &= ~(PWR_CR4_TCMRBSEN | PWR_CR4_TCMFLXRBSEN);
#endif
    PWR->CPUCR=cpucr | PWR_CPUCR_CSSF;
    SCB->SCR |= SCB_SCR_SLEEPDEEP_Msk;
    __DSB(); __ISB();
    LP[LPC_EXTI_IMR_OR]=EXTI->IMR1 | EXTI->IMR2 | EXTI->IMR3;
    LP[LPC_EXTI_EMR_OR]=EXTI->EMR1 | EXTI->EMR2 | EXTI->EMR3;
    LP[LPC_EXTI_RPR_OR]=EXTI->RPR1 | EXTI->RPR2 | EXTI->RPR3;
    LP[LPC_EXTI_FPR_OR]=EXTI->FPR1 | EXTI->FPR2 | EXTI->FPR3;
    if (LP[LPC_EXTI_IMR_OR] || LP[LPC_EXTI_EMR_OR] ||
        LP[LPC_EXTI_RPR_OR] || LP[LPC_EXTI_FPR_OR] ||
        (PWR->WKUPEPR & PWR_WKUPEPR_WKUPEN) || PWR->WKUPSR)
        refused(LPC_ERROR_PENDING_SOURCE);
    if ((PWR->CPUCR & (PWR_CPUCR_PDDS|PWR_CPUCR_SVOS)) !=
        (cpucr & (PWR_CPUCR_PDDS|PWR_CPUCR_SVOS)) ||
        (RCC->STOPCR & (RCC_STOPCR_HSISTOPEN|RCC_STOPCR_MSISTOPEN)))
        refused(LPC_ERROR_MODE_READBACK);
#endif
    LP[LPC_PWR_CPUCR_AFTER]=PWR->CPUCR;
    LP[LPC_PWR_CR4]=PWR->CR4;
    LP[LPC_PWR_WKUPEPR]=PWR->WKUPEPR;
    LP[LPC_PWR_WKUPSR]=PWR->WKUPSR;
    LP[LPC_RCC_STOPCR]=RCC->STOPCR;
    LP[LPC_SCR]=SCB->SCR;
}

__attribute__((noreturn,noinline,used)) void status_led_complete_sleep(void)
{
    for (unsigned i=0U; i<LOW_POWER_PROOF_WORDS; ++i) LP[i]=0U;
    LP[LPC_SCHEMA]=1U;
    LP[LPC_WORDS]=LOW_POWER_PROOF_WORDS;
    LP[LPC_MODE]=LOW_POWER_MODE;
    LP[LPC_STATE]=LPC_STATE_BEGIN;
    LP[LPC_BEGIN_CYCLES]=DWT->CYCCNT;
    LP[LPC_DELAY_US]=LOW_POWER_ENTRY_DELAY_US;
    LP[LPC_CPU_HZ]=NOMINAL_CPU_HZ;
    __DMB();
    LP[LPC_MAGIC]=LOW_POWER_PROOF_MAGIC;
    volatile camera_peripheral_proof_t *peripheral =
        (volatile camera_peripheral_proof_t *)LOW_POWER_PERIPHERAL_PROOF_ADDRESS;
    for (unsigned i=0U; i<64U; ++i) peripheral->word[i]=0U;
    __disable_irq();
    /* Interface supplied by peripherals.c: validates successful automatic SAVE,
     * idle/deinitialized card and CPU/cache context before touching hardware. */
    LP[LPC_PERIPHERAL_RESULT]=camera_peripherals_shutdown(peripheral);
    if (LP[LPC_PERIPHERAL_RESULT]) refused(LPC_ERROR_PERIPHERALS);
    publish(LPC_STATE_PERIPHERALS_OFF);
    status_led_set(STATUS_LED_OFF);
    mask_cpu_interrupts();
    prepare_mode();
    STATUS_LED_PROOF[LED_P_PHASE]=STATUS_LED_OFF;
    status_led_proof_sample(LED_P_SLEEP_CYCLE);
    STATUS_LED_PROOF[LED_P_SCR]=SCB->SCR;
    STATUS_LED_PROOF[LED_P_PRIMASK]=__get_PRIMASK();
    STATUS_LED_PROOF[LED_P_SYSTICK_CTRL]=SysTick->CTRL;
    STATUS_LED_PROOF[LED_P_ICSR]=SCB->ICSR;
    STATUS_LED_PROOF[LED_P_NVIC_ENABLE_OR]=LP[LPC_NVIC_ENABLE_OR];
    STATUS_LED_PROOF[LED_P_NVIC_PENDING_OR]=LP[LPC_NVIC_PENDING_OR];
    STATUS_LED_PROOF[LED_P_SLEEP_STATE]=0x100U+LOW_POWER_MODE;
    LP[LPC_GPIOG_ODR]=GPIOG->ODR;
    publish(LPC_STATE_PREPARED);
#if LOW_POWER_ENTRY_DELAY_US > 0
    if (!(DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) ||
        !(CoreDebug->DEMCR & CoreDebug_DEMCR_TRCENA_Msk))
        refused(LPC_ERROR_DELAY_CLOCK);
    uint32_t began=DWT->CYCCNT;
    while ((uint32_t)(DWT->CYCCNT-began) < LOW_POWER_ENTRY_DELAY_US*400U)
        __NOP();
#endif
    LP[LPC_ARM_CYCLES]=DWT->CYCCNT;
    publish(LPC_STATE_ARMED);
    (void)phase_gpio_emit(10U);
    __DSB(); __ISB();
#if LOW_POWER_MODE == 0
    __asm volatile(".global status_led_sleep_idle\n"
                   "status_led_sleep_idle:\n"
                   "nop\nb.n status_led_sleep_idle\n");
#else
    __asm volatile(".global status_led_sleep_idle\n"
                   "status_led_sleep_idle:\n"
                   "wfi\n" ::: "memory");
    /* A debugger may wake a real Stop/Sleep. Do not silently reenter, restart
     * capture, issue reset, or claim Standby was reached. Record and park. */
    LP[LPC_RETURN_CYCLES]=DWT->CYCCNT;
    LP[LPC_PWR_CPUCR_RETURN]=PWR->CPUCR;
    LP[LPC_SCR_RETURN]=SCB->SCR;
    SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;
    LP[LPC_ERROR]=LPC_ERROR_UNEXPECTED_RETURN;
    status_led_set(STATUS_LED_ERROR);
    publish(LPC_STATE_RETURNED);
    __asm volatile(".global low_power_return_idle\n"
                   "low_power_return_idle:\n"
                   "b.n low_power_return_idle\n");
#endif
    __builtin_unreachable();
}
