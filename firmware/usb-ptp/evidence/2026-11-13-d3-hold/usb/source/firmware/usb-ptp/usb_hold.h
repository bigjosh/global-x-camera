#ifndef USB_PTP_HOLD_H
#define USB_PTP_HOLD_H

/* Include after the target CMSIS register definitions (or the register model).
 * USB power must never maintain the battery latch. Preload LOW before selecting
 * the output so an inherited HIGH from provisional battery boot is removed.
 * This helper owns only PE9's fields; PA11 VBUS and other controls are untouched.
 * It is also used by the selector after VBUS sampling restores GPIOA state; HOLD lives on GPIOE.
 */
static inline int usb_hold_off(void)
{
    RCC->AHB4ENSR=RCC_AHB4ENR_GPIOEEN;
    __DSB();
    if(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIOEEN) ||
       (RCC->AHB4RSTR&RCC_AHB4RSTR_GPIOERST)) return 0;
    GPIOE->BSRR=1UL<<25; /* PE9 reset; never write its BSRR set bit. */
    __DSB();
    GPIOE->OTYPER&=~(1UL<<9);
    GPIOE->OSPEEDR&=~(3UL<<18);
    GPIOE->PUPDR&=~(3UL<<18);
    GPIOE->MODER=(GPIOE->MODER&~(3UL<<18))|(1UL<<18);
    __DSB();
    return (GPIOE->MODER&(3UL<<18))==(1UL<<18) &&
           !(GPIOE->PUPDR&(3UL<<18)) && !(GPIOE->OTYPER&(1UL<<9)) &&
           !(GPIOE->ODR&(1UL<<9)) && !(GPIOE->IDR&(1UL<<9));
}
#endif
