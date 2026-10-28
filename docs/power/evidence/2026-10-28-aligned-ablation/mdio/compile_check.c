#include "stm32n6xx.h"
#define RAW_POWER_PROBE 4
#define RAW_FLASH 0
#define RAW_STANDBY 0
#include "../../../../firmware/capture-raw/power_phy.inc"
int mdio_offline_compile_check(unsigned mode)
{ int e=power_phy_begin(mode); int cleanup=power_phy_restore(); return e?e:cleanup; }
