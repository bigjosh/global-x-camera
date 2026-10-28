"""Run the strict one-frame observer and post-START readback as native C."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from test_sensor_autostop import PREFIX

HERE=Path(__file__).resolve().parent
SINGLE_PREFIX=PREFIX.replace('#include <stdio.h>','#include <stdio.h>\n#include <setjmp.h>')
SINGLE_PREFIX=SINGLE_PREFIX.replace('static uint32_t ack,fsm=3,count=1,',
    'static uint32_t repeat=1,next=4;\nstatic uint32_t ack,fsm=3,count=1,')
SINGLE_PREFIX=SINGLE_PREFIX.replace('*v=(uint16_t)count;return 0;',
    '*v=(uint16_t)(address==0x048C?repeat:address==0x048E?next:count);return 0;')
SINGLE_PREFIX+='''
static volatile uint32_t early_mock[32];
static jmp_buf failed_jump;
static void fail(uint32_t where,int result){(void)where;(void)result;longjmp(failed_jump,1);}
'''
SUFFIX=r'''
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d:%s\n",__LINE__,#x);return 1;}}while(0)
int main(int argc,char **argv){
 if(argc!=2)return 2;uint32_t test=(uint32_t)strtoul(argv[1],0,0);
 early_mock[4]=100000;early_mock[5]=120000;dwt.CYCCNT=1000000;
 AST[12]=77;AST[32]=0;AST[33]=900000;count=test==1?1:0;
 if(test==2)repeat=2;
 if(test==3)next=0;
 if(test==4)count=2;
 if(test==5)read_error=0x048C;
 if(test==6)read_error=0x048E;
 if(test==7)read_error=0x0050;
 if(setjmp(failed_jump)) {
  CHECK(test>=2&&test<=7);CHECK(AST[3]==15&&AST[4]==0x99);return 0;
 }
 raw_sensor_autostop_begin();
 CHECK(!(test>=2&&test<=7));
 CHECK(AST[1]==2&&AST[3]==1&&AST[30]==1&&AST[9]==(test==1));
 CHECK(AST[5]>=AST[11]&&AST[7]==1&&AST[8]==4);
 CHECK(AST[12]==77&&AST[32]==0&&AST[33]==900000);
 AST[3]=2;AST[30]|=2;fsm=2;count=fast_strobes=1;dwt.CYCCNT+=500000;
 if(test==8)AST[18]=1;
 if(test==9)fast_strobes=2;
 if(test==10)count=2;
 if(test==11)count=0;
 ast_poll();
 if(test>=8&&test<=11){CHECK(AST[3]==15&&AST[4]==0x95);return 0;}
 CHECK(AST[3]==3&&AST[29]==1&&AST[15]==1&&AST[17]==1&&markers==1);
 CHECK(stopped==1&&capture_sensor_stopped&&!capture_async_error);
 dwt.CYCCNT+=100000000;
 CHECK(raw_sensor_autostop_finish()==0&&AST[3]==4&&AST[30]==15);
 CHECK(!AST[18]&&AST[25]==1&&AST[26]==1);
 return 0;
}
'''

class SensorSingleFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('clang') or shutil.which('gcc')
        if not compiler: raise RuntimeError('host C compiler required')
        cls.temp=tempfile.TemporaryDirectory()
        source=Path(cls.temp.name)/'single.c';cls.binary=source.with_suffix('.exe')
        observer=(HERE/'sensor_autostop.inc').read_text().replace(
            '(volatile uint32_t *)0x343F4000U','early_mock')
        source.write_text(SINGLE_PREFIX+observer+SUFFIX)
        r=subprocess.run([compiler,'-DRAW_SENSOR_SINGLE_FRAME=1','-std=c11','-O2',
            '-Wall','-Wextra','-Werror',str(source),'-o',str(cls.binary)],capture_output=True,text=True)
        if r.returncode: raise RuntimeError(r.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_poststart_readback_and_strict_single_frame(self):
        for case in range(12):
            with self.subTest(case=case):
                r=subprocess.run([str(self.binary),str(case)],capture_output=True,text=True,timeout=10)
                self.assertEqual(r.returncode,0,r.stderr)

    def test_prefix_transform_keeps_manual_mode_and_one_context_burst(self):
        sys.path.insert(0,str(HERE))
        try:
            import build
            import sensor_autostop_transform as ast
            source=build.sensor_source((build.BASE/'staged/stage1_sensor.c').read_text())
            changed=ast.sensor_single(source)
            self.assertIn('manual[12]={2,0,',changed)
            self.assertIn('TRY(22,write_reg(0x044C,manual,12));',changed)
            self.assertNotIn('TRY(32,write_value(0x044C,2,1));',changed)
            self.assertEqual(changed.count('single_context[4]={1,0,4,0}'),1)
            self.assertIn('TRY(32,write_reg(0x048C,single_context,4));',changed)
            self.assertLess(changed.index('write_reg(0x048C,single_context,4)'),changed.index('event(109)'))
            with self.assertRaises(ValueError):
                ast.sensor_single(source.replace('manual[12]={2,0,','manual[12]={0,0,'))
        finally:sys.path.remove(str(HERE))

    def test_production_audit_rejects_old_explicit_stop_prefix(self):
        import single_frame_prefix as audit
        with self.assertRaisesRegex(ValueError,'Unreviewed single-frame prefix bytes'):
            audit.check(HERE,audit.REFERENCE.read_bytes())

if __name__=='__main__':unittest.main()
