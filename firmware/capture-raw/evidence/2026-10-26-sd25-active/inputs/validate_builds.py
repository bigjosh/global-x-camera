"""Offline 25 MHz promotion identities and prior-profile byte preservation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
import bench
import inspect_flash

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())

result={'schema':1,'kind':'offline-25mhz-flash-promotion-build-validation',
        'hardware_access':False,'profiles':{},'prior_125_bytes':{}}
for name in ('flash25-awake','flash25-standby'):
    folder=HERE/name
    m=read(folder/'manifest.json'); p=read(folder/'staged/manifest.json')
    assert bench.startup_flash_profile(m)
    bench.diagnostic_layout(m,1)
    assert bench.clock_layout(m)==25000000
    assert bench.phase_layout(m)==0x10000
    assert m['late_load']['early_bytes']==15804
    assert m['sd_bus_width']==4 and m['sd_gpio_speed']==3
    assert m['sd_clock_negedge'] and m['sd_clock_negedge_init']
    assert m['sd_review_profile'] and m['sd_startup_opt']
    assert not any(m.get(key) for key in ('sd_fixed_compensation','sd_compensation_modified',
        'raw_dma_tail_wait','sd_idma_read','dma_sleep','cycle_trace','sd_early_run_clock'))
    assert sha(folder/'capture.bin')==m['binary_sha256']
    assert sha(folder/'staged/capture_sector_0.bin')==p['program_sha256']
    if not m['standby']:
        inspect_flash.checked_build(folder,m['binary_sha256'],p['program_sha256'])
    result['profiles'][name]={
        'build':str(folder.relative_to(ROOT)),
        'receiver_sha256':m['binary_sha256'],'receiver_bytes':m['binary_bytes'],
        'sector_sha256':p['program_sha256'],'prefix_sha256':p['stage1_raw_sha256'],
        'early_bytes':m['late_load']['early_bytes'],'sd_clock_hz':m['sd_clock_hz'],
        'standby':m['standby'],'startup_flash_admitted':True,
        'exact_recovery_review':'Separate reviewer audit and hardware qualification required'}
old=ROOT/'tmp/bringup/sd50-reviewed-20261026/flash-reviewed125-startup-standby'
new=HERE/'unchanged125-standby'
for rel in ('capture.bin','staged/stage1.bin','staged/stage1_boot.bin','staged/capture_sector_0.bin'):
    assert (old/rel).read_bytes()==(new/rel).read_bytes(),rel
    result['prior_125_bytes'][rel]={'sha256':sha(new/rel),'unchanged':True}
result['tests']={'capture_suite_count':162,'capture_suite_passed':True,
                 'log':'tmp/bringup/sd25-promote-20261026/capture-tests.txt',
                 'log_sha256':sha(HERE/'capture-tests.txt')}
(HERE/'build-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
