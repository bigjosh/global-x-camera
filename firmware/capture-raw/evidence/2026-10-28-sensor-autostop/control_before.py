"""Fresh unchanged-normal cold control, then exact UART recovery park."""
from pathlib import Path
import importlib.util,json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
normal=R/'tmp/bringup/ethernet-normal-20261028/flash-candidate'
def run(label,*args):
    with (H/(label+'.log')).open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
def park(label):
    run(label+'-recovery',R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',H/(label+'-recovery'))
    run(label+'-park',R/'firmware/capture-timing/recovery_gpio/check_park.py','--build',normal/'staged','--out',H/(label+'-park'))
    return H/(label+'-park/result.json')
p=park('initial')
run('control-before',R/'tmp/bringup/ethernet-normal-20261028/cold_logger.py','--out',H/'control-before/trace',
    '--cycle','--park-proof',p,'--expected-prefix-sha','2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344')
src=R/'tmp/bringup/ethernet-normal-20261028/analysis/analyze_cycles.py'
s=importlib.util.spec_from_file_location('autostop_normal_control',src);a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
a.HERE=H/'analysis';a.HERE.mkdir(exist_ok=True);a.CAMPAIGN=H
q=a.analyze(dict(run='control-before',group='normal',trace=str(H/'control-before/trace'),evidence=dict(build=str(normal))))
assert q['unique_marker_train'] and q['marker_precedence_pass'] and 6<q['low_plateau_100ms']['current_mean_mA']<12
print('NORMAL_CONTROL_VERIFIED',flush=True)
park('control-before')
print('NORMAL_PARK_VERIFIED',flush=True)
