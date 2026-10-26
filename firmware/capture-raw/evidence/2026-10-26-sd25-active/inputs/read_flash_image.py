"""One post-cold-boot UART recovery and full25MHz image retrieval."""
import json,subprocess,sys,time
from pathlib import Path
root=Path.cwd();base=Path(__file__).resolve().parent
mode=sys.argv[1];assert mode in ('awake','standby')
build=base/('flash25-'+mode);ram=root/'tmp/bringup/sd25-stress-20261026/ram25-scene'
m=json.loads((ram/'manifest.json').read_text())
if mode=='awake':
    p=json.loads((base/'awake-inspect/verified.json').read_text())
    assert p['passed'] and p['proof']['result']==0 and p['proof']['media_idle']==1
    assert not any(p['proof'][k] for k in ('initialized','controller_owned','cleanup_error'))
    assert time.time()-(base/'awake-inspect/verified.json').stat().st_mtime<600
    slot=p['proof']['slot']
else:
    slot=int(sys.argv[2])
    p=json.loads((base/'standby-cold/boot-proof.json').read_text())
    assert p['cold_boot_confirmed'] and time.time()-(base/'standby-cold/boot-proof.json').stat().st_mtime<600
def run(label,*args):
    print(label,flush=True)
    with (base/(label+'.log')).open('x') as f:
        subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
run(mode+'-recover',root/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',base/(mode+'-recover'))
run(mode+'-park',root/'firmware/capture-timing/recovery_gpio/check_park.py','--build',build/'staged','--out',base/(mode+'-park'))
if mode=='standby':
    run('standby-flag',root/'firmware/capture-sd/low_power/read_standby_flag.py',
        '--build',build/'staged','--park-result',base/'standby-park/result.json','--out',base/'standby-flag')
run(mode+'-read-start',root/'firmware/capture-raw/bench.py','read','--build',ram,
    '--expected-sha',m['binary_sha256'],'--recovery-build',build/'staged',
    '--lba',slot*3730,'--count',1,'--out',base/(mode+'-read-start'),'--execute')
args=[root/'tmp/bringup/sd-fourbit-20261024/magic_readback.py','read-slots','--build',ram,
    '--prior',base/(mode+'-read-start/verified.json'),'--scr-proof',base/'awake-inspect/verified.json',
    '--slot',slot,'--out',base/(mode+'-readback'),'--execute']
if mode=='awake':args+=['--reference',base/'awake-inspect/frame.bin','--reference-kind','sensor-ram']
run(mode+'-readback',*args)
print(mode+' complete, slot '+str(slot),flush=True)
