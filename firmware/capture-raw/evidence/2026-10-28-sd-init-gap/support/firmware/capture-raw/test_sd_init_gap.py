"""Offline execution of the real bounded gap; no controller or instrument use."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
PREFIX = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#define MAGIC_LATE
#define RAW_OP_CAPTURE 1U
#define RP_FRAME_DONE 0
#define RP_CAMERA_STOP 1
#define DWT_CTRL_CYCCNTENA_Msk 1U
static struct {uint32_t CTRL,CYCCNT;} dwt;
static uint32_t stall;
#define DWT (&dwt)
static uint32_t operation=1,storage_call_depth,ipsr,SystemCoreClock=400000000;
static struct {uint32_t initialized,controller_owned,timer_owned,command_count;
 uint64_t read_sectors,written_sectors;} raw_card;
static volatile uint32_t raw_sd_init_gap_proof[16],P[2];
static uint32_t polls,valid,stopped,fault,mode,markers,marker_fail;
static uint32_t __get_IPSR(void){return ipsr;}
static void __DSB(void){}
static uint32_t raw_capture_frame_validated(void){return valid;}
static uint32_t raw_capture_sensor_stopped(void){return stopped;}
static uint32_t raw_capture_fault(void){return fault;}
static void raw_capture_poll(void){
 polls++;if(!stall)dwt.CYCCNT+=1000000U;
 if(polls==2){valid=1;P[0]=dwt.CYCCNT;}
 if(polls==4&&mode!=2){stopped=1;P[1]=dwt.CYCCNT;}
 if(mode==1&&polls==3)fault=1;
 if(mode==3&&polls==3)raw_card.command_count=1;
}
static void __NOP(void){
 if(!stall)dwt.CYCCNT+=100000U;
 if(mode==4)raw_card.command_count=1;
 if(mode==5)dwt.CYCCNT+=100000000U;
}
static int phase_gpio_emit(uint32_t event){
 if(!valid||!stopped||raw_card.command_count)abort();
 if(event!=11U+markers)abort();markers++;
 return event!=marker_fail;
}
'''
SUFFIX = r'''
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d:%s\n",__LINE__,#x);return 1;}}while(0)
int main(int argc,char **argv){
 if(argc!=2)return 2;uint32_t test=(uint32_t)strtoul(argv[1],0,0),expected=0;
 dwt.CTRL=1;dwt.CYCCNT=1234;
 if(test==1)dwt.CYCCNT=0xFFF00000U;
 else if(test==2){operation=2;expected=1;}
 else if(test==3){raw_card.command_count=1;expected=1;}
 else if(test==4){SystemCoreClock=50000000U;expected=1;}
 else if(test==5){dwt.CTRL=0;expected=1;}
 else if(test==6){mode=1;expected=2;}
 else if(test==7){mode=2;expected=3;}
 else if(test==8){mode=3;expected=4;}
 else if(test==9){mode=4;expected=4;}
 else if(test==10){valid=stopped=stall=1;expected=5;}
 else if(test==11){mode=5;expected=5;}
 else if(test==12){marker_fail=11;expected=6;}
 else if(test==13){marker_fail=12;expected=6;}
 else if(test==14){ipsr=1;expected=1;}
 else if(test==15){storage_call_depth=1;expected=1;}
 else if(test==16){raw_card.controller_owned=1;expected=1;}
 else if(test==17){valid=stopped=fault=1;expected=2;}
 else if(test!=0)return 3;
 int result=magic_sd_init_gap();
 volatile uint32_t *v=raw_sd_init_gap_proof;
 CHECK(result==(int)expected&&v[3]==expected);
 CHECK(v[0]==0x31504147U&&v[1]==1&&v[9]==80000000U&&v[15]==0);
 CHECK(v[2]==(expected?15U:3U));
 if(!expected){
  CHECK(polls==4&&markers==2&&v[12]==1&&v[13]==1);
  CHECK(v[5]==P[0]&&v[6]==P[1]);
  CHECK((uint32_t)(v[7]-v[6])<1000000U);
  CHECK((uint32_t)(v[8]-v[7])>=80000000U&&(uint32_t)(v[8]-v[7])<100000000U);
  CHECK(!v[10]&&!v[11]&&v[14]==400000000U);
 }
 if(expected==1)CHECK(polls==0&&markers==0);
 if(expected==2||expected==3)CHECK(markers==0);
 return 0;
}
'''


class SdInitGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            raise RuntimeError('host C compiler required')
        cls.temp = tempfile.TemporaryDirectory()
        source = Path(cls.temp.name) / 'gap.c'
        cls.binary = source.with_suffix('.exe')
        source.write_text(PREFIX + (HERE / 'sd_init_gap.inc').read_text() + SUFFIX)
        result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                 str(source), '-o', str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_gap_success_wrap_and_all_failure_gates(self):
        for case in range(18):
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), str(case)], capture_output=True,
                                        text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_late_only_no_new_storage_or_gpio_access(self):
        source = (HERE / 'sd_init_gap.inc').read_text()
        self.assertEqual(re.findall(r'^(.*static int magic_sd_init_gap)', source, re.M),
                         ['MAGIC_LATE static int magic_sd_init_gap'])
        self.assertNotRegex(source, r'\bsd_(?:init|read|write|reset|erase)\w*\(')
        self.assertNotIn('GPIO', source)
        execute = (HERE / 'magic_runtime.inc').read_text()
        self.assertLess(execute.index('if(magic_sd_init_gap())'), execute.index('if(!raw_card.initialized) init_card();'))


if __name__ == '__main__':
    unittest.main()
