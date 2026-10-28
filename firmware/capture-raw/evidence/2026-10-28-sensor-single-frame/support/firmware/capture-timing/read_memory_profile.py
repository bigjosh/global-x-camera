"""Bounded AP1 register reads for the proposed native RAW10 SRAM layout."""
import argparse
import json
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'boot-timing'))
from nor_bench import Bench

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
b = Bench(a.out)
registers = {'rcc_cfgr1': (0x56028020, 4), 'rcc_ic11cfgr': (0x560280ec, 4),
             'rcc_enables': (0x56028240, 64), 'ramcfg3_cr': (0x52023100, 4),
             'ramcfg4_cr': (0x52023180, 4), 'ramcfg5_cr': (0x52023200, 4),
             'ramcfg6_cr': (0x52023280, 4), 'npu_icncr': (0x56008078, 4),
             'cacheaxi_cr_sr': (0x580dfc00, 8)}
result = {}
for name, (address, length) in registers.items():
    data = b.upload(address, length, name + '.bin')
    result[name] = dict(address=hex(address), words=[hex(x[0]) for x in struct.iter_unpack('<I', data)])
(b.output / 'registers.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
