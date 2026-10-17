/* Compile-time only: not linked into the measured image. */
#include <stddef.h>
#include "stm32n657xx.h"
#include "registers.h"

#define CHECK_OFFSET(type, field, expected) \
    _Static_assert(offsetof(type, field) == (expected), #type "." #field " changed")

_Static_assert(RCC_BASE_S == BT_RCC_BASE, "RCC secure address changed");
_Static_assert(GPIOD_BASE_S == BT_GPIOD_BASE, "GPIOD secure address changed");
_Static_assert(GPIOE_BASE_S == BT_GPIOE_BASE, "GPIOE secure address changed");
_Static_assert((RCC_AHB4ENSR_GPIODENS | RCC_AHB4ENSR_GPIOEENS) == BT_GPIOD_GPIOE_ENABLE,
               "GPIO clock-enable bits changed");
CHECK_OFFSET(RCC_TypeDef, AHB4ENR, BT_RCC_AHB4ENR);
CHECK_OFFSET(RCC_TypeDef, AHB4ENSR, BT_RCC_AHB4ENSR);
CHECK_OFFSET(GPIO_TypeDef, MODER, BT_GPIO_MODER);
CHECK_OFFSET(GPIO_TypeDef, OTYPER, BT_GPIO_OTYPER);
CHECK_OFFSET(GPIO_TypeDef, OSPEEDR, BT_GPIO_OSPEEDR);
CHECK_OFFSET(GPIO_TypeDef, PUPDR, BT_GPIO_PUPDR);
CHECK_OFFSET(GPIO_TypeDef, BSRR, BT_GPIO_BSRR);
_Static_assert(SCB_BASE + offsetof(SCB_Type, VTOR) == BT_SCB_VTOR, "VTOR changed");
_Static_assert(SCB_BASE + offsetof(SCB_Type, SCR) == BT_SCB_SCR, "SCR changed");
_Static_assert(SCB_SCR_SLEEPDEEP_Msk == BT_SCB_SLEEPDEEP, "SLEEPDEEP changed");
_Static_assert(GPIO_MODER_MODE0 == 3 && GPIO_MODER_MODE0_0 == 1,
               "Pin zero output-mode encoding changed");
