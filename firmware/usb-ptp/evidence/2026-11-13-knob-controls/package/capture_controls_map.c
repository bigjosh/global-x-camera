#include "capture_controls.h"
/* 64 log-spaced intervals, linear interpolation; <0.17% curve error including integer rounding (exhaustive host check).
 * The label itself is logarithmic in seconds, including its conventional marks. */
static const uint32_t exposure_lut[65]={
1000,1102,1214,1338,1475,1625,1791,1973,2175,2396,2641,2910,3207,3534,3894,4291,4729,5211,5742,6328,6973,7684,8468,9331,10283,11331,12487,13760,15163,16710,18414,20291,22361,24641,27154,29923,32974,36336,40042,44125,48625,53583,59047,65068,71704,79016,87073,95952,105737,116520,128402,141495,155924,171824,189346,208654,229932,253379,279217,307690,339066,373642,411744,453731,500000};
uint32_t capture_controls_exposure(uint32_t position) {
 if(position>=65535U)return 500000U;
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
