#include "stm32n6xx_hal.h"
#include "ptp.h"
#include "shutdown.h"
#include "transport/usb_ptp_transport.h"
#include "../sd-storage/sd_card.h"
#include <string.h>
#define P ((volatile uint32_t *)0x343F8000U)
#define Q ((volatile uint32_t *)0x343F7F00U)
static sd_card_t card;
static photo_store_t photos;
static uint32_t last_cycles,frac,milliseconds,usb_started;
#ifndef USB_TEST_READ_FAULT_LBA
#define USB_TEST_READ_FAULT_LBA 0U
#endif
#if USB_TEST_READ_FAULT_LBA
static uint32_t synthetic_read_pending;
#endif
uint32_t SystemCoreClock=400000000U;
extern void usb_park(void) __attribute__((noreturn));
extern int usb_vbus_sample(void);
extern volatile uint32_t vbus_proof[16];
uint32_t HAL_GetTick(void){uint32_t now=DWT->CYCCNT,delta=now-last_cycles;last_cycles=now;uint64_t total=(uint64_t)frac+delta;milliseconds+=(uint32_t)(total/400000U);frac=(uint32_t)(total%400000U);return milliseconds;}
void HAL_Delay(uint32_t ms){uint32_t start=HAL_GetTick();while(HAL_GetTick()-start<ms)__NOP();}
void sd_progress(void){HAL_GetTick();if(usb_started)usb_ptp_transport_poll();}
static int read_blocks(void *unused,uint32_t lba,void *p,uint32_t n){
 (void)unused;
#if USB_TEST_READ_FAULT_LBA
 if(ptp_stats[4]&&(ptp_stats[1]==0x1009U||ptp_stats[1]==0x100AU)&&
    lba<=USB_TEST_READ_FAULT_LBA&&USB_TEST_READ_FAULT_LBA-lba<n){
  memset(p,0xA5,n*512U);synthetic_read_pending=1;P[32]++;return 0;
 }
#endif
 return sd_read_blocks(&card,lba,p,n)==SD_OK;
}
static int write_blocks(void *unused,uint32_t lba,const void *p,uint32_t n){(void)unused;return sd_write_blocks(&card,lba,p,n)==SD_OK;}
static int sync_card(void *unused){(void)unused;return sd_sync(&card)==SD_OK;}
static int recover_card(void *unused){
 (void)unused;
#if USB_TEST_READ_FAULT_LBA
 if(synthetic_read_pending){synthetic_read_pending=0;return card.initialized&&card.media_idle&&sd_sync(&card)==SD_OK;}
#endif
 if(sd_sync(&card)!=SD_OK||sd_deinit(&card)!=SD_OK)return 0;
 memset(&card,0,sizeof card);return sd_init(&card,25000000U)==SD_OK;
}
static void snapshot(void){P[8]=card.error;P[9]=card.error_stage;P[10]=card.error_command;P[11]=card.error_sta;P[12]=card.cleanup_error;P[13]=card.initialized;P[14]=card.media_idle;P[15]=card.clock_hz;P[16]=(uint32_t)card.sector_count;P[17]=photos.scanned_slots;P[18]=photos.known_objects;P[19]=usb_ptp_debug.init_error;P[20]=usb_ptp_debug.init_stage;P[21]=SCB->CFSR;P[22]=SCB->HFSR;P[23]=HAL_GetTick();}
void usb_fault(void){P[2]=0xF000U|__get_IPSR();P[21]=SCB->CFSR;P[22]=SCB->HFSR;P[24]=SCB->BFAR;P[25]=SCB->MMFAR;__DSB();usb_park();}
void usb_main(void){
 RCC->AHB4ENSR=RCC_AHB4ENR_GPIODEN;__DSB();GPIOD->BSRR=1U<<7;GPIOD->OTYPER&=~(1U<<7);GPIOD->PUPDR&=~(3U<<14);GPIOD->MODER=(GPIOD->MODER&~(3U<<14))|(1U<<14);
 for(unsigned i=0;i<64;i++)P[i]=0;
 P[0]=0x31505450;P[1]=1;P[2]=1;P[3]=Q[1];
 CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;last_cycles=DWT->CYCCNT;
 P[4]=(uint32_t)ptp_stats;P[5]=(uint32_t)&usb_ptp_debug;P[6]=(uint32_t)ptp_log;P[7]=(uint32_t)&card;
 if(SCB->CCR&0x30000U||__get_CONTROL()||__get_IPSR()){P[2]=0xE001;usb_park();}
 P[30]=(uint32_t)vbus_proof;P[31]=(uint32_t)usb_vbus_sample();
 P[2]=2;
 if(sd_init(&card,25000000U)!=SD_OK){snapshot();P[2]=0xE002;usb_park();}
 sd_scr_t scr;if(sd_read_scr(&card,&scr)!=SD_OK){snapshot();P[2]=0xE003;usb_park();}
 photo_io_t io={0,read_blocks,write_blocks,sync_card,recover_card,ptp_service};
 if(photo_store_open(&photos,&io,card.sector_count,scr.erased_byte)){snapshot();P[2]=0xE004;usb_park();}
 P[2]=3;
 if(ptp_init(&photos,(void *)0x34000000U)){snapshot();P[2]=0xE005;usb_park();}
 usb_started=1;P[2]=4;
 uint32_t last_vbus=HAL_GetTick(),absent=0;P[33]=(uint32_t)&usb_shutdown_proof;
 while(Q[7]!=0x504F5453U){
  ptp_poll();snapshot();P[26]++;
  /* This app exclusively owns ADC12. Sample only between complete protocol
   * transactions, never in USB/SD callbacks or while a transfer is active. */
  if(!ptp_stats[4]&&HAL_GetTick()-last_vbus>=500U){
   int present=usb_vbus_sample();last_vbus=HAL_GetTick();P[31]=(uint32_t)present;
   absent=present==0?absent+1:0;
   if(absent>=2U)break;
  }
 }
 ptp_stop();usb_started=0;P[2]=5;
 if(sd_deinit(&card)||!card.media_idle||card.initialized||card.controller_owned||card.timer_owned||card.cleanup_error)P[2]=0xE006;
 else P[2]=8;
 snapshot();__DSB();
 if(absent>=2U&&P[2]==8)usb_shutdown_enter(USB_SHUTDOWN_REQUIRED);
 usb_park();
}
