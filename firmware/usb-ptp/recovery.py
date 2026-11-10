"""Exact live UART park verification for reviewed USB boot packages.

This sends no reset or stimulus. It reuses the existing recovery verifier,
including full live-prefix comparison, UART pulse evidence and core/XSPI
context checks. A new package must be independently reviewed and explicitly
pinned below before use; a self-consistent manifest is insufficient.
"""
import argparse, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
import nor_bench
nor_bench.CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'
APPROVED={
 # November9 PA2/A3 HOLD: independent prefix/layout/CRC review, 26 linked
 # package tests, 324 capture tests; original early UART block is byte-exact.
 # Exact candidate admission for installation/verification, not hardware proof.
 '852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084':
  dict(bytes=7160,sector='c822d2333ce265ded2ea420fd4c78e2a20e01c4b392b1decb99b80d9a040516d'),
 # Final cancellation cleanup gate; independently reproduced USB executable,
 # 24 linked package tests, original capture tail and UART guard unchanged.
 '4976a9e956095e3176ef4863b6c49225df271b231305e51069152baf731e4dd0':
  dict(bytes=7160,sector='dd69bc33981a35bebefaca4c1939b6334304a6ad72dcfb57492e539f0d1a0dad'),
 'bb61a7ad80e8fba5411d4c6233d8d6715ee922c850048429aca9451860cb425b':
  dict(bytes=7152,sector='9bf24f2542c0fb115bcf88dc2a895bda0513ccdd09d8c9b6bb90f2b8ee97437a'),
 # Corrected normal-boot I-cache disable/invalidate and capture-only restore;
 # 23 package tests, exact original UART bytes and complete capture tail.
 'd95d2bf715b36ede2c7a54a339183f38724a824b2811d66d65b580b014fe2110':
  dict(bytes=7160,sector='97067002c39d8a482a8e2c0dee4d71125cbacfab138cf4bab73ae1ac77dc9da8'),
 # November8 initial USB/capture-control packages: exact pinned capture tail,
 # B.W post-memory hook, unchanged original guard, linked context audits.
 '4ff9e4401c4cc7e1f1f74af506b6b9c158efdecb13b2fdf3308fc305ea6b4f51':
  dict(bytes=7060,sector='a270e87378a2450a83976b0762112006e9ad7fa55b7c4a069173d1dfbcb3950c'),
 '3c6cdd592b0f8b06c28f9c9c08209df2f93a19f79adf3e86c534cde3394badb5':
  dict(bytes=7052,sector='e124932c7a5550386abd00944a86942ecf3f0bbb721048014c0a465e678575e5'),
}

def main():
 p=argparse.ArgumentParser();p.add_argument('--package',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 s=importlib.util.spec_from_file_location('usb_early_guard',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py')
 guard=importlib.util.module_from_spec(s);s.loader.exec_module(guard)
 if a.package:
  m=json.loads((a.package/'manifest.json').read_text(encoding='utf-8'))
  pin=APPROVED.get(m['prefix_sha256'])
  if pin is None or pin['sector']!=m['sector0_sha256'] or pin['bytes']!=m['prefix_bytes']:
   raise ValueError('USB package has not received an exact offline recovery review')
  guard.APPROVED[m['prefix_sha256']]=dict(pin,park=0x3418078C,vcp=True)
  build=a.package/'recovery'
 else:
  build=ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/flash-standby-v1/staged'
 sys.argv=['guard','--build',str(build),'--out',str(a.out)]
 guard.main()

if __name__=='__main__':main()
