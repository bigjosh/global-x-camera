
#include <stddef.h>
#include "stm32n657xx.h"
_Static_assert(BSEC_BASE_S == 0x56009000, "BSEC base");
_Static_assert(offsetof(BSEC_TypeDef, DBGCR) == 0xE8C, "DBGCR offset");
_Static_assert(offsetof(BSEC_TypeDef, AP_UNLOCK) == 0xE90, "AP_UNLOCK offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENSR2) == 0xA78, "BSEC clock set offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENR2) == 0x278, "BSEC clock readback offset");
_Static_assert(RCC_APB4ENSR2_BSECENS == 2, "BSEC clock bit");
_Static_assert(offsetof(RCC_TypeDef, RDCR) == 0x44C, "RDCR offset");
_Static_assert(DBGMCU_BASE_S == 0x54001000, "DBGMCU base");
_Static_assert(offsetof(DBGMCU_TypeDef, CR) == 4, "DBGMCU CR offset");
_Static_assert(DBGMCU_CR_DBG_SLEEP == 1, "Debug sleep bit");
_Static_assert(DBGMCU_CR_DBGCLKEN == 0x00100000, "Debug clock bit");
_Static_assert(offsetof(RCC_TypeDef, MISCENSR) == 0xA48, "DBG clock set offset");
_Static_assert(offsetof(RCC_TypeDef, MISCENR) == 0x248, "DBG clock read offset");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENSR) == 0xA88, "DBG sleep clock set offset");
_Static_assert(offsetof(RCC_TypeDef, MISCLPENR) == 0x288, "DBG sleep clock read offset");
_Static_assert(RCC_MISCENSR_DBGENS == 1, "DBG clock bit");
_Static_assert(RCC_MISCLPENSR_DBGLPENS == 1, "DBG sleep clock bit");
_Static_assert(SCB_BASE + offsetof(SCB_Type, DCCMVAC) == 0xE000EF68, "Cache clean address");
