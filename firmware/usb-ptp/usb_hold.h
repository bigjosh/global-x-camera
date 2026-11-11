#ifndef USB_PTP_HOLD_H
#define USB_PTP_HOLD_H

/* Include after the target CMSIS register definitions (or the register model).
 * USB power must never maintain the battery latch. Preload LOW before selecting
 * the output so an inherited HIGH from provisional battery boot is removed.
 * This helper owns only PA2's fields; PA11 VBUS and other controls are untouched.
 * It is also used by the selector after VBUS sampling restores GPIOA state.
 */
static inline int usb_hold_off(void)
{
    RCC->AHB4ENSR=RCC_AHB4ENR_GPIOAEN;
    __DSB();
    if(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIOAEN) ||
       (RCC->AHB4RSTR&RCC_AHB4RSTR_GPIOARST)) return 0;
    GPIOA->BSRR=1UL<<18; /* PA2 reset; never write its BSRR set bit. */
    __DSB();
    GPIOA->OTYPER&=~(1UL<<2);
    GPIOA->OSPEEDR&=~(3UL<<4);
    GPIOA->PUPDR&=~(3UL<<4);
    GPIOA->MODER=(GPIOA->MODER&~(3UL<<4))|(1UL<<4);
    __DSB();
    return (GPIOA->MODER&(3UL<<4))==(1UL<<4) &&
           !(GPIOA->PUPDR&(3UL<<4)) && !(GPIOA->OTYPER&(1UL<<2)) &&
           !(GPIOA->ODR&(1UL<<2)) && !(GPIOA->IDR&(1UL<<2));
}
#endif
