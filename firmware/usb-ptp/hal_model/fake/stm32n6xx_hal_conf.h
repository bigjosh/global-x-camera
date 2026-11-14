#ifndef SIM_HAL_CONF_H
#define SIM_HAL_CONF_H
#define HAL_MODULE_ENABLED
#define HAL_ADC_MODULE_ENABLED
#define HSI_VALUE 64000000UL
#define HSE_VALUE 48000000UL
#define MSI_VALUE 4000000UL
#define LSI_VALUE 32000UL
#define LSE_VALUE 32768UL
#define EXTERNAL_I2S_CLOCK_VALUE 12288000UL
#define VDD_VALUE 3300UL
#define TICK_INT_PRIORITY 15UL
#define USE_HAL_ADC_REGISTER_CALLBACKS 0U
#define HAL_DMA_MODULE_ENABLED
#include "stm32n6xx_hal_dma.h"
#include "stm32n6xx_hal_adc.h"
#ifdef ADC_MODEL_STRICT
/* HAL's direct ISR assignment means write-one-to-clear on hardware, not RAM.
 * Override that access macro only; compile the actual ST driver unchanged. */
#undef __HAL_ADC_CLEAR_FLAG
#define __HAL_ADC_CLEAR_FLAG(HANDLE, FLAG) sim_write(&(HANDLE)->Instance->ISR, (FLAG))
#endif
#define assert_param(expr) ((void)0U)
#endif
