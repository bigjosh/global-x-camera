/* Same operations as pinned HAL CSI/DCMIPP clock branches. */
#include "stm32n6xx_hal.h"
void baseline_clocks(void) {}
HAL_StatusTypeDef MX_DCMIPP_ClockConfig(DCMIPP_HandleTypeDef *hdcmipp)
{
  (void)hdcmipp;
  MODIFY_REG(RCC->IC18CFGR,RCC_IC18CFGR_IC18SEL|RCC_IC18CFGR_IC18INT,
             RCC_ICCLKSOURCE_PLL1|(59U<<RCC_IC18CFGR_IC18INT_Pos));
  LL_RCC_IC18_Enable();
  MODIFY_REG(RCC->IC17CFGR,RCC_IC17CFGR_IC17SEL|RCC_IC17CFGR_IC17INT,
             RCC_ICCLKSOURCE_PLL1|(3U<<RCC_IC17CFGR_IC17INT_Pos));
  LL_RCC_IC17_Enable();
  __HAL_RCC_DCMIPP_CONFIG(RCC_DCMIPPCLKSOURCE_IC17);
  return HAL_OK;
}
