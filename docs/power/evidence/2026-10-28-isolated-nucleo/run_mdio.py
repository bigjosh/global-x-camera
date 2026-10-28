import importlib.util,json,time
from pathlib import Path
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('isolated_mdio',HERE/'mdio/v2/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
b,p=m.prepare_from_refused_v3(HERE/'mdio03',HERE/'cpu400a/operation/prepared.json',HERE/'cpu400a/operation/proof.json')
m.launch(b,p);time.sleep(.6)
r=m.observe(b,p)
print(json.dumps({k:r[k] for k in ('completed_and_restored','phy_found','matches','pad_levels_expected','pc','cfsr','hfsr')},indent=2))
print(json.dumps({k:r['proof'][k] for k in ('state','error','cleanup','scan_count','bit_count','clock_low_fail','clock_high_fail')},indent=2))
if r['completed_and_restored']:
    b.call('-halt','-coreReg','PC=0x343003AA','XPSR=0x01000000','-run',success='Core run')
    (b.output/'return-to-v3-park.json').write_text(json.dumps({'returned_to_v3_park_requested':True,'pc':'0x343003AA','reason':'Completed read-only MDIO probe with exact restored GPIO/clocks; v3 proof/code unchanged. Next operation requires its own fresh gate.'},indent=2))
