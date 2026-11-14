/* Shared fixed-RAM and on-media controls ABI. All fields are little endian. */
#ifndef CAPTURE_CONTROLS_H
#define CAPTURE_CONTROLS_H
#include <stdint.h>
#include <stddef.h>
#define CAPTURE_CONTROLS_ADDRESS 0x343F9400U
#define CAPTURE_CONTROLS_HELPER 0x34200101U
#define CAPTURE_CONTROLS_MANUAL_ADDRESS 0x343F9440U
#define CAPTURE_CONTROLS_MAGIC 0x314E4B43U
#define CAPTURE_CONTROLS_SCHEMA 1U
#define CC_ADC_READY 2U
#define CC_SENSOR_CONFIGURED 3U
#define CC_APPLIED_VERIFIED 4U
#define CC_FAILED 15U
#define CC_F_ADC_VALID 1U
#define CC_F_EXCITATION_OFF 2U
#define CC_F_SENSOR_CONFIGURED 4U
#define CC_F_APPLIED_VALID 8U
#define CC_F_ASA_PROVISIONAL 16U
#define CC_REQUIRED_FLAGS (CC_F_ADC_VALID|CC_F_EXCITATION_OFF|CC_F_ASA_PROVISIONAL)
typedef struct {
 uint32_t magic,schema,bytes,state,error,flags;
 uint32_t adc_low,exposure_high,asa_high,exposure_raw,asa_raw;
 uint32_t exposure_q16,asa_q16,requested_us,line_length,frame_length;
 uint8_t manual[12];
 uint32_t asa,vt_hz,applied_coarse,applied_gain,applied_digital,margin;
 uint32_t adc_begin,adc_end,sensor_begin,sensor_end,reserved0,reserved1,crc32;
} capture_controls_t;
_Static_assert(sizeof(capture_controls_t)==128,"Controls ABI size");
_Static_assert(offsetof(capture_controls_t,manual)==64,"Controls manual offset");
_Static_assert(offsetof(capture_controls_t,crc32)==124,"Controls CRC offset");
#define CAPTURE_CONTROLS ((volatile capture_controls_t *)CAPTURE_CONTROLS_ADDRESS)
static inline uint32_t capture_controls_crc(const volatile capture_controls_t *p) {
 const volatile uint8_t *b=(const volatile uint8_t *)p;uint32_t c=~0U;
 for(unsigned i=0;i<124;i++){c^=b[i];for(unsigned j=0;j<8;j++)c=(c>>1)^(0xEDB88320U&(0U-(c&1U)));}
 return c^~0U;
}
static inline int capture_controls_valid(const volatile capture_controls_t *p) {
 return p->magic==CAPTURE_CONTROLS_MAGIC && p->schema==1U && p->bytes==128U &&
  !p->error && (p->flags&CC_REQUIRED_FLAGS)==CC_REQUIRED_FLAGS &&
  p->crc32==capture_controls_crc(p);
}
uint32_t capture_controls_exposure(uint32_t position);
int capture_controls_map(capture_controls_t *p);
void capture_controls_sample(void);
int capture_controls_sensor_apply(uint16_t reg,uint32_t value,unsigned bytes);
#endif
