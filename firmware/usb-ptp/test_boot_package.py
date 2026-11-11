"""Offline boot package regressions; never import or operate bench clients.

Set USB_BOOT_TEST_PACKAGE to a package directory for linked-artifact checks.
Without it, pure input/mutation checks and a native cache-guard harness run.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('usb_boot_package',HERE/'package.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def fixture():
 image=bytearray(128)
 struct.pack_into('<II',image,0,p.USB_STACK,p.USB_LOAD+65)
 image[80:82]=b'\xfe\xe7'
 manifest=dict(schema=1,kind='usb-ptp-ram',load=p.USB_LOAD,entry=p.USB_LOAD+65,
               stack=p.USB_STACK,park=p.USB_LOAD+80,proof=0x343F8000,proof_words=64,
               request=0x343F7F00,bss_start=p.USB_LOAD+128,bss_end=p.USB_LOAD+256,
               bytes=len(image),sha256=p.sha(image))
 return manifest,bytes(image)


class BoundsTests(unittest.TestCase):
 def setUp(self):self.m,self.image=fixture()
 def reject(self,**changes):
  m={**self.m,**changes}
  with self.assertRaises(ValueError):p.validate_usb_image(m,self.image)
 def test_valid_image(self):p.validate_usb_image(self.m,self.image)
 def test_bad_manifest_identity(self):
  for changes in ({'schema':2},{'kind':'unrelated'},{'sha256':'0'*64},{'bytes':127},{'load':p.USB_LOAD+4}):
   with self.subTest(changes=changes):self.reject(**changes)
 def test_entry_outside_image_or_not_thumb(self):
  for address in (p.USB_LOAD-1,p.USB_LOAD+64,p.USB_LOAD+129):
   with self.subTest(address=address):self.reject(entry=address)
 def test_stack_and_records(self):
  for changes in ({'stack':p.USB_STACK-8},{'proof':0},{'proof_words':63},{'request':0},{'entry':True}):
   with self.subTest(changes=changes):self.reject(**changes)
 def test_bss_cannot_overlap_code_or_reserved_ram(self):
  for changes in ({'bss_start':p.USB_LOAD+124},{'bss_start':p.USB_LOAD+129},
                  {'bss_end':p.USB_LOAD+120},{'bss_end':p.USB_BSS_LIMIT},
                  {'bss_end':p.USB_STACK}):
   with self.subTest(changes=changes):self.reject(**changes)
 def test_vector_and_park_bytes_not_trusted_from_manifest(self):
  for offset in (0,4,80):
   with self.subTest(offset=offset):
    image=bytearray(self.image);image[offset]^=1;m={**self.m,'sha256':p.sha(image)}
    with self.assertRaises(ValueError):p.validate_usb_image(m,image)
 def test_flash_length_limit(self):
  image=self.image+b'\0'*(p.USB_MAX_BYTES-len(self.image));m={**self.m,'bytes':len(image),'sha256':p.sha(image),'bss_start':p.USB_LOAD+len(image),'bss_end':p.USB_LOAD+len(image)}
  p.validate_usb_image(m,image)
  with self.assertRaises(ValueError):p.validate_usb_image({**m,'bytes':len(image)+1,'sha256':p.sha(image+b'\0')},image+b'\0')
 def test_checks_survive_python_optimization(self):
  code="import runpy; p=runpy.run_path(sys.argv[1]); p['require'](False,'intentional guard')"
  result=subprocess.run([sys.executable,'-O','-c','import sys;'+code,str(HERE/'package.py')],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertIn('intentional guard',result.stderr)

class USBHoldPolicyTests(unittest.TestCase):
 def setUp(self):self.m={'gpio_hold':dict(schema=2,port='GPIOA',pin=2,mode='usb-off',shutdown_proof_schema=3)}
 def test_usb_off_policy_admits_normal_pa2_and_explicit_legacy(self):
  p.validate_usb_hold_policy(self.m,'pa2-hold')
  p.validate_usb_hold_policy(self.m,'legacy-october28',True)
 def test_old_reasserting_or_missing_policy_is_rejected(self):
  for change in ({'schema':1},{'pin':7},{'port':'GPIOD'},{'mode':'usb-hold'},{'shutdown_proof_schema':2}):
   with self.subTest(change=change),self.assertRaises(ValueError):
    p.validate_usb_hold_policy({'gpio_hold':{**self.m['gpio_hold'],**change}},'pa2-hold')
  with self.assertRaises(ValueError):p.validate_usb_hold_policy({},'pa2-hold')
 def test_latched_capture_cannot_override_usb_selection(self):
  with self.assertRaises(ValueError):p.validate_usb_hold_policy(self.m,'pa2-hold',True)


class ReferenceAndCompositionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=(p.REFERENCE/'stage1.bin').read_bytes()
  cls.sector=(p.REFERENCE/'capture_sector_0.bin').read_bytes()
  cls.reference=json.loads((p.REFERENCE/'manifest.json').read_text(encoding='utf-8'))
  # Independently linked encodings for these exact two addresses.
  cls.patch=bytes.fromhex('01f00bb8')
  cls.hook=p.DSB+b'\0'*16
 def test_pinned_reference(self):p.validate_reference(self.original,self.sector,self.reference)
 def test_corrupt_reference_is_rejected_even_with_updated_manifest(self):
  bad=bytearray(self.sector);bad[-1]^=1
  m={**self.reference,'program_sha256':p.sha(bad)}
  with self.assertRaises(ValueError):p.validate_reference(self.original,bad,m)
 def test_nonlinking_branch_and_backwards_branch(self):
  self.assertEqual(p.branch_target(self.patch,p.PATCH_ADDRESS),p.HOOK_BASE)
  self.assertEqual(p.branch_target(bytes.fromhex('fef7e3bf'),0x34181E60),p.RESUME_ADDRESS)
 def test_reject_linking_wrong_target_and_short_branch(self):
  for patch in (bytes.fromhex('01f00bf8'),bytes.fromhex('01f00ab8'),b'\0\xe0'):
   with self.subTest(patch=patch.hex()),self.assertRaises(ValueError):
    p.compose(self.original,self.sector,patch,self.hook,b'1234',b'12345678')
 def test_prefix_and_capture_preservation(self):
  prefix,boot,s0,s1=p.compose(self.original,self.sector,self.patch,self.hook,b'selector',b'USBIMAGE')
  self.assertEqual(prefix[:p.PATCH_OFFSET],self.original[:p.PATCH_OFFSET])
  self.assertEqual(prefix[p.PATCH_OFFSET+4:len(self.original)],self.original[p.PATCH_OFFSET+4:])
  self.assertEqual(prefix[len(self.original):],self.hook)
  self.assertEqual(s0[p.CAPTURE_OFFSET:],self.sector[p.CAPTURE_OFFSET:])
  self.assertEqual(s0[:len(boot)],boot)
  self.assertEqual(s1[:8],b'selector');self.assertEqual(s1[0x2000:0x2008],b'USBIMAGE')
  self.assertEqual(s1[8:0x2000],b'\xff'*(0x2000-8))
  self.assertEqual(len(s0),p.SECTOR_BYTES);self.assertEqual(len(s1),p.SECTOR_BYTES)
 def test_reserved_regions_and_displaced_barrier(self):
  for changes in ({'hook':b'\0'*16},{'hook':p.DSB+b'\0'*445},
                  {'selector':b'x'*8193},{'selector':b''},{'usb':b'x'*(p.USB_MAX_BYTES+1)}):
   params=dict(original=self.original,sector=self.sector,patch=self.patch,hook=self.hook,selector=b'1234',usb=b'12345678');params.update(changes)
   with self.subTest(changes=tuple(changes)),self.assertRaises(ValueError):p.compose(**params)
 def test_recovery_metadata_preserves_contract_without_allowlisting(self):
  prefix,boot,s0,_=p.compose(self.original,self.sector,self.patch,self.hook,b'1234',b'12345678')
  m=p.recovery_manifest(self.reference,prefix,boot,s0)
  for key in ('recovery_gpio','recovery_vcp','error_signal'):
   if key in self.reference:self.assertEqual(m[key],self.reference[key])
  self.assertEqual(m['stage1_raw_sha256'],p.sha(prefix));self.assertEqual(m['program_sha256'],p.sha(s0))
  self.assertFalse(m['usb_boot_package']['recovery_allowlist_admission'])
  self.assertEqual(self.reference['program_sha256'],p.REFERENCE_SECTOR_SHA)


class NativeCacheGuardTests(unittest.TestCase):
 def test_actual_boot_read_rejects_caches_before_touching_nor(self):
  compiler=shutil.which('clang') or shutil.which('gcc')
  if not compiler:self.skipTest('Native C compiler unavailable')
  with tempfile.TemporaryDirectory(prefix='usb-boot-cache-') as tmp:
   root=Path(tmp)
   (root/'stm32n657xx.h').write_text(r'''
#include <stdint.h>
typedef struct { uint32_t CR,CCR,IR,SR,FCR,DLR,AR,DR; } XSPI_TypeDef;
typedef struct { uint32_t CCR; } SCB_Type;
typedef struct { uint32_t CYCCNT; } DWT_Type;
extern XSPI_TypeDef fake_x;extern SCB_Type scb;extern DWT_Type dwt;
#define XSPI1 (&fake_x)
#define SCB (&scb)
#define DWT (&dwt)
#define SCB_CCR_IC_Msk (1U<<17)
#define SCB_CCR_DC_Msk (1U<<16)
#define XSPI_SR_BUSY (1U<<5)
#define XSPI_SR_FLEVEL (0x7FU<<8)
#define XSPI_SR_TEF 1U
#define XSPI_SR_TCF 2U
#define XSPI_FCR_CTCF 2U
#define XSPI_FCR_CTEF 1U
''',encoding='utf-8')
   shutil.copyfile(HERE/'boot_read.h',root/'boot_read.h')
   (root/'main.c').write_text(r'''
#include <string.h>
#include "boot_read.h"
XSPI_TypeDef fake_x;SCB_Type scb;DWT_Type dwt;
int main(void){uint8_t target[8];
 for(unsigned mask=1;mask<4;mask++){
  fake_x=(XSPI_TypeDef){.CR=0x10000001,.CCR=0x01002101,.IR=11,.FCR=0x1234,.DLR=0x5678,.AR=0x9ABC};
  XSPI_TypeDef before=fake_x;memset(target,0xA5,sizeof target);scb.CCR=mask<<16;
  if(boot_read(0x10000,target,8,0)!=0||memcmp(&fake_x,&before,sizeof fake_x))return 1;
  for(unsigned i=0;i<8;i++)if(target[i]!=0xA5)return 2;
 }
 return 0;
}
''',encoding='utf-8')
   exe=root/'cache-test.exe'
   compiled=subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-I'+str(root),str(root/'main.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(compiled.returncode,0,compiled.stderr)
   ran=subprocess.run([str(exe)],capture_output=True,text=True)
   self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)


class NativeCacheTransitionTests(unittest.TestCase):
 def test_actual_hook_restores_initial_ic_only_after_capture_return(self):
  compiler=shutil.which('clang') or shutil.which('gcc')
  if not compiler:self.skipTest('Native C compiler unavailable')
  with tempfile.TemporaryDirectory(prefix='usb-boot-transition-') as tmp:
   root=Path(tmp)
   # Only replace the proof record MMIO address with a native RAM symbol.
   source=(HERE/'boot_hook.c').read_text(encoding='utf-8')
   self.assertEqual(source.count('0x343F9000U'),1)
   (root/'hook.c').write_text(source.replace('0x343F9000U','(uintptr_t)proof'),encoding='utf-8')
   (root/'boot_read.h').write_text(r"""
#include <stdint.h>
#include <setjmp.h>
#include <assert.h>
typedef struct {uint32_t CCR;} MockSCB;
typedef struct {uint32_t CYCCNT;} MockDWT;
extern MockSCB scb;extern MockDWT dwt;extern uint32_t proof[16];
extern unsigned reads,branches,disabled,enabled,barriers,read_result;
extern jmp_buf failure;
#define SCB (&scb)
#define DWT (&dwt)
#define SCB_CCR_IC_Msk (1U<<17)
#define SCB_CCR_DC_Msk (1U<<16)
static void SCB_DisableICache(void){disabled++;scb.CCR&=~SCB_CCR_IC_Msk;}
static void SCB_EnableICache(void){assert(branches==1);enabled++;scb.CCR|=SCB_CCR_IC_Msk;}
static void __DSB(void){barriers|=1;}
static void __ISB(void){assert(barriers&1);barriers|=2;}
static void __NOP(void){longjmp(failure,1);}
static int boot_read(uint32_t offset,uint8_t *to,uint32_t n,uint32_t crc){
 assert(!(scb.CCR&SCB_CCR_IC_Msk));
 assert(offset==0x10000 && to==(uint8_t*)0x34200000 && n==4284 && crc==123);
 reads++;return (scb.CCR&SCB_CCR_DC_Msk)?0:(int)read_result;
}
void test_selector(void);
""",encoding='utf-8')
   (root/'boot_config.h').write_text('#define SELECTOR_BYTES 4284U\n#define SELECTOR_CRC 123U\n#define SELECTOR_ENTRY ((uintptr_t)test_selector)\n',encoding='utf-8')
   (root/'main.c').write_text(r"""
#include <string.h>
#include "hook.c"
MockSCB scb;MockDWT dwt;uint32_t proof[16];jmp_buf failure;
unsigned reads,branches,disabled,enabled,barriers,read_result;
void test_selector(void){assert(!enabled && barriers==3 && !(scb.CCR&SCB_CCR_IC_Msk));branches++;}
int main(void){
 for(unsigned initial=0;initial<4;initial++){
  reads=branches=disabled=enabled=barriers=0;read_result=1;memset(proof,0,sizeof proof);
  scb.CCR=0x201|(initial<<16);
  if(!setjmp(failure)){usb_selector_load();assert(!(initial&1));}
  else{assert(initial&1);assert(proof[1]==0xE001 && reads==1 && !branches && disabled==!!(initial&2) && !enabled);continue;}
  assert(reads==1 && branches==1 && disabled==!!(initial&2) && enabled==!!(initial&2));
  assert(scb.CCR==(0x201|(initial<<16)) && proof[1]==3);
 }
 reads=branches=disabled=enabled=barriers=0;read_result=0;scb.CCR=SCB_CCR_IC_Msk|0x201;
 if(!setjmp(failure)){usb_selector_load();return 2;}
 assert(proof[1]==0xE001 && reads==1 && disabled==1 && !enabled && !branches);
 return 0;
}
""",encoding='utf-8')
   exe=root/'transition-test.exe'
   compiled=subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-I'+str(root),str(root/'main.c'),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(compiled.returncode,0,compiled.stderr)
   ran=subprocess.run([str(exe)],capture_output=True,text=True)
   self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)


@unittest.skipUnless(os.environ.get('USB_BOOT_TEST_PACKAGE'),'Set USB_BOOT_TEST_PACKAGE for linked artifact checks')
class LinkedPackageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=Path(os.environ['USB_BOOT_TEST_PACKAGE']).resolve()
  cls.m=json.loads((cls.out/'manifest.json').read_text(encoding='utf-8'))
  cls.hook=(cls.out/'hook.bin').read_bytes();cls.hl=(cls.out/'hook.lst').read_text(encoding='utf-8')
  cls.sl=(cls.out/'selector.lst').read_text(encoding='utf-8')
 def test_source_binding(self):
  for name,value in self.m['sources'].items():
   self.assertEqual(p.sha((self.out/name).read_bytes()),value)
   self.assertEqual((self.out/name).read_bytes(),(HERE/name).read_bytes())
 def test_linked_context_save_restore_and_resume(self):
  # DSB; STM SP!,{r0-r12,lr}; MRS APSR; PUSH {r0,r1}.
  self.assertEqual(self.hook[:14],bytes.fromhex('bff34f8f2de9ff5feff3008003b4'))
  # POP {r0,r1}; MSR APSR_nzcvqg,r0; LDM SP!,{r0-r12,lr}; DSB.
  self.assertEqual(self.hook[18:32],bytes.fromhex('03bc80f3008cbde8ff5fbff34f8f'))
  self.assertEqual(p.branch_target(self.hook[32:36],p.HOOK_BASE+32),p.RESUME_ADDRESS)
  self.assertEqual((14+2)*4%8,0)  # The hook preserves ABI stack alignment.
 def test_linked_patch_and_original_capture_exact(self):
  capture=Path(self.m.get('capture_build',p.REFERENCE))
  original=(capture/'stage1.bin').read_bytes();prefix=(self.out/'stage1.bin').read_bytes()
  self.assertEqual(p.branch_target(prefix[p.PATCH_OFFSET:p.PATCH_OFFSET+4],p.PATCH_ADDRESS),p.HOOK_BASE)
  self.assertEqual(prefix[:p.PATCH_OFFSET],original[:p.PATCH_OFFSET])
  self.assertEqual(prefix[p.PATCH_OFFSET+4:len(original)],original[p.PATCH_OFFSET+4:])
  sector=(self.out/'sector0.bin').read_bytes();self.assertEqual(sector[p.CAPTURE_OFFSET:],(capture/'capture_sector_0.bin').read_bytes()[p.CAPTURE_OFFSET:])
  self.assertEqual(p.sha(prefix),self.m['prefix_sha256']);self.assertEqual(p.sha(sector),self.m['sector0_sha256'])
 def test_early_uart_guard_is_identical_to_original(self):
  prefix=(self.out/'stage1.bin').read_bytes();legacy=(p.REFERENCE/'stage1.bin').read_bytes()
  # Reset startup through the complete PE6/UART park/recovery block remains
  # fixed. PA2 may change only the reset vector before this range.
  self.assertEqual(prefix[0x40:p.PATCH_OFFSET],legacy[0x40:p.PATCH_OFFSET])
  self.assertEqual(prefix[0x38C:0x38E],bytes.fromhex('fee7'))
 def test_pa2_capture_reference_and_usb_contract(self):
  if self.m.get('capture_profile')!='pa2-hold':self.skipTest('Legacy package has no early HOLD')
  capture=Path(self.m['capture_build']);original=(capture/'stage1.bin').read_bytes()
  sector=(capture/'capture_sector_0.bin').read_bytes();manifest=json.loads((capture/'manifest.json').read_text(encoding='utf-8'))
  self.assertEqual(p.validate_reference(original,sector,manifest),'pa2-hold')
  self.assertEqual(struct.unpack_from('<I',original,4)[0],0x34181DF1)
  self.assertEqual(self.m['gpio_hold'],manifest['raw_slots']['gpio_hold_contract'])
  usb=json.loads((Path(self.m['usb_build'])/'manifest.json').read_text(encoding='utf-8'))
  self.assertEqual((usb['gpio_hold']['port'],usb['gpio_hold']['pin']),('GPIOA',2))
  p.validate_usb_hold_policy(usb,'pa2-hold',self.m['force_capture'])
  self.assertEqual(usb['gpio_hold']['shutdown_proof_schema'],3)
  self.assertEqual(self.m['usb_hold_policy'],usb['gpio_hold'])
  # A self-consistent manifest cannot admit corrupted code or old PD7 claims.
  bad=bytearray(original);bad[0x19F0]^=1
  with self.assertRaises(ValueError):p.validate_reference(bad,sector,{**manifest,'stage1_raw_sha256':p.sha(bad)})
  for change in ({'port':'GPIOD'},{'pin':7},{'schema':2}):
   with self.subTest(change=change),self.assertRaises(ValueError):
    p.validate_reference(original,sector,{**manifest,'raw_slots':{**manifest['raw_slots'],'gpio_hold_contract':{**manifest['raw_slots']['gpio_hold_contract'],**change}}})
 def test_linked_loaders_guard_caches_and_sync_before_executable_branch(self):
  self.assertRegex(self.hl,r'tst\.w\s+r3, #196608')
  guard=self.hl.index('#196608');first_nor_store=self.hl.index('str\tr1, [r2, #36]')
  self.assertLess(guard,first_nor_store)
  # A copied executable is only entered after instruction synchronization.
  self.assertRegex(self.hl,r'dsb\s+sy\s*\n[^\n]+isb\s+sy(?:(?!\bblx\b)[\s\S])*?blx\s+r3')
  if not self.m['force_capture']:
   self.assertRegex(self.sl,r'#196608')
   self.assertTrue(re.search(r'dsb\s+sy\s*\n[^\n]+isb\s+sy(?:\s*\n[^\n]+){1,3}?blx\s+',self.sl),'USB handoff lacks adjacent DSB/ISB before branch')
 def test_linked_ic_disable_invalidate_and_conditional_restore(self):
  disable=re.search(r'bic\.w\s+[^\n]+#131072',self.hl)
  restore=re.search(r'orr\.w\s+[^\n]+#131072',self.hl)
  handoff=re.search(r'\bblx\s+r3',self.hl)
  self.assertIsNotNone(disable);self.assertIsNotNone(restore);self.assertIsNotNone(handoff)
  self.assertLess(disable.start(),handoff.start());self.assertLess(handoff.start(),restore.start())
  self.assertEqual(len(re.findall(r'str\.w\s+[^\n]+#592',self.hl)),2)
  self.assertRegex(self.hl[handoff.end():restore.start()],r'cbnz\s+r4,')
  self.assertGreaterEqual(len(re.findall(r'dsb\s+sy\s*\n[^\n]+isb\s+sy',self.hl)),5)
 def test_recovery_folder_matches_package_without_generic_admission(self):
  recovery=self.out/'recovery';m=json.loads((recovery/'manifest.json').read_text(encoding='utf-8'))
  self.assertEqual((recovery/'stage1.bin').read_bytes(),(self.out/'stage1.bin').read_bytes())
  self.assertEqual((recovery/'capture_sector_0.bin').read_bytes(),(self.out/'sector0.bin').read_bytes())
  self.assertEqual(m['stage1_raw_sha256'],self.m['prefix_sha256']);self.assertEqual(m['program_sha256'],self.m['sector0_sha256'])
  self.assertFalse(m['usb_boot_package']['recovery_allowlist_admission'])
  original_checker=(p.ROOT/'firmware/capture-timing/recovery_gpio/check_park.py').read_text(encoding='utf-8')
  self.assertNotIn(self.m['prefix_sha256'],original_checker)
 def test_selector_memory_and_nor_bounds(self):
  symbols=(self.out/'selector.symbols').read_text(encoding='utf-8')
  start=int(re.search(r'^([0-9a-f]+) \w __bss_start__$',symbols,re.M)[1],16)
  end=int(re.search(r'^([0-9a-f]+) \w __bss_end__$',symbols,re.M)[1],16)
  self.assertGreaterEqual(start,p.SELECTOR_LOAD+self.m['selector_bytes']);self.assertLess(end,p.SELECTOR_LIMIT)
  sector1=(self.out/'sector1.bin').read_bytes();self.assertEqual(len(sector1),p.SECTOR_BYTES)
  self.assertEqual(sector1[:self.m['selector_bytes']],(self.out/'selector.bin').read_bytes())
  self.assertEqual(sector1[self.m['selector_bytes']:0x2000],b'\xff'*(0x2000-self.m['selector_bytes']))
  usb=Path(self.m['usb_build']);image=(usb/'usb.bin').read_bytes();manifest=json.loads((usb/'manifest.json').read_text(encoding='utf-8'))
  p.validate_usb_image(manifest,image);self.assertEqual(sector1[0x2000:0x2000+len(image)],image)
  self.assertEqual(sector1[0x2000+len(image):],b'\xff'*(p.SECTOR_BYTES-0x2000-len(image)))


if __name__=='__main__':unittest.main()
