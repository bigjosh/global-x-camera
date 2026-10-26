"""One root-owned exact NOR installation; stop immediately on any failed gate."""
import hashlib,json,subprocess,sys
from pathlib import Path

root=Path.cwd()
old,new,prior_build,prior,out=map(Path,sys.argv[1:6])
out.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
for b in (old,new):
    m=read(b/'manifest.json');s=read(b/'staged/manifest.json')
    assert m['flash'] and sha(b/'capture.bin')==m['binary_sha256']==s['stage2_full_sha256']
    assert sha(b/'staged/capture_sector_0.bin')==s['program_sha256']
assert read(new/'manifest.json')['sd_clock_hz']==25000000
def run(label,*args):
    print(label,flush=True)
    with (out/(label+'.log')).open('x') as f:
        subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
run('idle',root/'tmp/bringup/sd-early-clock-20261026/fresh_idle.py',prior_build,prior,out/'idle')
run('recovery',root/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',out/'recovery')
run('park',root/'firmware/capture-timing/recovery_gpio/check_park.py','--build',old/'staged','--out',out/'park')
nr=root/'tmp/bringup/cycle-trace-20261025/nor_read.py'
guard=root/'tmp/bringup/rom-nor-maintenance-readonly-20261017/following-sector-before.bin'
run('nor-before',nr,out/'nor-before',old/'staged/capture_sector_0.bin',0)
run('following-before',nr,out/'following-before',guard,65536)
nb=root/'firmware/boot-timing/nor_bench.py'
helper=root/'tmp/bringup/rom-nor-programmer-v2-20261024'
run('info',nb,'info','--build',helper,'--out',out/'info','--sequence','261001')
run('write',nb,'write','--build',helper,'--out',out/'write','--sequence','261002',
    '--current',old/'staged/capture_sector_0.bin','--desired',new/'staged/capture_sector_0.bin')
run('completion-diagnostic',root/'tmp/bringup/raw-slots-20261024/read_nor_diagnostic.py',out/'completion-diagnostic','261002')
run('nor-after',nr,out/'nor-after',new/'staged/capture_sector_0.bin',0)
run('following-after',nr,out/'following-after',guard,65536)
(out/'complete.json').write_text(json.dumps(dict(passed=True,old_sector_sha256=sha(old/'staged/capture_sector_0.bin'),
    new_sector_sha256=sha(new/'staged/capture_sector_0.bin'),independent_full_readback=True,following4096_unchanged=True),indent=2))
print('Installation and independent physical readback passed',flush=True)
