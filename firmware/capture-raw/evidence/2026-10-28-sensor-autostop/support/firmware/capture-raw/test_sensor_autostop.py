"""Execute the real autonomous-stop observer offline; never opens hardware."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
PREFIX=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
static struct {uint32_t CYCCNT;} dwt;
#define DWT (&dwt)
static struct {uint32_t IDR;} gpio;
#define GPIOA (&gpio)
static struct {struct {uint32_t is_streaming;} ctx;} sensor;
static volatile uint32_t AST[40],CPROF[2];
#define CP_SENSOR_STOP_DONE 0
#define CP_FLAGS 1
#define CP_F_SAFE_STOP 1
static uint32_t capture_async_error,capture_stop_pending=1,capture_sensor_stopped;
static uint32_t capture_stop_started,capture_stop_poll,fast_strobes=1,frames=1;
static uint32_t ack,fsm=3,count=1,read_error,marker_error,markers,stopped,fault;
static void __DSB(void){}
static int rd8(void *ctx,uint16_t address,uint8_t *v){
 (void)ctx;if(read_error==address)return -1;
 *v=(uint8_t)(address==0x0202?ack:fsm);return 0;
}
static int rd16(void *ctx,uint16_t address,uint16_t *v){
 (void)ctx;if(read_error==address)return -1;*v=(uint16_t)count;return 0;
}
static int phase_gpio_emit(uint32_t event){if(event!=11)abort();markers++;return !marker_error;}
static void raw_capture_stopped(void){stopped++;}
static uint32_t raw_capture_fault(void){return fault;}
'''
SUFFIX=r'''
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d:%s\n",__LINE__,#x);return 1;}}while(0)
int main(int argc,char **argv){
 if(argc!=2)return 2;uint32_t test=(uint32_t)strtoul(argv[1],0,0),expected=0;
 AST[3]=2;AST[30]=3;AST[31]=400000000;dwt.CYCCNT=500000;
 ast_poll();CHECK(!stopped&&AST[19]==1&&AST[20]==3);
 dwt.CYCCNT+=500000;fsm=2;
 if(test==1)count=fast_strobes=2;
 else if(test==2)count=2; /* Independent observations are retained. */
 else if(test==3){dwt.CYCCNT=400000001;expected=0x91;}
 else if(test==4){read_error=0x0202;expected=0x92;}
 else if(test==5){read_error=0x0028;expected=0x93;}
 else if(test==6){read_error=0x0050;expected=0x94;}
 else if(test==7){ack=1;expected=0x95;}
 else if(test==8){AST[18]=1;expected=0x95;}
 else if(test==9){count=0;expected=0x95;}
 else if(test==10){count=3;expected=0x95;}
 else if(test==11){fast_strobes=0;expected=0x95;}
 else if(test==12){gpio.IDR=1;expected=0x95;}
 else if(test==13){marker_error=1;expected=0x98;}
 else if(test==14){AST[9]=1;expected=0x95;}
 ast_poll();
 if(test>=15){
  CHECK(stopped==1&&AST[3]==3&&AST[30]==7);
  dwt.CYCCNT+=100000000;
  if(test==15){read_error=0x0028;expected=0x96;}
  else if(test==16){read_error=0x0050;expected=0x96;}
  else if(test==17){fsm=3;expected=0x97;}
  else if(test==18){count++;expected=0x97;}
  else if(test==19){fast_strobes++;expected=0x97;}
  else if(test==20){gpio.IDR=1;expected=0x97;}
  else if(test==21){AST[18]=1;expected=0x97;}
  else if(test==22){frames=2;expected=0x97;}
  else if(test==23){fault=1;expected=0x97;}
  else return 3;
  CHECK(raw_sensor_autostop_finish()==-1);
 }else if(!expected){
  CHECK(stopped==1&&capture_sensor_stopped&&AST[3]==3&&AST[30]==7);
  CHECK(AST[15]==count&&AST[17]==fast_strobes&&AST[29]==count&&markers==1);
  dwt.CYCCNT+=100000000;CHECK(raw_sensor_autostop_finish()==0);
  CHECK(AST[3]==4&&AST[30]==15&&AST[25]==count&&AST[26]==fast_strobes);
 }
 if(expected)CHECK(AST[4]==expected&&AST[3]==15&&capture_async_error==expected&&!capture_stop_pending);
 CHECK(AST[18]==(test==8||test==21)); /* No hidden fallback STOP exists. */
 return 0;
}
'''

class SensorAutostopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('clang') or shutil.which('gcc')
        if not compiler: raise RuntimeError('host C compiler required')
        cls.temp=tempfile.TemporaryDirectory()
        source=Path(cls.temp.name)/'autostop.c'
        cls.binary=source.with_suffix('.exe')
        source.write_text(PREFIX+(HERE/'sensor_autostop.inc').read_text()+SUFFIX)
        r=subprocess.run([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(cls.binary)],capture_output=True,text=True)
        if r.returncode: raise RuntimeError(r.stderr)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_real_observer_one_two_independent_and_all_failure_gates(self):
        for case in range(24):
            with self.subTest(case=case):
                r=subprocess.run([str(self.binary),str(case)],capture_output=True,text=True,timeout=10)
                self.assertEqual(r.returncode,0,r.stderr)

    def test_never_writes_sensor_and_preserves_late_placement(self):
        source=(HERE/'sensor_autostop.inc').read_text()
        self.assertNotRegex(source,r'\b(?:wr8|wr16|wr32|VD6G_Stop)\s*\(')
        self.assertIn('AST_LATE static void ast_poll',source)
        self.assertIn('AST_LATE int raw_sensor_autostop_finish',source)

    def test_generated_paths_preserve_preload_evidence_and_remove_success_stop(self):
        sys.path.insert(0,str(HERE))
        try:
            import build
            import sensor_autostop_transform as ast
            normal=build.transform_magic(build.transform_capture(
                (build.BASE/'receiver/capture.c').read_text()))
            source=ast.capture(normal)
            poll=source[source.index('void raw_capture_poll(void)'):]
            # The source's unused #else retains VD6G_Stop; the admitted
            # diagnostic always defines RAW_ASYNC_STOP=1. Its active arm
            # has no STOP write and keeps the ordinary snapshot checks.
            active=poll.split('#if RAW_ASYNC_STOP',2)[-1].split('#else',1)[0]
            self.assertNotIn('wr8(&sensor,0x0202,1U)',active)
            self.assertIn('fast_shutdown_data_off()',poll)
            self.assertIn('AST[18]++',source)
            self.assertIn('AST[32]=fast_strobes;',source)
            self.assertIn('AST[33]=DWT->CYCCNT;',source)
            prestart=ast.sensor(build.sensor_source((build.BASE/'staged/stage1_sensor.c').read_text()))
            self.assertLess(prestart.index('write_value(0x048C,1U,2)'),prestart.index('event(109)'))
            self.assertLess(prestart.index('read_reg(0x0050,2,&ast_count)'),prestart.index('event(109)'))
        finally:
            sys.path.remove(str(HERE))

if __name__=='__main__': unittest.main()
