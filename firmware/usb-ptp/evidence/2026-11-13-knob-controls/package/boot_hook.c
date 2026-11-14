#include "boot_read.h"
#include "boot_config.h"
void usb_selector_load(void)
{
 volatile uint32_t *p=(volatile uint32_t *)0x343F9000U;
 p[0]=0x31534255U;p[1]=1;p[2]=DWT->CYCCNT;
 uint32_t cache=SCB->CCR;
 /* boot_read independently refuses D-cache before touching NOR. */
 /* Normal stage1 enables I-cache after the early recovery guard. Newly
  * copied selector/USB code must be visible; restore I-cache only when the
  * selector returns to the unchanged capture path. */
 if(cache&SCB_CCR_IC_Msk)SCB_DisableICache();
 if(!boot_read(0x10000U,(uint8_t *)0x34200000U,SELECTOR_BYTES,SELECTOR_CRC)){
  p[1]=0xE001U;for(;;)__NOP();
 }
 __DSB();__ISB();
 p[1]=2;((void (*)(void))SELECTOR_ENTRY)();
 if(cache&SCB_CCR_IC_Msk)SCB_EnableICache();
 p[1]=3;p[3]=DWT->CYCCNT;
}
