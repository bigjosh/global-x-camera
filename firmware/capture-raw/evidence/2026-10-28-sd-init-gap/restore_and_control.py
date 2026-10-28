"""After image checks, restore exact normal NOR and record a final cold control."""
from pathlib import Path
import json, subprocess, sys
H=Path(__file__).resolve().parent;R=H.parents[2]
sys.path.insert(0,str(H/'analysis'))
from analyze_gap import analyze
normal=R/'tmp/bringup/ethernet-normal-20261028/flash-candidate'
def run(name,*args):
    with (H/(name+'.log')).open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=f,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
v=json.loads((H/'cold-images-readback/summary.json').read_text())
assert v['passed'] and [s['slot'] for s in v['slots']]==[133,134]
run('next-slot-check',R/'tmp/bringup/sd-fourbit-20261024/magic_readback.py','read-headers',
    '--build',H/'design/ram-gap','--prior',v['prior'],'--scr-proof',H/'ram-gap01/capture/verified.json',
    '--slot',135,'--out',H/'next-slot-check','--execute')
nextslot=json.loads((H/'next-slot-check/summary.json').read_text())
assert nextslot['passed'] and nextslot['slots'][0]['header']['state']=='FREE'
run('before-restore',H/'park_from_idle.py',H/'design/ram-gap',nextslot['prior'],
    H/'design/flash-gap/staged',H/'before-restore')
run('restore-normal',R/'tmp/bringup/error-blinks-20261026/install.py',H/'design/flash-gap',normal,H/'restore-normal')
run('restored-recovery',R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',H/'restored-recovery')
run('restored-park',R/'firmware/capture-timing/recovery_gpio/check_park.py','--build',normal/'staged','--out',H/'restored-park')
run('control-after',R/'tmp/bringup/ethernet-normal-20261028/cold_logger.py','--out',H/'control-after/trace','--cycle',
    '--park-proof',H/'restored-park/result.json','--expected-prefix-sha',
    '2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344')
q=analyze(dict(run='control-after',group='normal',trace=str(H/'control-after/trace'),evidence=dict(build=str(normal))))
assert q['unique_marker_train'] and q['marker_precedence_pass'] and 6<q['low_plateau_100ms']['current_mean_mA']<12
js=json.loads((H/'control-after/trace/result.json').read_text());assert js['success'] and not js['cleanup_errors']
result=dict(completed=True,normal_restored=True,installed_build=str(normal),
    sector_sha256='a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645',
    final_power='enabled; JS restored range128 and stream/EXTIO settings',
    current_state='Normal cold boot then low-current plateau with all ten phase markers; not RAM helper',
    low_plateau=q['low_plateau_100ms'],cycle_ms=q['whole_cycle_raw_unqualified']['duration_ms'],
    expected_extra_slot=135,extra_slot_was_free_before_boot=True,extra_slot_reread=False,
    current_cycle_standby_flag_reread=False,prior_gap2_standby_flags='SBF1/PDDS1/STOPF0; generic trial_entry_proven false',
    cold_image_slots_verified=[133,134],original_ram_equality_slots=[132],
    no_card_erase=True,serial='COM8 closed/BREAK released; no further serial stimulus',
    logger_closed_utc=js['utc'],measurement_limits=q['qualification'])
(H/'final-state.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
