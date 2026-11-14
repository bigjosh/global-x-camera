#include <stdio.h>
#include <string.h>
#include "capture_controls.h"
int main(int argc,char **argv) {
 if(argc!=2)return 1;
 FILE *f=fopen(argv[1],"wb");if(!f)return 2;
 for(unsigned p=0;p<65536;p++){uint32_t v=capture_controls_exposure(p);if(fwrite(&v,4,1,f)!=1)return 3;}
 fclose(f);unsigned cases=0;
 for(unsigned raw=0;raw<=3840;raw++)for(unsigned gain=0;gain<=3840;gain+=160){
  capture_controls_t r={0};r.adc_low=0;r.exposure_high=3840;r.asa_high=3840;r.exposure_raw=raw;r.asa_raw=gain;
  if(capture_controls_map(&r))return 4;
  unsigned coarse=r.manual[2]|(r.manual[3]<<8);
  unsigned expected=(unsigned)(((uint64_t)r.requested_us*160800000ULL+1279999999ULL)/1280000000ULL);
  if(r.line_length!=1280||coarse!=expected||coarse<21||r.frame_length>65535||r.frame_length<coarse+2000)return 5;
  unsigned ag=r.manual[1];if(!((ag==0&&r.asa==100)||(ag==16&&r.asa==200)||(ag==24&&r.asa==400)||(ag==28&&r.asa==800)))return 6;
  for(unsigned i=4;i<12;i+=2)if(r.manual[i]!=0||r.manual[i+1]!=1)return 7;
  cases++;
 }
 printf("%u\n",cases);return 0;
}