/* USB-only terminal teardown. Standby guards are adapted from
 * capture-sd/low_power/completion.c and capture-raw/error_signal.c; the final
 * HOLD stays LOW in USB service/refusal and floats at the terminal WFI.
 * An unexpected return keeps it OFF; only battery capture may assert HOLD.
 * The capture success record is deliberately NOT reused or forged here.
 * No live USB/SD operation may call this code, including from an IRQ.
 */
#include "shutdown.h"
#include <stddef.h>
#ifdef USB_SHUTDOWN_HOST_TEST
#include "shutdown_test_platform.h"
#else
#include "stm32n657xx.h"
_Static_assert(GPIOD_BASE==0x56020C00UL,"HOLD requires secure GPIOD");
_Static_assert(offsetof(GPIO_TypeDef,MODER)==0U,"HOLD MODER offset");
_Static_assert(offsetof(GPIO_TypeDef,PUPDR)==12U,"HOLD PUPDR offset");
_Static_assert(offsetof(GPIO_TypeDef,BSRR)==24U,"HOLD BSRR offset");
#endif
#include "usb_hold.h"

#define LEDS ((1UL<<10)|(1UL<<8)|1UL)
#define LED_MODES ((3UL<<20)|(3UL<<16)|3UL)
#define SD_MODES ((3UL<<0)|(3UL<<4)|(3UL<<6)|(3UL<<8)|(3UL<<10))
#define NOR_MODES ((3UL<<4)|(3UL<<6)|(3UL<<12))
#define GPIO_CLOCKS (RCC_AHB4ENR_GPIOAEN|RCC_AHB4ENR_GPIOBEN|RCC_AHB4ENR_GPIOCEN|RCC_AHB4ENR_GPIODEN|RCC_AHB4ENR_GPIOEEN|RCC_AHB4ENR_GPIOGEN|RCC_AHB4ENR_GPIONEN|RCC_AHB4ENR_GPIOOEN)
#define GPIO_RESETS (RCC_AHB4RSTR_GPIOARST|RCC_AHB4RSTR_GPIOBRST|RCC_AHB4RSTR_GPIOCRST|RCC_AHB4RSTR_GPIODRST|RCC_AHB4RSTR_GPIOERST|RCC_AHB4RSTR_GPIOGRST|RCC_AHB4RSTR_GPIONRST|RCC_AHB4RSTR_GPIOORST)
#define DEBUG_EMULATION (DBGMCU_CR_DBG_SLEEP|DBGMCU_CR_DBG_STOP|DBGMCU_CR_DBG_STANDBY)
#define USB_CLOCKS (RCC_AHB5ENR_OTG1EN|RCC_AHB5ENR_OTGPHY1EN)
#define USB_RESETS (RCC_AHB5RSTR_OTG1RST|RCC_AHB5RSTR_OTGPHY1RST|RCC_AHB5RSTR_OTG1PHYCTLRST)
#define OTP_BIT (1UL<<28)

volatile usb_shutdown_proof_t usb_shutdown_proof;
#define S usb_shutdown_proof

static void publish(uint32_t state)
{
    S.seal=0U; S.state=state;
    const volatile uint32_t *p=(const volatile uint32_t *)&S;
    uint32_t hash=2166136261U;
    for(unsigned i=0;i<offsetof(usb_shutdown_proof_t,checksum)/4U;i++) {
        uint32_t value=p[i];
        for(unsigned j=0;j<4;j++){hash=(hash^(value&255U))*16777619U;value>>=8;}
    }
    S.checksum=hash; __DMB(); S.seal=USB_SHUTDOWN_SEAL; __DSB();
}

static int release_hold(void)
{
    int off=usb_hold_off();
    if(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIODEN) ||
       (RCC->AHB4RSTR&RCC_AHB4RSTR_GPIODRST)) return 0;
    S.hold_moder=GPIOD->MODER; S.hold_pupdr=GPIOD->PUPDR;
    S.hold_odr=GPIOD->ODR; S.hold_idr=GPIOD->IDR;
    return off;
}

__attribute__((noreturn,noinline)) static void refuse(uint32_t error,uint32_t state)
{
    /* A failed USB shutdown must not fall back to battery power. */
    S.error=error; S.hold_verified=(uint32_t)release_hold();
    SCB->SCR&=~(SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk|SCB_SCR_SEVONPEND_Msk);
    publish(state);
#ifdef USB_SHUTDOWN_HOST_TEST
    usb_shutdown_test_park();
#else
    __asm volatile(".global usb_shutdown_refused_park\n"
                   "usb_shutdown_refused_park:\n"
                   "b.n usb_shutdown_refused_park\n");
#endif
    __builtin_unreachable();
}
#define REQUIRE(condition,error) do{if(!(condition))refuse((error),USB_SHUTDOWN_REFUSED);}while(0)

static void peripherals_off(void)
{
    /* Caller proves clean SD completion; the independent RCC check prevents
     * resetting an enabled SD host. A gated host alone does not prove idle. */
    S.ahb5enr_before=RCC->AHB5ENR;
    REQUIRE(!(S.ahb5enr_before&RCC_AHB5ENR_SDMMC2EN),USB_SHUTDOWN_STORAGE_ACTIVE);
    REQUIRE(!(S.ahb5enr_before&(RCC_AHB5ENR_XSPI2EN|RCC_AHB5ENR_XSPI3EN|
            RCC_AHB5ENR_OTG2EN|RCC_AHB5ENR_OTGPHY2EN)) &&
            !(RCC->APB5ENR&(RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN)) &&
            !(RCC->APB1ENR1&RCC_APB1ENR1_I2C2EN),USB_SHUTDOWN_OTHER_CLIENT_ACTIVE);

    /* Do not retain internal pulls into switched-off card/sensor supplies.
     * Only the named pins change; PE6 UART and PD12 HOLD remain untouched. */
    GPIOC->MODER|=SD_MODES; GPIOC->PUPDR&=~SD_MODES;
    GPIOE->MODER|=3UL<<8; GPIOE->PUPDR&=~(3UL<<8);
    GPIOB->MODER|=(3UL<<20)|(3UL<<22); GPIOB->PUPDR&=~((3UL<<20)|(3UL<<22));
    GPIOO->BSRR=1UL<<21; GPIOO->OTYPER&=~(1UL<<5);
    GPIOO->PUPDR&=~(3UL<<10); GPIOO->MODER=(GPIOO->MODER&~(3UL<<10))|(1UL<<10);
    GPIOG->BSRR=LEDS; GPIOG->OTYPER&=~LEDS; GPIOG->PUPDR&=~LED_MODES;
    GPIOG->MODER=(GPIOG->MODER&~LED_MODES)|(LED_MODES/3U);
    /* NOR nCS HIGH before taking its host down. No command/deep-power-down:
     * ROM must read this NOR before the unchanged UART recovery guard. */
    GPION->BSRR=1UL<<1; GPION->OTYPER&=~(1UL<<1);
    GPION->MODER=(GPION->MODER&~(3UL<<2))|(1UL<<2); __DSB();
    REQUIRE((GPION->IDR&(1UL<<1)) && !(GPIOO->IDR&(1UL<<5)),USB_SHUTDOWN_PIN_READBACK);
    RCC->AHB5RSTSR=RCC_AHB5RSTSR_XSPI1RSTS|RCC_AHB5RSTSR_OTG1RSTS|
        RCC_AHB5RSTSR_OTGPHY1RSTS|RCC_AHB5RSTSR_OTG1PHYCTLRSTS; __DSB();
    RCC->AHB5ENCR=RCC_AHB5ENCR_XSPI1ENC|RCC_AHB5ENCR_XSPIMENC|
        RCC_AHB5ENCR_OTG1ENC|RCC_AHB5ENCR_OTGPHY1ENC;
    RCC->AHB5LPENCR=RCC_AHB5LPENCR_XSPI1LPENC|RCC_AHB5LPENCR_XSPIMLPENC|
        RCC_AHB5LPENCR_OTG1LPENC|RCC_AHB5LPENCR_OTGPHY1LPENC;
    GPION->MODER|=NOR_MODES; GPION->PUPDR&=~(NOR_MODES|(3UL<<2));
    /* USB1 is stopped/reset, no USB2 client exists; remove only USB supply
     * validity/monitor bits. Do not touch ADC, VDDIO, RTC or backup supplies. */
    PWR->SVMCR3&=~(PWR_SVMCR3_USB33SV|PWR_SVMCR3_USB33VMEN); __DSB();
    S.svmcr3_after=PWR->SVMCR3; S.ahb5enr_after=RCC->AHB5ENR;
    REQUIRE(!(S.ahb5enr_after&(USB_CLOCKS|RCC_AHB5ENR_XSPI1EN|RCC_AHB5ENR_XSPIMEN|RCC_AHB5ENR_SDMMC2EN)) &&
            (RCC->AHB5RSTR&USB_RESETS)==USB_RESETS &&
            !(S.svmcr3_after&(PWR_SVMCR3_USB33SV|PWR_SVMCR3_USB33VMEN)) &&
            (GPIOC->MODER&SD_MODES)==SD_MODES && !(GPIOC->PUPDR&SD_MODES) &&
            (GPIOE->MODER&(3UL<<8))==(3UL<<8) && !(GPIOE->PUPDR&(3UL<<8)),
            USB_SHUTDOWN_PERIPHERAL_READBACK);
}

static void prepare_standby(void)
{
    /* Keep the legacy BSEC clock and existing-shadow guards. No OTP load or
     * program, no option-byte mutation and no backup-domain reset. */
    REQUIRE((RCC->MISCENR&RCC_MISCENR_DBGEN) && !(RCC->MISCRSTR&RCC_MISCRSTR_DBGRST),USB_SHUTDOWN_DEBUG_UNAVAILABLE);
    S.dbg_cr_before=DBGMCU->CR; DBGMCU->CR&=~DEBUG_EMULATION; __DSB();
    S.dbg_cr_after=DBGMCU->CR;
    REQUIRE(!(S.dbg_cr_after&DEBUG_EMULATION),USB_SHUTDOWN_DEBUG_EMULATION);
    S.otp_shadowed=BSEC->SFSRx[3]&OTP_BIT; S.otp_valid=BSEC->OTPVLDRx[3]&OTP_BIT;
    REQUIRE(S.otp_shadowed && S.otp_valid,USB_SHUTDOWN_OTP_UNKNOWN);
    S.otp_value=BSEC->FVRw[124];
    REQUIRE(!(S.otp_value&(1UL<<11)),USB_SHUTDOWN_RESET_OPTION);
    REQUIRE(!(S.otp_value&1U),USB_SHUTDOWN_HARDWARE_WATCHDOG);

    SysTick->CTRL=0U; SysTick->VAL=0U;
    unsigned banks=(ICB->ICTR&ICB_ICTR_INTLINESNUM_Msk)+1U;
    for(unsigned i=0;i<banks;i++){NVIC->ICER[i]=~0U;NVIC->ICPR[i]=~0U;}
    SCB->ICSR=SCB_ICSR_PENDSTCLR_Msk|SCB_ICSR_PENDSVCLR_Msk;
    SCB->SCR&=~(SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk|SCB_SCR_SEVONPEND_Msk);
    EXTI->IMR1=0; EXTI->IMR2=0; EXTI->IMR3=0;
    EXTI->EMR1=0; EXTI->EMR2=0; EXTI->EMR3=0;
    EXTI->RTSR1=0; EXTI->RTSR2=0; EXTI->RTSR3=0;
    EXTI->FTSR1=0; EXTI->FTSR2=0; EXTI->FTSR3=0;
    EXTI->RPR1=EXTI->RPR1; EXTI->RPR2=EXTI->RPR2; EXTI->RPR3=EXTI->RPR3;
    EXTI->FPR1=EXTI->FPR1; EXTI->FPR2=EXTI->FPR2; EXTI->FPR3=EXTI->FPR3;
    PWR->WKUPEPR&=~PWR_WKUPEPR_WKUPEN; PWR->WKUPCR=PWR_WKUPCR_WKUPC;
    RCC->STOPCCR=RCC_STOPCCR_HSISTOPENC|RCC_STOPCCR_MSISTOPENC;
    S.cpucr_before=PWR->CPUCR;
    uint32_t cpucr=(S.cpucr_before&~(PWR_CPUCR_PDDS|PWR_CPUCR_SVOS))|PWR_CPUCR_PDDS;
    PWR->CR4&=~(PWR_CR4_TCMRBSEN|PWR_CR4_TCMFLXRBSEN);
    PWR->CPUCR=cpucr|PWR_CPUCR_CSSF; __DSB(); __ISB();
    S.exti_pending=EXTI->RPR1|EXTI->RPR2|EXTI->RPR3|EXTI->FPR1|EXTI->FPR2|EXTI->FPR3;
    S.wkup_enable=PWR->WKUPEPR; S.wkup_status=PWR->WKUPSR;
    S.cpucr_after=PWR->CPUCR; S.cr4_after=PWR->CR4; S.stopcr=RCC->STOPCR;
    S.nvic_enabled=0;S.nvic_pending=0;
    for(unsigned i=0;i<banks;i++){S.nvic_enabled|=NVIC->ISER[i];S.nvic_pending|=NVIC->ISPR[i];}
    S.systick_ctrl=SysTick->CTRL;
    REQUIRE(!S.exti_pending && !S.nvic_enabled && !S.nvic_pending && !S.systick_ctrl &&
            !(EXTI->IMR1|EXTI->IMR2|EXTI->IMR3|EXTI->EMR1|EXTI->EMR2|EXTI->EMR3) &&
            !(S.wkup_enable&PWR_WKUPEPR_WKUPEN) && !S.wkup_status,USB_SHUTDOWN_PENDING_SOURCE);
    REQUIRE((S.cpucr_after&(PWR_CPUCR_PDDS|PWR_CPUCR_SVOS))==PWR_CPUCR_PDDS &&
            !(S.stopcr&(RCC_STOPCR_HSISTOPEN|RCC_STOPCR_MSISTOPEN)) &&
            !(S.cr4_after&(PWR_CR4_TCMRBSEN|PWR_CR4_TCMFLXRBSEN)),USB_SHUTDOWN_MODE_READBACK);
    SCB->SCR|=SCB_SCR_SLEEPDEEP_Msk; __DSB(); __ISB(); S.scr_after=SCB->SCR;
    REQUIRE((S.scr_after&(SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk|SCB_SCR_SEVONPEND_Msk))==SCB_SCR_SLEEPDEEP_Msk &&
            __get_PRIMASK()==1U,USB_SHUTDOWN_MODE_READBACK);
}

__attribute__((noreturn,noinline)) void usb_shutdown_enter(uint32_t prerequisites)
{
    __disable_irq();
    volatile uint32_t *p=(volatile uint32_t *)&S;
    for(unsigned i=0;i<sizeof(S)/4U;i++)p[i]=0;
    S.magic=USB_SHUTDOWN_MAGIC;S.schema=USB_SHUTDOWN_SCHEMA;S.words=sizeof(S)/4U;
    S.prerequisites=prerequisites; S.state=USB_SHUTDOWN_BEGIN;
    S.ccr=SCB->CCR; S.control=__get_CONTROL(); S.ipsr=__get_IPSR();
    S.faultmask=__get_FAULTMASK(); S.fpccr=FPU->FPCCR;
    REQUIRE(prerequisites==USB_SHUTDOWN_REQUIRED,USB_SHUTDOWN_BAD_PREREQUISITES);
    REQUIRE(!S.ipsr && !S.faultmask && !(S.control&~0x0CU) &&
            !(S.ccr&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk)) &&
            !(S.fpccr&FPU_FPCCR_LSPACT_Msk),USB_SHUTDOWN_BAD_CONTEXT);
    RCC->APB4ENSR2=RCC_APB4ENSR2_BSECENS;
    RCC->AHB4ENSR=RCC_AHB4ENSR_PWRENS|GPIO_CLOCKS; __DSB();
    S.apb4enr2=RCC->APB4ENR2; S.ahb4enr=RCC->AHB4ENR; S.ahb4rstr=RCC->AHB4RSTR;
    REQUIRE((S.apb4enr2&RCC_APB4ENR2_BSECEN) &&
            (S.ahb4enr&(GPIO_CLOCKS|RCC_AHB4ENR_PWREN))==(GPIO_CLOCKS|RCC_AHB4ENR_PWREN) &&
            !(S.ahb4rstr&(GPIO_RESETS|RCC_AHB4RSTR_PWRRST)),USB_SHUTDOWN_BAD_CLOCKS);
    S.hold_verified=(uint32_t)release_hold();
    REQUIRE(S.hold_verified,USB_SHUTDOWN_HOLD_UNAVAILABLE);
    peripherals_off(); publish(USB_SHUTDOWN_PERIPHERALS_OFF);
    prepare_standby(); publish(USB_SHUTDOWN_ARMED);
#ifdef USB_SHUTDOWN_HOST_TEST
    usb_shutdown_test_hold_wfi();
#else
    /* HOLD is already LOW. Float only PD12 immediately before WFI; there is
     * deliberately no battery-HOLD assertion if WFI unexpectedly returns. */
    __asm volatile(
        ".global usb_shutdown_hold_release\nusb_shutdown_hold_release:\n"
        "movw r0, #0x0c00\nmovt r0, #0x5602\n"
        "ldr.w r1, [r0, #12]\nbic.w r1, r1, #0x3000000\nstr.w r1, [r0, #12]\n"
        "ldr.w r1, [r0]\nbic.w r1, r1, #0x3000000\nstr.w r1, [r0]\n"
        "dsb sy\nisb sy\n.global usb_shutdown_wfi\nusb_shutdown_wfi:\nwfi\n"
        ".global usb_shutdown_hold_end\nusb_shutdown_hold_end:\n"
        ::: "r0", "r1", "memory");
#endif
    refuse(USB_SHUTDOWN_UNEXPECTED_RETURN,USB_SHUTDOWN_RETURNED);
}
