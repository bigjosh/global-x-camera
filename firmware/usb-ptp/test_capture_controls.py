"""Native tests of the real controls mapping/helper; no instrument imports."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest
HERE=Path(__file__).resolve().parent
class ControlTests(unittest.TestCase):
 def test_mapping_and_sensor_failure_paths(self):
  cc=shutil.which('clang') or shutil.which('gcc')
  if not cc:self.skipTest('Native compiler unavailable')
  with tempfile.TemporaryDirectory(prefix='capture-controls-') as t:
   root=Path(t);source=root/'test.c';exe=root/'test.exe'
   source.write_text(HARNESS,encoding='utf-8')
   r=subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-DCAPTURE_CONTROLS_HOST=1','-I'+str(HERE),str(source),str(HERE/'capture_controls_map.c'),str(HERE/'capture_controls_sensor.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(exe)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
HARNESS=r'''
#include "capture_controls.h"
#include <assert.h>
#include <string.h>
volatile capture_controls_t cc_test_record;
static unsigned reads,writes,fail_read,fail_write;static uint32_t margin=68,clock_value;
uint32_t cc_test_cycles(void){return ++clock_value;}
int cc_test_read(uint16_t reg,uint32_t n,uint32_t *value){reads++;assert((reg==0x0946&&n==2)||(reg==0x097E&&n==1)||(reg==0x0960&&n==1));*value=reg==0x0946?margin:(reg==0x0960?28:0);return reads==fail_read;}
int cc_test_write(uint16_t reg,uint32_t value,uint32_t n){
 writes++;assert(n==(writes==1?1:2));assert(reg==(writes==1?0x0960:(writes==2?0x0300:0x0458)));
 assert(value==(writes==1?28:(writes==2?1280:cc_test_record.frame_length)));return writes==fail_write;
}
static capture_controls_t fixture(unsigned exposure,unsigned asa){
 capture_controls_t r={0};r.magic=CAPTURE_CONTROLS_MAGIC;r.schema=1;r.bytes=128;r.state=CC_ADC_READY;r.flags=CC_REQUIRED_FLAGS;
 r.adc_low=2;r.exposure_high=r.asa_high=3840;r.exposure_raw=exposure;r.asa_raw=asa;
 assert(!capture_controls_map(&r));r.crc32=capture_controls_crc(&r);return r;
}
static void reset(unsigned e,unsigned a){cc_test_record=fixture(e,a);reads=writes=fail_read=fail_write=0;margin=68;}
int main(void){
 assert(sizeof(capture_controls_t)==128&&offsetof(capture_controls_t,manual)==64);
 uint32_t last=0;
 for(uint32_t x=0;x<=65535;x++){uint32_t us=capture_controls_exposure(x);assert(us>=last&&us>=1000&&us<=500000);last=us;}
 assert(capture_controls_exposure(0)==1000&&capture_controls_exposure(65535)==500000);
 capture_controls_t r=fixture(3840,0);assert(r.requested_us==1000&&r.asa==100&&r.manual[1]==0);
 r=fixture(0,3840);assert(r.requested_us==500000&&r.asa==800&&r.manual[1]==28);
 assert(r.line_length==1280&&r.frame_length==64813&&(r.manual[2]|r.manual[3]<<8)==62813);
 r=fixture(2177,1781);assert(r.exposure_q16!=32768&&r.asa_q16!=32768);
 const unsigned inputs[4]={2,1281,2561,3840},codes[4]={0,16,24,28};
 for(unsigned i=0;i<4;i++){r=fixture(2000,inputs[i]);assert(r.manual[1]==codes[i]&&r.asa==(100U<<i));}
 for(unsigned raw=0;raw<=4095;raw++){
  r=fixture(raw,raw);unsigned coarse=r.manual[2]|r.manual[3]<<8;
  assert(r.line_length==1280&&coarse>=21&&r.frame_length>=coarse+2000&&r.frame_length<=65535);
  assert((uint64_t)coarse*1280*1000000>=(uint64_t)r.requested_us*160800000);
 }
 r=fixture(2000,2000);r.exposure_high=2999;assert(capture_controls_map(&r));
 r=fixture(2000,2000);r.adc_low=129;assert(capture_controls_map(&r));
 reset(3840,0);assert(!capture_controls_sensor_apply(0x0458,4336,2));
 assert(reads==3&&writes==3&&cc_test_record.state==CC_SENSOR_CONFIGURED&&capture_controls_valid(&cc_test_record));
 reset(0,3840);assert(!capture_controls_sensor_apply(0x0458,4336,2));assert(cc_test_record.margin==68);
 reset(0,3840);margin=1994;assert(capture_controls_sensor_apply(0x0458,4336,2)==-106&&writes==0);
 reset(0,3840);fail_read=1;assert(capture_controls_sensor_apply(0x0458,4336,2)==-105&&writes==0);
 for(unsigned i=1;i<=3;i++){reset(0,3840);fail_write=i;const int expected[3]={-110,-107,-108};assert(capture_controls_sensor_apply(0x0458,4336,2)==expected[i-1]);assert(cc_test_record.state==CC_FAILED&&cc_test_record.crc32==capture_controls_crc(&cc_test_record));}
 reset(0,3840);cc_test_record.crc32^=1;assert(capture_controls_sensor_apply(0x0458,4336,2)==-101&&reads==0&&writes==0);
 reset(0,3840);cc_test_record.manual[1]=3;cc_test_record.crc32=capture_controls_crc(&cc_test_record);assert(capture_controls_sensor_apply(0x0458,4336,2)==-104&&reads==0);
 reset(0,3840);assert(capture_controls_sensor_apply(0x0459,4336,2)==-100&&reads==0&&writes==0);
 reset(0,3840);cc_test_record.flags&=~CC_F_EXCITATION_OFF;cc_test_record.crc32=capture_controls_crc(&cc_test_record);assert(capture_controls_sensor_apply(0x0458,4336,2)==-101&&reads==0);
 return 0;
}
'''
if __name__=='__main__':unittest.main()
