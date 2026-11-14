/* Runs from the checked selector image after sensor BOOT, before START.
 * Original stage1 calls this at its fixed FRAME_LENGTH write callsite. */
#include "capture_controls.h"
#ifndef CAPTURE_CONTROLS_HOST
#include "stm32n6xx_hal.h"
#define CC_RECORD CAPTURE_CONTROLS
#define CC_CYCLES() (DWT->CYCCNT)
#define CC_BARRIER() __DSB()
#define CC_WRITE ((int (*)(uint16_t,uint32_t,uint32_t))0x341806D9U)
#define CC_READ ((int (*)(uint16_t,uint32_t,uint32_t *))0x34180619U)
#else
extern volatile capture_controls_t cc_test_record;
extern uint32_t cc_test_cycles(void);
extern int cc_test_write(uint16_t,uint32_t,uint32_t);
extern int cc_test_read(uint16_t,uint32_t,uint32_t *);
#define CC_RECORD (&cc_test_record)
#define CC_CYCLES() cc_test_cycles()
#define CC_BARRIER() ((void)0)
#define CC_WRITE cc_test_write
#define CC_READ cc_test_read
#endif
static int finish(volatile capture_controls_t *p,uint32_t error) {
 p->error=error;p->state=error?CC_FAILED:CC_SENSOR_CONFIGURED;
 if(!error)p->flags|=CC_F_SENSOR_CONFIGURED;
 p->sensor_end=CC_CYCLES();p->crc32=capture_controls_crc(p);CC_BARRIER();
 return error?-(int)error:0;
}
int capture_controls_sensor_apply(uint16_t reg,uint32_t value,unsigned bytes) {
 volatile capture_controls_t *p=CC_RECORD;
 if(reg!=0x0458U || value!=4336U || bytes!=2U)return -100;
 if(!capture_controls_valid(p) || p->state!=CC_ADC_READY)return finish(p,101);
 capture_controls_t expected;uint32_t *to=(uint32_t *)&expected;
 const volatile uint32_t *from=(const volatile uint32_t *)p;
 for(unsigned i=0;i<32;i++)to[i]=from[i];
 if(capture_controls_map(&expected))return finish(p,102);
 if(expected.exposure_q16!=p->exposure_q16 || expected.asa_q16!=p->asa_q16 ||
    expected.requested_us!=p->requested_us || expected.line_length!=p->line_length ||
    expected.frame_length!=p->frame_length || expected.asa!=p->asa || expected.vt_hz!=p->vt_hz)
  return finish(p,103);
 for(unsigned i=0;i<12;i++)if(expected.manual[i]!=p->manual[i])return finish(p,104);
 p->sensor_begin=CC_CYCLES();uint32_t margin=0;
 if(CC_READ(0x0946U,2U,&margin))return finish(p,105);
 p->margin=margin;
 uint32_t coarse=p->manual[2]|((uint32_t)p->manual[3]<<8);
 if(margin>1993U || p->frame_length<coarse+margin+7U)return finish(p,106);
 uint32_t min_gain=0,max_gain=0;
 /* The documented default maximum24 is only4x. Explicitly admit8x (code28)
  * inSW_STANDBY, and verify the limit before the manual block is applied. */
 if(CC_READ(0x097EU,1U,&min_gain) || min_gain>28U || p->manual[1]<min_gain)return finish(p,109);
 if(CC_WRITE(0x0960U,28U,1U))return finish(p,110);
 if(CC_READ(0x0960U,1U,&max_gain) || max_gain!=28U)return finish(p,111);
 /* Constant1280 preserves READ_OFFSET18 and keeps500ms frame within16bits. */
 if(CC_WRITE(0x0300U,p->line_length,2U))return finish(p,107);
 if(CC_WRITE(0x0458U,p->frame_length,2U))return finish(p,108);
 return finish(p,0);
}
