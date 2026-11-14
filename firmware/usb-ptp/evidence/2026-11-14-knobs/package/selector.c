#include "stm32n6xx_hal.h"
#include "boot_read.h"
#include "boot_config.h"
#include "usb_hold.h"
extern int usb_vbus_sample(void);
extern volatile uint32_t vbus_proof[16];
/* knob.c: exposure and gain knobs, battery capture path only. */
extern uint32_t knob_apply(void);
extern volatile uint32_t knob_proof[32];
uint32_t SystemCoreClock=400000000U;
static uint32_t last,frac,ms;
uint32_t HAL_GetTick(void){uint32_t now=DWT->CYCCNT,delta=now-last;last=now;uint64_t t=(uint64_t)frac+delta;ms+=(uint32_t)(t/400000U);frac=(uint32_t)(t%400000U);return ms;}
void HAL_Delay(uint32_t n){uint32_t start=HAL_GetTick();while(HAL_GetTick()-start<n)__NOP();}
extern uint32_t __bss_start__,__bss_end__;
static void usb_select_mode(int present,volatile uint32_t *proof)
{
 /* Only legacy no-HOLD packages may compile this diagnostic override.
  * An uncertain VBUS result must never be turned into a capture decision. */
#ifdef USB_BOOT_FORCE_CAPTURE
 if(present>=0)return;
#endif
 if(!present)return;
 /* VBUS sampling restores its GPIOA snapshot. Release AFTER it returns,
  * before USB loading (including failure/ambiguous-voltage parks). The
  * battery path alone retains early HOLD and the original UART guard. */
 if(!usb_hold_off()){proof[1]=0xE005U;for(;;)__NOP();}
 proof[7]=DWT->CYCCNT;proof[8]=GPIOD->ODR;
 if(present<0){proof[1]=0xE002U;for(;;)__NOP();}
 if(!boot_read(USB_FLASH_OFFSET,(uint8_t *)0x34300000U,USB_BYTES,USB_CRC)){
  proof[1]=0xE003U;for(;;)__NOP();
 }
 proof[1]=4;proof[6]=DWT->CYCCNT;
 volatile uint32_t *q=(volatile uint32_t *)0x343F7F00U;
 for(unsigned i=0;i<8;i++)q[i]=0;
 q[0]=0x31505450U;
 __DSB();__ISB();((void (*)(void))USB_ENTRY)();for(;;)__NOP();
}
__attribute__((section(".text.entry"))) void usb_selector(void)
{
 for(uint32_t *p=&__bss_start__;p<&__bss_end__;p++)*p=0;
 last=DWT->CYCCNT;volatile uint32_t *proof=(volatile uint32_t *)0x343F9000U;
 proof[4]=(uint32_t)vbus_proof;
 int present=usb_vbus_sample();proof[5]=(uint32_t)present;
 /* A certain "no cable" is the only case that returns to capture. Read the
  * knobs then, after the VBUS sampler has released the converter. A knob
  * failure leaves the fixed exposure and never changes the mode decision. */
 if(present==0){proof[9]=(uint32_t)knob_proof;proof[10]=knob_apply();}
 usb_select_mode(present,proof);
}
