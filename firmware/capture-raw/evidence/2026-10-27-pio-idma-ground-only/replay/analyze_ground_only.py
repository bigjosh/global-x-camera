"""Offline four-condition read comparison, reusing sealed analysis logic."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=next(p for p in Path(__file__).resolve().parents
    if (p/'NOTES.md').is_file() and (p/'firmware/capture-raw').is_dir())
CLK_ONLY=ROOT/'firmware/capture-raw/evidence/2026-10-27-pio-idma-clk-only'
CAMPAIGN=ROOT/'tmp/bringup/sd-read-pio-dma-20261027/ground-only-control'

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def binding(path): return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
def require(ok,message):
    if not ok: raise ValueError(message)

def analyze(campaign,allow_partial=False):
    index=read(CLK_ONLY/'archive-index.json')
    require(index['sealed'] is True,'CLK-only archive must remain sealed')
    script=CLK_ONLY/'replay/analyze_clk_only.py'
    require(sha(script)==index['files']['replay/analyze_clk_only.py']['sha256'],
        'Sealed CLK-only analyzer identity differs')
    spec=importlib.util.spec_from_file_location('sealed_clk_only_analyzer',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.analyze(campaign,allow_partial)
    current=report.pop('clk_only25_outcomes')
    previous_path=CLK_ONLY/'addenda/clk-only/evidence/analysis-complete.json'
    previous=read(previous_path)
    require(previous['all_six_complete'] is True,'Preceding CLK-only comparison is incomplete')
    report.update(schema=3,
        condition=dict(user_confirmed_probes={'CH0_CMD':'removed','CH1_CLK':'removed','ground':'connected'},
            change_from_clk_only='Only CLK signal probe disconnected; analyzer ground retained',
            clk_connection='Direct jumper; NO series resistor throughout all compared tests',
            other_wiring='User reported unchanged; no independent geometry inspection',
            camera='Held in reset by the same diagnostic firmware',
            binaries='Exact same original PIO25/IDMA25 RAM executables'),
        clk_only_archive=dict(checksums=binding(CLK_ONLY/'SHA256SUMS'),
            index=binding(CLK_ONLY/'archive-index.json'),analyzer=binding(script),
            results=binding(previous_path)),
        clk_only25_outcomes=previous['clk_only25_outcomes'],ground_only25_outcomes=current,
        interpretation_limits=[
            'Matched CLK-only versus ground-only controls retain analyzer ground while changing the CLK signal probe connection.',
            'Ground connection in the original probe-free condition was not independently established; the explicit ground-only condition resolves that ambiguity for this comparison.',
            'All trials read one known512-byte sector with the camera held reset; no full capture/write cycle is qualified.',
            'Failed cleanup and failed CRC records remain failures; explicit authorized recovery never converts them into successful-idle proofs.',
            'A probe-dependent reversal does not itself prove reflection, voltage, edge-count or analog timing mechanisms.',
            'Passing isolated CLK-only reads does not rule out CMD-probe effects during full capture/write operation.',
            'Earlier archives and their wiring-correction addendum remain sealed and unchanged.'])
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
        'initial_probe_free25_outcomes','joint_probe25_outcomes','clk_only25_outcomes',
        'ground_only25_outcomes')},indent=2))

if __name__=='__main__': main()
