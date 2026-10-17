
#include <stddef.h>
#include "stm32n657xx.h"
_Static_assert(BSEC_BASE_S == 0x56009000, "BSEC base");
_Static_assert(offsetof(BSEC_TypeDef, DBGCR) == 0xE8C, "DBGCR offset");
_Static_assert(offsetof(BSEC_TypeDef, AP_UNLOCK) == 0xE90, "AP_UNLOCK offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENSR2) == 0xA78, "BSEC clock set offset");
_Static_assert(offsetof(RCC_TypeDef, APB4ENR2) == 0x278, "BSEC clock readback offset");
_Static_assert(RCC_APB4ENSR2_BSECENS == 2, "BSEC clock bit");
_Static_assert(offsetof(RCC_TypeDef, RDCR) == 0x44C, "RDCR offset");
_Static_assert(SCB_BASE + offsetof(SCB_Type, DCCMVAC) == 0xE000EF68, "Cache clean address");
