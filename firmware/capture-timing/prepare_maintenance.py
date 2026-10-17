"""Abandon a completed capture into a checked integer-only maintenance context.

RAM/core/cache operations only; no reset, power control, or NOR commands. The
immutable cache helper must be unchanged at its reserved address. This does not
return to the application. Run the frozen NOR helper's INFO before any WRITE.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
from bench import REPO, sha

CACHE = REPO / 'tmp/bringup/capture-maintenance-cache-20261017/cache_prep.bin'
CACHE_SHA = 'e084dfd2aaedd80c26ffaaf7b51e161ac804edb053f54c9f4ce5a68609f54e9a'
CACHE_LOAD, CACHE_STATUS = 0x341A0000, 0x341A0400

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boot-timing'))
from nor_bench import Bench


def registers(text):
    return {name: int(value, 16) for name, value in
            re.findall(r'^(PC|XPSR|CONTROL|PRIMASK|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)', text, re.M)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--layout', choices=('raw8', 'raw10'), default='raw8')
    a = p.parse_args()
    cache_path, cache_sha = CACHE, CACHE_SHA
    cache_load, cache_status = CACHE_LOAD, CACHE_STATUS
    trace_address = 0x341F0000
    if a.layout == 'raw10':
        trace_address = 0x343F0000
        cache_path = REPO / 'tmp/bringup/capture-maintenance-cache-raw10-20261017/cache_prep.bin'
        cache_sha = '59427aa1c107a24378a35c3f85eb7f7d4fc1209115a319f05d3322646f62943d'
        cache_load, cache_status = 0x343C0000, 0x343C0400
    b = Bench(a.out)
    trace = struct.unpack('<64I', b.upload(trace_address, 256, 'capture-trace.bin'))
    if trace[0] != 0x43545031 or trace[1] != 40:
        raise ValueError('Require a completed capture; no interruption of active operations')
    context = registers(b.call('-halt', '-coreReg'))
    if (context.get('XPSR', 511) & 511 or context.get('CONTROL', 3) & ~0xC
            or context.get('FAULTMASK') != 0):
        raise ValueError('Require idle privileged MSP Thread mode, FP ownership flags only')
    fpccr, = struct.unpack('<I', b.upload(0xE000EF34, 4, 'fpccr.bin'))
    if fpccr & 1:
        raise ValueError('Lazy FP save active; do not discard this context')
    code = cache_path.read_bytes()
    if sha(code) != cache_sha:
        raise ValueError('Frozen cache helper hash mismatch')
    present = b.upload(cache_load, len(code), 'cache-before.bin')
    if present != code and any(present):
        raise ValueError('RAM helper differs; fresh cold-boot procedure required')
    clear = b.output / 'clear-cache.bin'
    clear.write_bytes(bytes(20))
    b.call('-halt', '-w', clear, hex(cache_status), '-v',
           '-w', cache_path, hex(cache_load), '-v', '-coreReg',
           'PRIMASK=1', f'PC={hex(cache_load + 1)}', 'XPSR=0x01000000', '-run', success='Core run')
    status = struct.unpack('<5I', b.upload(cache_status, 20, 'cache-after.bin'))
    if status[0] != 0x43414348 or status[3] != 0 or status[4] & 0x30000:
        raise RuntimeError('Cache helper did not complete as expected')
    parked = registers(b.call('-halt', '-coreReg'))
    if parked.get('PC') not in (cache_load + 0x72, cache_load + 0x74) or parked.get('PRIMASK') != 1:
        raise RuntimeError('Cache helper not in its IRQ-masked idle loop')
    b.call('-coreReg', 'CONTROL=0', 'PRIMASK=1')
    final = registers(b.call('-coreReg'))
    if final.get('CONTROL') != 0 or final.get('PRIMASK') != 1 or final.get('FAULTMASK') != 0 or final.get('XPSR', 511) & 511:
        raise RuntimeError('Core context did not read back as requested')
    result = dict(initial=context, fpccr=fpccr, cache_status=status, final=final,
                  flash_commands_sent=False, application_abandoned=True, layout=a.layout,
                  cache_helper_sha256=cache_sha)
    (b.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
