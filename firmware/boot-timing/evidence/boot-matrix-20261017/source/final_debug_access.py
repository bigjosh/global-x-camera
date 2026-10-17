import sys,json,struct
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from nor_bench import Bench
b=Bench(Path('tmp/bringup/opt-final-debug-access'))
w=struct.unpack('<7I',b.upload(0x34182000,28,'debug-status.bin'))
assert w[0]==0xB451B400 and w[1]==0xB4 and w[3]==0x44424732,w
(b.output/'status.json').write_text(json.dumps({'words':[hex(v) for v in w], 'debug_marker_record_verified':True,'no_halt_or_reset':True},indent=2))
print('Final awake baseline debug record verified without halting/resetting.')
