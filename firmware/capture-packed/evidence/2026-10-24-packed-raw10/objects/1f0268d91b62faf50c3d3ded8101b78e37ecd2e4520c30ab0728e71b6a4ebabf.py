"""Offline RAM-only RAW10 passthrough experiment; never access instruments."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from build_raw10 import checked_manifest, compile_sources, replace

BASE = ROOT / 'tmp/bringup/sd-normal-20261024/v66c-normal-standby'
BASE_RECEIVER = '20c5ddaef2e1bf6b78d272e3ee23f891ead2d41f88e922538962e218987f4e99'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--mode', required=True, choices=('native10', 'opaque8'))
    p.add_argument('--pattern', required=True, choices=('scene', 'diagonal'))
    a = p.parse_args()
    mode = int(a.mode == 'opaque8')
    pattern = int(a.pattern == 'diagonal')
    rdir, pdir = BASE / 'receiver', BASE / 'staged'
    m = checked_manifest(rdir)
    if sha((rdir / 'capture.bin').read_bytes()) != BASE_RECEIVER:
        raise ValueError('Unexpected frozen v66c receiver')
    pm = checked_manifest(pdir)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    excluded = {'sleep.c', 'save_loader.c', 'module-save.bin', 'module-manifest.json',
                'save_module_config.h', 'late_config.h'}
    compiled = []
    for rel, digest in m['sources'].items():
        src = ROOT / rel
        if src.name in excluded:
            continue
        target = out / src.name
        data = src.read_bytes()
        if src.name == 'capture.c':
            text = data.decode('utf-8').replace('\r\n', '\n')
            text = replace(text, '#define BYTES (WIDTH * HEIGHT * 2U)',
                           '#define BYTES (WIDTH * HEIGHT * (RAW_MODE ? 5U : 8U) / 4U)\n#define ALLOCATION_BYTES (WIDTH * HEIGHT * 2U)\n#include "experiment.h"')
            text = replace(text, 'uint8_t g_frame[BYTES];', 'uint8_t g_frame[ALLOCATION_BYTES];')
            text = replace(text, 'DCMIPP_PIPE0,BYTES/4U)', 'DCMIPP_PIPE0,ALLOCATION_BYTES/4U)')
            text = replace(text, '  event(21);', '''  volatile uint32_t *allocation_guard=(volatile uint32_t *)(0x34000000U+ALLOCATION_BYTES);
  for(unsigned i=0;i<8;++i) allocation_guard[i]=0xA15A1000U+i;
  __DSB();
  event(21);''')
            text = replace(text, '.DataTypeIDA=DCMIPP_DT_RAW10',
                           '.DataTypeIDA=(RAW_MODE ? 0x30U : DCMIPP_DT_RAW10)')
            text = replace(text, 'DCMIPP_VIRTUAL_CHANNEL0,DCMIPP_CSI_DT_BPP10)',
                           'DCMIPP_VIRTUAL_CHANNEL0,(RAW_MODE ? DCMIPP_CSI_DT_BPP8 : DCMIPP_CSI_DT_BPP10))')
            text = replace(text, 'int main(void)\n{\n  fast_init();',
                           'int main(void)\n{\n  raw_experiment_begin();\n  fast_init();')
            text = replace(text, 'if(raw_bits!=10U || raw_dt!=0x2BU)',
                           'if(raw_bits!=10U || raw_dt!=(RAW_MODE ? 0x30U : 0x2BU))')
            text = replace(text, '  CPROF[CP_FLAGS]|=CP_F_RAW10;', '''  volatile uint32_t *allocation_guard=(volatile uint32_t *)(0x34000000U+ALLOCATION_BYTES);
  raw10[10]=0U;
  for(unsigned i=0;i<8;++i) if(allocation_guard[i]!=(0xA15A1000U+i)) raw10[10]|=1U<<i;
  uint16_t pattern_readback=0;
  uint8_t duster_readback=0,dark_readback=0;
  check(0x86,rd16(&sensor,0x0400,&pattern_readback));
  check(0x87,rd8(&sensor,0x0318,&duster_readback));
  check(0x88,rd8(&sensor,0x0340,&dark_readback));
  raw10[11]=pattern_readback; raw10[12]=duster_readback; raw10[13]=dark_readback;
  if(raw10[10] || pattern_readback!=(RAW_PATTERN?0x0121U:0U) ||
     (RAW_PATTERN && (duster_readback || dark_readback!=2U))) fail(0x89,-1);
  CPROF[CP_FLAGS]|=CP_F_RAW10;''')
            # The existing cache-free receiver writes the full frame. Leave its
            # transfer/STOP/error guards intact; replace only the SD handoff.
            begin = text.index('  extern int photo_save_load(void);')
            text = text[:begin] + '  event(40);\n  raw_experiment_complete();\n}\n'
            target.write_text(text, encoding='utf-8', newline='\n')
        else:
            target.write_bytes(data)
        if target.suffix.lower() in ('.c', '.s'):
            compiled.append(target)
    sensor = (pdir / 'stage1_sensor.c').read_text()
    sensor = replace(sensor, 'write_value(0x030F,0x2B,1)',
                     'write_value(0x030F,RAW_MODE ? 0x30U : 0x2BU,1)')
    sensor = replace(sensor, 'TRY(34,write_value(0x0400,0,2));',
        '''/* ST VD6G/Linux driver test-pattern sequence; UM2602 table29. */
    if(RAW_PATTERN) {
        TRY(38,write_value(0x0318,0,1));
        TRY(39,write_value(0x0340,2,1));
    }
    TRY(34,write_value(0x0400,RAW_PATTERN ? 0x0121U : 0U,2));''')
    (out / 'stage1_sensor.c').write_text(sensor, encoding='utf-8', newline='\n')
    compiled.append(out / 'stage1_sensor.c')
    for name in ('experiment.c', 'experiment.h'):
        shutil.copyfile(HERE / name, out / name)
    compiled.append(out / 'experiment.c')
    flags = [f for f in m['compile_flags'] if f != '-I' + str(rdir)]
    flags.insert(0, '-I' + str(out))
    flags += [f'-DRAW_MODE={mode}', f'-DRAW_PATTERN={pattern}', '-DSTAGE1_SENSOR_TRIM=1']
    code, size = compile_sources(out, compiled, flags, out / 'capture.ld', 'capture', libc=True)
    symbols = (out / 'symbols.txt').read_text()
    def symbol(name):
        match = re.search(r'^([0-9a-f]+) [A-Za-z] ' + name + '$', symbols, re.M)
        if not match:
            raise ValueError('Missing symbol ' + name)
        return int(match[1], 16)
    park = symbol('raw_experiment_park')
    reject = symbol('raw_experiment_reject_park')
    assert code[park - 0x34300000:park - 0x34300000 + 2] == b'\xfe\xe7'
    assert code[reject - 0x34300000:reject - 0x34300000 + 2] == b'\xfe\xe7'
    if re.search(r' [Tt] (photo_save_load|module_run|SDMMC2_IRQHandler|HAL_SD_\w+|BSP_XSPI_NOR_\w+)\b', symbols):
        raise ValueError('Unexpected storage code linked')
    sp, entry = struct.unpack_from('<II', code)
    assert sp == 0x343B0000 and 0x34300000 <= entry - 1 < 0x34300000 + len(code)
    assert len(code) < 0x20000
    manifest = dict(schema=1, mode=mode, mode_name=a.mode, pattern=pattern,
        pattern_name=a.pattern, load=0x34300000, entry=entry, stack=sp,
        park=park, reject_park=reject, failure_park=symbol('fast_failure_idle'),
        request=0x343FD000, proof=0x343FD100, proof_words=40,
        bss_start=symbol('_sbss'), bss_end=symbol('_ebss'),
        data_start=symbol('_sdata'), data_end=symbol('_edata'),
        system_core_clock=symbol('SystemCoreClock'),
        immutable_bytes=symbol('_sdata')-0x34300000,
        stack_floor=symbol('_sstack'), allocation_bytes=1120*1364*2,
        allocation_guard=0x34000000+1120*1364*2, guard_bytes=32,
        owned_context_cleanup=dict(proof=0x343F6000+14*4,words=5,
            fields=['control','fpccr','cpacr','msplim','msp'],
            nonreturning=True,restored_control=0,restored_cpacr=0),
        frame=0x34000000, width=1120, height=1364,
        frame_bytes=1120*1364*(5 if mode else 8)//4,
        binary_bytes=len(code), binary_sha256=sha(code), flags=flags, size=size,
        base_receiver_sha256=BASE_RECEIVER, base_prefix_sha256=pm['stage1_raw_sha256'],
        sd_commands=False, nor_commands=False, sensor_reset=True,
        cold_start_measurement=False, installed_recovery_unchanged=True,
        source_hashes={f.name:sha(f.read_bytes()) for f in out.iterdir()
                       if f.suffix.lower() in ('.c', '.h', '.s', '.ld')},
        hardware_status='untested')
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
