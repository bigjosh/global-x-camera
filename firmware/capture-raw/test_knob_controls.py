"""Offline controls patch, sensor readback and immutable metadata checks."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
import knob_transform

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class PrefixControlsTests(unittest.TestCase):
    def test_known_metadata_decode_rejects_corruption_and_false_applied_claim(self):
        raw = bytearray(128)
        struct.pack_into('<16I', raw, 0, 0x314E4B43, 1, 128, 3, 0, 23,
                         0, 3840, 3840, 0, 3840, 65535, 65535, 500000, 1280, 64813)
        raw[64:76] = bytes((2, 28, 62813 & 255, 62813 >> 8, 0, 1, 0, 1, 0, 1, 0, 1))
        struct.pack_into('<6I', raw, 76, 800, 160800000, 0, 0, 0, 68)
        struct.pack_into('<I', raw, 124, zlib.crc32(raw[:124]))
        result = knob_transform.decode_record(raw + bytes(24))
        self.assertEqual((result['validation'], result['asa'], result['coarse_lines']), ('configured', 800, 62813))
        self.assertEqual(result['nominal_exposure_us'], 500004)
        for i in range(128):
            bad = bytearray(raw); bad[i] ^= 1
            with self.subTest(byte=i), self.assertRaises(ValueError): knob_transform.decode_record(bad)
        struct.pack_into('<II', raw, 12, 4, 0)
        struct.pack_into('<I', raw, 20, 31)
        struct.pack_into('<I', raw, 124, zlib.crc32(raw[:124]))
        with self.assertRaises(ValueError): knob_transform.decode_record(raw)
        struct.pack_into('<III', raw, 84, 62813, 28, 256)
        struct.pack_into('<I', raw, 124, zlib.crc32(raw[:124]))
        self.assertEqual(knob_transform.decode_record(raw)['validation'], 'applied')

    def test_exact_patch_preserves_every_other_byte(self):
        original = (ROOT / 'firmware/usb-ptp/evidence/2026-11-13-d8-hold/capture-input/stage1.bin').read_bytes()
        changed, audit = knob_transform.patch_prefix(original)
        self.assertTrue(audit['all_other_bytes_preserved'])
        call = knob_transform.CALL - knob_transform.BASE
        hi, lo = struct.unpack_from('<HH', changed, call)
        self.assertEqual((hi & 0xF800, lo & 0xD000), (0xF000, 0xD000))
        sign = (hi >> 10) & 1
        offset = ((sign << 24) | ((1 ^ ((lo >> 13) & 1) ^ sign) << 23) |
                  ((1 ^ ((lo >> 11) & 1) ^ sign) << 22) | ((hi & 1023) << 12) | ((lo & 2047) << 1))
        if sign: offset -= 1 << 25
        self.assertEqual(knob_transform.CALL + 4 + offset, 0x34200100)
        for at in (0, 4, 0x390, 0x676, 0x1420, 0x19F0, call, knob_transform.MANUAL_LITERAL-knob_transform.BASE):
            bad = bytearray(changed); bad[at] ^= 1
            with self.subTest(at=at), self.assertRaises(ValueError):
                knob_transform.audit_prefix(original, bad)
        with self.assertRaises(ValueError): knob_transform.patch_prefix(changed)

    def test_transform_anchors_and_publication_order(self):
        baseline = ROOT / 'tmp/bringup/d8-hold-20261113/capture-standby-final/capture.c'
        text = knob_transform.capture(baseline.read_text())
        self.assertNotIn('if(line_length!=1236U)', text)
        self.assertNotIn('exposure_coarse!=RAW_EXPOSURE_COARSE', text)
        self.assertIn('knob_verify_applied(line_length,exposure_coarse)', text)
        with self.assertRaises(ValueError): knob_transform.capture(text)
        magic = knob_transform.magic_runtime((HERE / 'magic_runtime.inc').read_text())
        # Both the partial and complete publication exits freeze metadata first.
        head = magic[:magic.index('#if RAW_DMA_TAIL_WAIT')]
        self.assertEqual(head.count('raw_controls_metadata_freeze((void *)'), 2)
        self.assertLess(head.rindex('raw_controls_metadata_freeze((void *)'), head.index('*available=MAGIC_SLOTS_PADDED_BYTES'))
        self.assertIn('HAL_GetTick()-began>3000U', magic)
        ast = (HERE / 'sensor_autostop.inc').read_text()
        self.assertIn('now-capture_stop_started)>AST[31]', ast)


class ControlsRuntimeTests(unittest.TestCase):
    def test_actual_record_guard_applied_checks_and_snapshot_immutability(self):
        header = (ROOT / 'firmware/usb-ptp/capture_controls.h').read_text()
        source = (HERE / 'knob_capture.inc').read_text()
        source = source.replace('#define KNOB_LATE __attribute__((section(".raw_late_text"),noinline,noclone))', '#define KNOB_LATE')
        source = source.replace('(volatile uint32_t *)0x343F4000U', 'early_status')
        harness = r'''
#include <stdio.h>
#include <string.h>
#include "capture_controls.h"
static capture_controls_t controls;
static uint32_t early_status[32];
#undef CAPTURE_CONTROLS
#define CAPTURE_CONTROLS (&controls)
#define MAGIC_SLOTS_METADATA_BYTES 152U
#define __DSB() ((void)0)
static unsigned sensor, read_count, fail_read;
static uint16_t addresses[4], actual_frame,actual_margin,actual_digital;
static uint8_t actual_gain;
static int rd16(void *ctx,uint16_t reg,uint16_t *out) {
 (void)ctx;addresses[read_count++]=reg;if(fail_read)return -99;
 *out=reg==0x0458?actual_frame:reg==0x0946?actual_margin:actual_digital;return 0;
}
static int rd8(void *ctx,uint16_t reg,uint8_t *out) {
 (void)ctx;addresses[read_count++]=reg;if(fail_read)return -99;*out=actual_gain;return 0;
}
SOURCE
#define CHECK(x) do {if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);return 1;}}while(0)
static void crc(void){controls.crc32=capture_controls_crc(&controls);}
static void setup(unsigned us,unsigned asa,unsigned gain) {
 memset(&controls,0,sizeof controls);controls.magic=CAPTURE_CONTROLS_MAGIC;
 controls.schema=1;controls.bytes=128;controls.state=CC_SENSOR_CONFIGURED;
 controls.flags=CC_REQUIRED_FLAGS|CC_F_SENSOR_CONFIGURED;controls.requested_us=us;
 controls.line_length=1280;controls.vt_hz=160800000;controls.asa=asa;controls.margin=68;
 unsigned coarse=(unsigned)(((uint64_t)us*160800000U+1279999999U)/1280000000U);
 controls.frame_length=coarse+2000U<4336U?4336U:coarse+2000U;
 controls.manual[0]=2;controls.manual[1]=gain;controls.manual[2]=coarse;controls.manual[3]=coarse>>8;
 for(unsigned i=4;i<12;i+=2)controls.manual[i+1]=1;
 actual_frame=controls.frame_length;actual_margin=68;actual_gain=gain;actual_digital=256;
 read_count=fail_read=0;knob_metadata_frozen=0;crc();
}
int main(void) {
 uint32_t meta[38],frozen[38];
 for(unsigned n=0;n<4;n++) {
  const unsigned gains[]={0,16,24,28};setup(n==3?500000U:1000U+n*50000U,100U<<n,gains[n]);
  CHECK(knob_record_valid());memset(meta,0xA5,sizeof meta);
  CHECK(raw_controls_metadata_freeze(meta)==0);memcpy(frozen,meta,sizeof meta);
  CHECK(memcmp(meta,&controls,128)==0);for(unsigned i=32;i<38;i++)CHECK(meta[i]==0);
  unsigned coarse=controls.manual[2]|((unsigned)controls.manual[3]<<8);
  CHECK(knob_verify_applied(1280,coarse)==0);CHECK(knob_record_valid());
  CHECK(read_count==4&&addresses[0]==0x0458&&addresses[1]==0x0946&&addresses[2]==0x0068&&addresses[3]==0x006A);
  CHECK(controls.state==CC_APPLIED_VERIFIED&&controls.applied_gain==gains[n]&&controls.applied_digital==256);
  CHECK(raw_controls_metadata_freeze(meta)==0);CHECK(memcmp(meta,frozen,sizeof meta)==0);
  CHECK(((capture_controls_t *)meta)->state==CC_SENSOR_CONFIGURED);
  if(n==3)CHECK(coarse==62813U&&controls.frame_length==64813U);
 }
 setup(500000,800,28);controls.requested_us=500001;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.line_length=1236;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.manual[1]=27;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.manual[5]=2;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.frame_length=65536;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.margin=1994;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.flags|=0x80;crc();CHECK(!knob_record_valid());
 setup(500000,800,28);controls.crc32^=1;CHECK(raw_controls_metadata_freeze(meta)!=0);
 for(unsigned n=0;n<4;n++) {
  setup(500000,800,28);if(n==0)actual_gain=0;if(n==1)actual_frame--;if(n==2)actual_margin++;if(n==3)actual_digital=257;
  CHECK(knob_verify_applied(1280,62813)!=0);CHECK(controls.state==CC_SENSOR_CONFIGURED);
 }
 setup(500000,800,28);fail_read=1;CHECK(knob_verify_applied(1280,62813)==-99);
 setup(500000,800,28);CHECK(knob_verify_applied(1280,62812)!=0&&read_count==0);
 puts("controls bounds/readback/immutable metadata passed");return 0;
}
'''.replace('SOURCE', source)
        compiler = shutil.which('clang') or shutil.which('gcc')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='capture-controls-') as tmp:
            tmp = Path(tmp)
            (tmp / 'capture_controls.h').write_text(header)
            (tmp / 'test.c').write_text(harness)
            subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', str(tmp/'test.c'), '-o', str(tmp/'test.exe')], check=True)
            subprocess.run([str(tmp/'test.exe')], check=True, capture_output=True)


if __name__ == '__main__': unittest.main()
