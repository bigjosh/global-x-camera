"""Offline fixed-window NOR audit. No programmer, debugger or device access.

Execute the actual relocated planning/programming C against a memory NOR and
the exact WIP/WEL completion code against scripted status values. Host wrapper
tests replace nor_bench completely before importing it.
"""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


builder=load('fixed_nor_builder_audit',HERE/'build_nor_sector1.py')
original=(builder.SOURCE/'programmer.c').read_text(encoding='utf-8')
completion=load('fixed_nor_completion_audit',builder.SOURCE/'test_completion.py')


def calls(text):
    return [tuple(x.strip() for x in m.split(','))
            for m in re.findall(r'transfer\(c,\s*([^)]*)\)',text)]


EXECUTE_HARNESS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t s[128],d[64];
static uint8_t flash[3*65536],input[65536],output[65536];
#define S s
#define D d
#define INPUT input
#define OUTPUT output
ENUMS
CONTEXT
FAIL
CRC
COMPARE
static uint32_t addressed,erases,pages,finish_calls;
static int status(struct context *c){(void)c;S[NOR_STATUS]=0;return 1;}
static int security(struct context *c){(void)c;S[NOR_SECURITY]=0;return 1;}
static int healthy(struct context *c){(void)c;return 1;}
static int write_enable(struct context *c){(void)c;S[WREN_COUNT]++;return 1;}
static int write_finished(struct context *c,uint32_t us){(void)c;(void)us;finish_calls++;return 1;}
static int transfer(struct context *c,uint32_t op,int has_address,uint32_t address,
                    uint32_t n,int receive,volatile uint8_t *data){
 (void)c;
 if(!has_address){assert(op==0x9f&&n==3&&receive);data[0]=0xc2;data[1]=0x80;data[2]=0x3a;return 1;}
 addressed++;
 assert(address>=65536&&address<131072&&address+n<=131072);
 if(op==0x0b){
  assert(receive&&data==OUTPUT+address-65536);
  assert(n==65536||n==4096||n==256);
  for(uint32_t i=0;i<n;i++)data[i]=flash[address+i];
 }else if(op==0x20){
  assert(!receive&&!n&&!data&&address%4096==0&&address+4096<=131072);
  assert(S[ADDRESS]==address-65536);assert(S[STAGE]==ST_ERASE);
  memset(flash+address,255,4096);erases++;
 }else{
  assert(op==0x02&&!receive&&n==256&&address%256==0);
  assert(data==INPUT+address-65536);assert(S[ADDRESS]==address-65536);assert(S[STAGE]==ST_PROGRAM);
  for(uint32_t i=0;i<n;i++)flash[address+i]&=data[i];pages++;
 }
 return 1;
}
EXECUTE
static struct context setup(void){
 struct context c={0};memset(s,0,sizeof s);memset(d,0,sizeof d);
 memset(flash,0xa5,65536);memset(flash+65536,0x37,65536);memset(flash+131072,0x5a,65536);
 memcpy(input,flash+65536,65536);memset(output,0xcc,65536);
 addressed=erases=pages=finish_calls=0;S[COMMAND]=3;S[FIRST_MISMATCH]=UINT32_MAX;
 return c;
}
static void crc_setup(void){S[EXPECTED_INPUT_CRC]=crc32_bytes(INPUT,65536);S[EXPECTED_CURRENT_CRC]=crc32_bytes(flash+65536,65536);}
static void unchanged_neighbors(void){for(uint32_t i=0;i<65536;i++){assert(flash[i]==0xa5);assert(flash[131072+i]==0x5a);}}
int main(void){
 struct context c=setup();crc_setup();execute(&c);
 assert(c.result==OK&&addressed==2&&erases==0&&pages==0&&S[CHANGED_MASK]==0);unchanged_neighbors();
 c=setup();for(uint32_t i=0;i<65536;i++)input[i]=(uint8_t)(i*13u+11u);crc_setup();execute(&c);
 assert(c.result==OK&&erases==16&&pages==256&&finish_calls==272);
 assert(S[CHANGED_MASK]==65535&&S[ERASED_MASK]==65535&&S[COMPLETED_MASK]==65535);
 assert(!memcmp(input,output,65536)&&!memcmp(input,flash+65536,65536));unchanged_neighbors();
 c=setup();memset(input,255,4096);memset(input+15*4096,255,4096);input[0]=0;input[65535]=0;
 crc_setup();execute(&c);assert(c.result==OK&&erases==2&&pages==2&&S[CHANGED_MASK]==0x8001);
 assert(S[FIRST_MISMATCH]==UINT32_MAX&&!memcmp(input,flash+65536,65536));unchanged_neighbors();
 c=setup();crc_setup();S[EXPECTED_INPUT_CRC]^=1;execute(&c);
 assert(c.result==INPUT_CHANGED&&addressed==0&&erases==0&&pages==0);unchanged_neighbors();
 c=setup();crc_setup();S[EXPECTED_CURRENT_CRC]^=1;execute(&c);
 assert(c.result==CURRENT_CHANGED&&addressed==1&&erases==0&&pages==0);unchanged_neighbors();
 c=setup();S[COMMAND]=2;execute(&c);assert(c.result==OK&&addressed==0&&erases==0&&pages==0);unchanged_neighbors();
 puts("6 relocated execute scenarios passed; neighbors and relative RAM/status indices intact");return 0;
}
'''


class RelocationTests(unittest.TestCase):
    def compile_run(self,code,includes=()):
        with tempfile.TemporaryDirectory(prefix='gx-nor-audit-') as directory:
            source=Path(directory)/'audit.c';exe=Path(directory)/'audit.exe'
            source.write_text(code,encoding='utf-8')
            compiler=shutil.which('clang') or shutil.which('gcc')
            self.assertIsNotNone(compiler)
            argv=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror']
            for path in includes:argv+=['-I',str(path)]
            built=subprocess.run(argv+[str(source),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            return ran.stdout

    def test_complete_input_pin_and_optimized_python_rejection(self):
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),builder.SOURCE_SHA256)
        self.assertRaises(ValueError,builder.transform,original+'\ntransfer(c,0x02,1,0,256,0,INPUT);\n')
        self.assertRaises(ValueError,builder.transform,original.replace('sector<16','sector<17'))
        script=("import importlib.util; from pathlib import Path; "
                f"s=importlib.util.spec_from_file_location('b', {str(HERE/'build_nor_sector1.py')!r}); "
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "m.transform((m.SOURCE/'programmer.c').read_text(encoding='utf-8')+'/* drift */')")
        p=subprocess.run([sys.executable,'-O','-c',script],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertIn('ValueError',p.stderr)

    def test_only_six_address_arguments_change(self):
        modified=builder.transform(original);old,new=calls(original),calls(modified)
        self.assertEqual(len(old),len(new))
        addressed=0
        for before,after in zip(old,new):
            if before[1]=='1':
                addressed+=1
                self.assertEqual(before[:2],after[:2]);self.assertEqual(before[3:],after[3:])
                self.assertEqual(after[2],'65536' if before[2]=='0' else '65536+'+before[2])
            else:self.assertEqual(before,after)
        self.assertEqual(addressed,6)
        # Removing the actual address expressions restores every other source
        # byte, including RAM pointers, loops, status schema and cleanup code.
        def neutral(text):
            return re.sub(r'(transfer\(c,\s*0x[0-9A-Fa-f]+,\s*1,\s*)[^,]+',r'\1ADDRESS',text)
        self.assertEqual(neutral(original),neutral(modified))

    def test_non_execute_functions_status_and_command_abi_are_identical(self):
        modified=builder.transform(original)
        signatures=re.findall(r'(?:static\s+)?(?:int|void|uint32_t)\s+(\w+)\s*\(',original)
        for name in signatures:
            if name=='execute':continue
            pattern=re.search(r'(?:static\s+)?(?:int|void|uint32_t)\s+'+name+r'\s*\(',original)
            self.assertEqual(completion.function(original,pattern.group()),completion.function(modified,pattern.group()),name)
        self.assertEqual(re.findall(r'enum \{.*?\};',original,re.S),re.findall(r'enum \{.*?\};',modified,re.S))

    def test_actual_relocated_execute_all_pages_and_refusals(self):
        source=builder.transform(original)
        code=EXECUTE_HARNESS.replace('ENUMS','\n'.join(re.findall(r'enum \{.*?\};',source,re.S)))
        code=code.replace('\nCONTEXT\n','\n'+re.search(r'struct context \{.*?\};',source,re.S).group()+'\n')
        for token,signature in [('FAIL','static void fail('),('CRC','static uint32_t crc32_bytes('),
                                ('COMPARE','static int compare('),('EXECUTE','static void execute(')]:
            code=code.replace('\n'+token+'\n','\n'+completion.function(source,signature)+'\n')
        self.assertIn('6 relocated execute scenarios passed',self.compile_run(code))

    def test_actual_relocated_wip_wel_completion_is_preserved(self):
        source=builder.transform(original)
        code=completion.HARNESS.replace('ENUMS','\n'.join(re.findall(r'enum \{.*?\};',source,re.S)))
        for token,signature in [('FAIL','static void fail('),('HEALTHY','static int healthy('),
                                ('FINISHED','static int write_finished(')]:
            code=code.replace('\n'+token+'\n','\n'+completion.function(source,signature)+'\n')
        self.assertIn('16 exact-C completion scenarios passed',self.compile_run(code,[builder.SOURCE]))


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='gx-nor-wrapper-')
        self.base=Path(self.temp.name)
        self.fake=types.ModuleType('nor_bench')
        self.dispatch=[]
        self.fake.main=lambda:self.dispatch.append(list(sys.argv))
        self.fake.Bench=lambda *_:(_ for _ in ()).throw(AssertionError('Unexpected bench construction'))
        with mock.patch.dict(sys.modules,{'nor_bench':self.fake}):
            self.wrapper=load('fixed_nor_wrapper_audit',HERE/'nor.py')

    def tearDown(self):self.temp.cleanup()

    def invoke(self,*args):
        with mock.patch.object(sys,'argv',['nor.py',*map(str,args)]),mock.patch.dict(sys.modules,{'build_nor_sector1':builder}):
            self.wrapper.main()

    def write_build(self,offset):
        path=self.base/f'helper{offset}';(path/'source').mkdir(parents=True)
        manifest={'fixed_flash_base':offset,'physical_write_window':[65536,131072],
                  'binary_sha256':'e69f0d0c3c49c2bad1ad5e7e8ff5907fcf3b251cb5b968629c18a9c57247f307'}
        (path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (path/'source/programmer.c').write_text(builder.transform(original),encoding='utf-8')
        return path

    def test_only_two_explicit_write_windows_dispatch(self):
        for offset in [0,65536]:
            build=self.write_build(offset)
            self.invoke('write','--offset',offset,'--build',build,'--current',self.base/'current',
                        '--desired',self.base/'desired','--out',self.base/'result')
            argv=self.dispatch[-1]
            self.assertEqual(argv[:2],['nor','write'])
            self.assertEqual(argv[argv.index('--sequence')+1],str(268000+offset))
            self.assertNotIn('--offset',argv) # address is compiled into the helper, not a command field
        with self.assertRaises((AssertionError,ValueError,SystemExit)):
            self.invoke('write','--offset',131072,'--build',build,'--current',self.base/'current',
                        '--desired',self.base/'desired','--out',self.base/'result')
        self.assertEqual(len(self.dispatch),2)

    def test_transformed_source_mismatch_refuses_before_dispatch(self):
        build=self.write_build(65536)
        (build/'source/programmer.c').write_text(builder.transform(original)+'/* unreviewed */',encoding='utf-8')
        with self.assertRaises((AssertionError,ValueError)):
            self.invoke('write','--offset',65536,'--build',build,'--current',self.base/'current',
                        '--desired',self.base/'desired','--out',self.base/'result')
        self.assertEqual(self.dispatch,[])


if __name__=='__main__':unittest.main()
