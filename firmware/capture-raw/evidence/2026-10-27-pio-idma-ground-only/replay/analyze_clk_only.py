"""Offline CLK-only comparison using the two sealed preceding archives.

No instruments or subprocesses. Reuses the sealed matched-attempt analyzer,
changes the condition label before emitting results, and binds both histories.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=next(p for p in Path(__file__).resolve().parents
    if (p/'NOTES.md').is_file() and (p/'firmware/capture-raw').is_dir())
JOINT=ROOT/'firmware/capture-raw/evidence/2026-10-27-pio-idma-probe-control'
CAMPAIGN=ROOT/'tmp/bringup/sd-read-pio-dma-20261027/clk-only-control'

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def binding(path): return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
def require(ok,message):
    if not ok: raise ValueError(message)

def analyze(campaign,allow_partial=False):
    index=read(JOINT/'archive-index.json')
    require(index['sealed'] is True,'Joint-probe archive must remain sealed')
    script=JOINT/'replay/analyze_probe_control.py'
    require(sha(script)==index['files']['replay/analyze_probe_control.py']['sha256'],
        'Sealed matched-attempt analyzer identity differs')
    spec=importlib.util.spec_from_file_location('sealed_probe_control_analyzer',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.analyze(campaign,allow_partial)
    current=report.pop('probe_control25_outcomes')
    prior_path=JOINT/'addenda/clk-cmd-probes/evidence/analysis-complete.json'
    prior=read(prior_path)
    require(prior['all_six_complete'] is True,'Joint comparison is incomplete')
    report.update(schema=2,
        condition=dict(user_confirmed_probes={'CH0_CMD':'removed','CH1':'CLK','ground':'connected'},
            change_from_joint='Only CMD probe disconnected, as confirmed by user',
            clk_connection='Direct jumper with NO series resistor, per subsequent user clarification covering all trials since CLK-slew testing began',
            other_wiring='User reported unchanged; no independent geometry inspection',
            camera='Held in reset by the same diagnostic firmware',
            binaries='Exact same original PIO25/IDMA25 RAM executables'),
        joint_probe_archive=dict(checksums=binding(JOINT/'SHA256SUMS'),
            index=binding(JOINT/'archive-index.json'),analyzer=binding(script),results=binding(prior_path)),
        joint_probe25_outcomes=prior['probe_control25_outcomes'],clk_only25_outcomes=current,
        wiring_correction='firmware/capture-raw/evidence/2026-10-27-sd-wiring-correction/README.md',
        interpretation_limits=[
            'All three conditions test one known512-byte sector, with camera held reset and no capture/write activity.',
            'Passing CLK-only reads does not rule out a CMD-probe effect during full capture/write cycles.',
            'CLK-probe loading and its ground/return connection are not isolated from each other.',
            'No full-image integrity, analog timing margin, reflection mechanism or formal compliance claim follows.',
            'Both earlier archives remain sealed and unchanged.'])
    report.pop('limitations',None)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,default=CAMPAIGN)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    report=analyze(args.campaign.resolve(),args.allow_partial)
    if args.out:
        with args.out.open('x',encoding='utf-8') as file:
            json.dump(report,file,indent=2,allow_nan=False);file.write('\n')
    print(json.dumps({key:report[key] for key in ('hardware_access','all_six_complete',
        'initial_probe_free25_outcomes','joint_probe25_outcomes','clk_only25_outcomes')},indent=2))

if __name__=='__main__': main()
