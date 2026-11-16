#include "capture_controls.h"
/* 64 log-spaced intervals, linear interpolation; <0.17% curve error including integer rounding (exhaustive host check).
 * The label itself is logarithmic in seconds, including its conventional marks. */
static const uint32_t exposure_lut[65]={
1000,1078,1163,1254,1352,1458,1572,1696,1829,1972,2126,2293,2473,2666,2875,3101,3344,3606,3888,4193,4522,4876,5258,5670,6114,6593,7110,7667,8268,8916,9614,10368,11180,12056,13001,14020,15119,16303,17581,18959,20444,22046,23774,25637,27646,29812,32148,34667,37384,40313,43472,46879,50552,54513,58785,63392,68359,73716,79492,85721,92439,99682,107493,115917,125000};
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
 uint32_t q=p->asa_q16*6U;unsigned sector=q<65535U?0:(q<196605U?1:(q<327675U?2:3));
 static const uint8_t gains[4]={0,16,24,28};
 p->asa=100U<<sector;p->vt_hz=160800000U;
 p->manual[0]=2;p->manual[1]=gains[sector];p->manual[2]=(uint8_t)coarse;p->manual[3]=(uint8_t)(coarse>>8);
 for(unsigned i=4;i<12;i+=2){p->manual[i]=0;p->manual[i+1]=1;}
 return 0;
}
