#include "capture_controls.h"
/* 64 log-spaced intervals, linear interpolation; <0.5% curve error including integer rounding (worst at the short end, where entries are small integers).
 * The 167 us floor (21 lines) is also enforced by the capture receiver (capture-raw/knob_capture.inc, error 0x7D) and by
 * the USB metadata check (storage/photo_store.c); all three must change together.
 * The label itself is logarithmic in seconds, including its conventional marks. */
static const uint32_t exposure_lut[65]={
167,185,205,228,253,280,311,344,382,424,470,521,578,641,710,788,874,969,1074,1191,1321,1465,1625,1801,1998,2215,2457,2724,3021,3350,3715,4120,4569,5067,5619,6231,6910,7662,8497,9423,10449,11588,12850,14250,15802,17524,19433,21550,23898,26502,29389,32590,36141,40078,44444,49286,54656,60610,67213,74536,82656,91660,101646,112720,125000};
uint32_t capture_controls_exposure(uint32_t position) {
 if(position>=65535U)return 125000U;
 uint32_t scaled=position*64U,index=scaled/65535U,fraction=scaled%65535U;
 return exposure_lut[index]+(uint32_t)(((uint64_t)(exposure_lut[index+1]-exposure_lut[index])*fraction+32767U)/65535U);
}
static uint32_t normalize(uint32_t raw,uint32_t low,uint32_t high) {
 if(raw<=low)return 0;
 if(raw>=high)return 65535U;
 return ((raw-low)*65535U+(high-low)/2U)/(high-low);
}
int capture_controls_map(capture_controls_t *p) {
 if(p->adc_low>128U || p->exposure_high>4095U || p->asa_high>4095U ||
    p->exposure_high<p->adc_low+3000U || p->asa_high<p->adc_low+3000U ||
    p->exposure_raw>4095U || p->asa_raw>4095U)return -1;
 p->exposure_q16=65535U-normalize(p->exposure_raw,p->adc_low,p->exposure_high);
 p->asa_q16=normalize(p->asa_raw,p->adc_low,p->asa_high);
 p->requested_us=capture_controls_exposure(p->exposure_q16);
 p->line_length=1280U; /* 500 ms plus conservative2000-line reserve fits16 bits. */
 uint32_t coarse=(uint32_t)(((uint64_t)p->requested_us*160800000U+
   (uint64_t)p->line_length*1000000U-1U)/((uint64_t)p->line_length*1000000U));
 p->frame_length=coarse+2000U;if(p->frame_length<4336U)p->frame_length=4336U;
 if(coarse<21U || p->frame_length>65535U)return -2;
 unsigned sector=0; /* ASA fixed at 100: the prototype's ASA knob only ever read its end values (NOTES 2026-11-16), and daylight needs the headroom (NOTES 2026-11-20, 2026-11-21); asa_q16 is still recorded. */
 static const uint8_t gains[4]={0,16,24,28};
 p->asa=100U<<sector;p->vt_hz=160800000U;
 p->manual[0]=2;p->manual[1]=gains[sector];p->manual[2]=(uint8_t)coarse;p->manual[3]=(uint8_t)(coarse>>8);
 for(unsigned i=4;i<12;i+=2){p->manual[i]=0;p->manual[i+1]=1;}
 return 0;
}
