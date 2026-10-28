"""After all image checks, leave the installed normal firmware after a cold cycle."""
from pathlib import Path
import importlib.util,json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def run(name,*args):
    with (H/(name+'.log')).open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=f,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
v=json.loads((H/'cold-images-readback/summary.json').read_text());assert v['passed'] and len(v['slots'])==6
run('next-slot-check',R/'tmp/bringup/sd-fourbit-20261024/magic_readback.py','read-headers',
    '--build',H/'ram-candidate','--prior',v['prior'],'--scr-proof',H/'candidate-reobserved/verified.json',
    '--slot',130,'--out',H/'next-slot-check','--execute')
nextslot=json.loads((H/'next-slot-check/summary.json').read_text())
assert nextslot['passed'] and nextslot['slots'][0]['header']['state']=='FREE'
prior=Path(nextslot['prior']);p=json.loads(prior.read_text())
bmod=load('raw_finish_bench',R/'firmware/capture-raw/bench.py')
m,code=bmod.checked_build(H/'ram-candidate',p['binary_sha256'])
b=bmod.sd.Bench(H/'final-idle');bmod.terminal_gate(b,H/'ram-candidate',m,code,p,'fresh')
run('final-recovery',R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',H/'final-recovery')
run('final-park',R/'firmware/capture-timing/recovery_gpio/check_park.py',
    '--build',H/'flash-candidate/staged','--out',H/'final-park')
run('final-cold',H/'cold_logger.py','--out',H/'final-cold/trace','--cycle',
    '--park-proof',H/'final-park/result.json','--expected-prefix-sha',
    '2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344')
a=load('final_analysis',H/'analysis/analyze_cycles.py')
q=a.analyze(dict(run='final-cold',group='final-restoration',trace=str(H/'final-cold/trace'),
    evidence=dict(build=str(H/'flash-candidate'),not_in_three_run_comparison=True)))
assert q['unique_marker_train'] and q['marker_precedence_pass'] and 6<q['low_plateau_100ms']['current_mean_mA']<12
js=json.loads((H/'final-cold/trace/result.json').read_text());assert js['success'] and not js['cleanup_errors']
result=dict(normal_flash_restored=True,installed_build=str(H/'flash-candidate'),
    sector_sha256='a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645',
    final_power='enabled; JS restored starting range128 and stream/EXTIO settings',
    current_state='Normal cold boot then low-current plateau with all ten phase markers; not RAM helper',
    low_plateau=q['low_plateau_100ms'],cycle_ms=q['whole_cycle_raw_unqualified']['duration_ms'],
    expected_extra_slot=130,extra_slot_was_free_before_boot=True,extra_slot_reread=False,
    current_cycle_standby_flag_reread=False,prior_measured_candidate3_standby_flags='SBF1/PDDS1/STOPF0; generic trial_entry_proven false',
    six_measured_cold_images_passed=True,original_ram_equality_slots=[122,126],
    no_card_erase=True,serial='COM8 closed/BREAK released after final recovery; no further serial stimulus',
    logger_closed_utc=js['utc'],measurement_limits=q['qualification'])
(H/'final-state.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
