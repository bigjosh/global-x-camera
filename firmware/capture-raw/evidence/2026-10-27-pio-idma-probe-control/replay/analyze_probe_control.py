"""Offline paired probe-control summary using the sealed original analyzer.

Does not import the hardware runner or access instruments. The original
archive remains immutable, including its Python cache directories.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=next(p for p in Path(__file__).resolve().parents
    if (p/'NOTES.md').is_file() and (p/'firmware/capture-raw').is_dir())
ORIGINAL=ROOT/'firmware/capture-raw/evidence/2026-10-27-pio-idma-read'
CAMPAIGN=ROOT/'tmp/bringup/sd-read-pio-dma-20261027/probe-control'
EXPECTED=('pio25-01','idma25-01','idma25-02','pio25-02','pio25-03','idma25-03')

def require(ok,message):
    if not ok: raise ValueError(message)

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def binding(path): return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))

def analyze(campaign,allow_partial=False):
    original=read(ORIGINAL/'archive-index.json')
    require(original['sealed'] is True,'Original archive must remain sealed')
    script=ORIGINAL/'replay/analyze_reads.py'
    require(sha(script)==original['files']['replay/analyze_reads.py']['sha256'],
        'Sealed analyzer identity differs')
    spec=importlib.util.spec_from_file_location('sealed_read_analyzer',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    historical,historical_meta=module.historical_reference(ORIGINAL/'attempts')
    fresh,fresh_meta=module.successful_fresh_reference(ORIGINAL/'attempts')
    require(fresh is not None and fresh==historical,'Original reference differs')
    identity=historical_meta['card_identity']
    records=[]
    for name in EXPECTED:
        folder=campaign/name
        complete=(folder/'result.json').is_file() or (folder/'failed.json').is_file()
        if not complete:
            require(allow_partial,'Attempt is not complete: '+name)
            records.append(dict(name=name,outcome='pending_or_running'))
            continue
        item=module.analyze_attempt(folder,historical,fresh,identity)
        mode='idma' if name.startswith('idma') else 'pio'
        binary=ORIGINAL/f'builds/ram-{mode}25/capture.bin'
        require(item['mode']==mode and item['clock_hz']==25000000 and
            item['binary_sha256']==sha(binary),'Control does not use exact original25MHz binary')
        item['same_original_binary']=binding(binary)
        if (folder/'result.json').exists():
            result=read(folder/'result.json')
            require(result.get('passed') is True and (folder/'final-idle/verified.json').is_file(),
                'Successful trial lacks final exact idle proof')
            item['runner_result']=binding(folder/'result.json')
            item['final_idle']=binding(folder/'final-idle/verified.json')
        else:
            item['runner_failure']=binding(folder/'failed.json')
        records.append(item)
    initial=read(ORIGINAL/'reports/analysis-complete01.json')
    groups={mode:dict(Counter(item['outcome'] for item in records
        if item['name'].startswith(mode+'25-'))) for mode in ('pio','idma')}
    complete=all(item['outcome']!='pending_or_running' for item in records)
    return dict(schema=1,generated_utc=datetime.now(timezone.utc).isoformat(),hardware_access=False,
        original_archive=dict(checksums=binding(ORIGINAL/'SHA256SUMS'),
            index=binding(ORIGINAL/'archive-index.json'),analyzer=binding(script),
            results=binding(ORIGINAL/'reports/analysis-complete01.json')),
        condition=dict(user_confirmed_probes={'CH0':'CMD','CH1':'CLK','ground':'connected'},
            other_wiring='User reported unchanged; no independent geometry inspection',
            camera='Held in reset by the same diagnostic firmware',
            binaries='Exact same original PIO25/IDMA25 RAM executables'),
        historical_reference=historical_meta,fresh_reference=fresh_meta,
        initial_probe_free25_outcomes=initial['formal25_outcomes'],
        probe_control25_outcomes=groups,all_six_complete=complete,records=records,
        limitations=['Single known512-byte sector only; no image capture or complete-image read/write qualification.',
            'Both CLK and CMD probes plus their ground connection changed together; individual loading/return-path causes are not isolated.',
            'This is a paired digital outcome comparison, not measured analog timing margin or formal SD compliance.',
            'Failed attempts remain failed; cleanup fields never synthesize successful-idle permission.',
            'The preexisting sealed archive is referenced and never modified.'])

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
        'initial_probe_free25_outcomes','probe_control25_outcomes')},indent=2))

if __name__=='__main__': main()
