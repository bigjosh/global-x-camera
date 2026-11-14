#ifndef USB_PTP_HOLD_H
#define USB_PTP_HOLD_H

/* Include after the target CMSIS register definitions (or the register model).
 * USB power must never maintain the battery latch. Preload LOW before selecting
 * the output so an inherited HIGH from provisional battery boot is removed.
 * This helper owns only PD12's fields; PA11 VBUS and other controls are untouched.
 * It is also used by the selector after VBUS sampling restores GPIOA state; HOLD lives on GPIOD.
 */
static inline int usb_hold_off(void)
{
    RCC->AHB4ENSR=RCC_AHB4ENR_GPIODEN;
    __DSB();
    if(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIODEN) ||
       (RCC->AHB4RSTR&RCC_AHB4RSTR_GPIODRST)) return 0;
    GPIOD->BSRR=1UL<<28; /* PD12 reset; never write its BSRR set bit. */
    __DSB();
    GPIOD->OTYPER&=~(1UL<<12);
    GPIOD->OSPEEDR&=~(3UL<<24);
    GPIOD->PUPDR&=~(3UL<<24);
    GPIOD->MODER=(GPIOD->MODER&~(3UL<<24))|(1UL<<24);
    __DSB();
    return (GPIOD->MODER&(3UL<<24))==(1UL<<24) &&
           !(GPIOD->PUPDR&(3UL<<24)) && !(GPIOD->OTYPER&(1UL<<12)) &&
           !(GPIOD->ODR&(1UL<<12)) && !(GPIOD->IDR&(1UL<<12));
}
#endif
