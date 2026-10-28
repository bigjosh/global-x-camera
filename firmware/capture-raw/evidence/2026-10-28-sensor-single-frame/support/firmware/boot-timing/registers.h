/* Addresses and fields checked against ST's pinned STM32N657 CMSIS header.
 * No vendor implementation is copied; address_check.c verifies these facts.
 */
#ifndef BOOT_TIMING_REGISTERS_H
#define BOOT_TIMING_REGISTERS_H

#define BT_RCC_BASE           0x56028000
#define BT_RCC_AHB4ENR        0x025C
#define BT_RCC_AHB4ENSR       0x0A5C
#define BT_GPIOD_GPIOE_ENABLE 0x00000018
#define BT_GPIOD_BASE         0x56020C00
#define BT_GPIOE_BASE         0x56021000
#define BT_GPIO_MODER         0x00
#define BT_GPIO_OTYPER        0x04
#define BT_GPIO_OSPEEDR       0x08
#define BT_GPIO_PUPDR         0x0C
#define BT_GPIO_BSRR          0x18
#define BT_SCB_VTOR           0xE000ED08
#define BT_SCB_SCR            0xE000ED10
#define BT_SCB_SLEEPDEEP      0x04

#endif
