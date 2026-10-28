"""Offline RAW-cycle phase/energy report using the frozen v66c energy method.

No hardware imports or commands. Failed phase widths stay failed. Completion
qualification needs an independently bound, root-authored SBF attestation;
image verification is separate. Large sample hashing requires stopped recorders.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

from phase_decode import summarize_folder

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=ROOT/'firmware/capture-sd/evidence/2026-10-24-normal-profile/analysis/energy'
ENERGY=BASE/'support/cycle_energy.py'
ENERGY_SHA='f27c99858edc83fb55636767386b476c474f10a14ba3847f1b0dac81bc4e8e9c'
BASE_SHA='3e1bcca11c5ff8ef1153d427699d3821824ca2b535b3a7b91d9b8d33bf112399'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''): h.update(block)
    return h.hexdigest()


def require(value,message):
    if not value: raise ValueError(message)


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def resolve(base,value):
    p=Path(value)
    return p.resolve() if p.is_absolute() else (base/p).resolve()


def bound_artifact(base,item):
    path=resolve(base,item['path'])
    require(sha(path)==item['sha256'],'Evidence hash changed: '+str(path))
    return path


def qualification(path,*,cycle_name,recording_result,sector,prefix):
    """Validate independently checked SBF without inventing trial attribution."""
    path=Path(path); q=read(path)
    require(q.get('schema')==1 and q.get('bench_owner')=='root','Expected root qualification schema1')
    require(q.get('cycle')==cycle_name and q.get('sector_sha256')==sector,
            'Qualification cycle/firmware mismatch')
    require(q.get('recording_result_sha256')==sha(recording_result),'Qualification recording mismatch')
    for key in ('owner_attests_no_intervening_poweroff','owner_attests_sbf_cleared_before_cycle'):
        require(q.get(key) is True,'Missing trial attribution: '+key)
    require(isinstance(q.get('owner_attestation'),str) and bool(q['owner_attestation'].strip()),
            'Missing human-readable owner attribution')
    sbf_path=bound_artifact(path.parent,q['sbf_evidence']); s=read(sbf_path)
    require(s.get('passed') is True and s.get('sbf') is True and s.get('prefix_sha256')==prefix,
            'SBF proof is not a passed exact-prefix observation')
    require(s.get('cpucr_written') is False and s.get('reset_or_power_changed') is False,
            'SBF reader changed trial state')
    park=s.get('fresh_park_result',{})
    require(park.get('passed') is True and park.get('prefix_sha256')==prefix,
            'SBF proof lacks exact fresh recovery park')
    result=dict(terminal_state_qualified=True,owner_attestation=q['owner_attestation'],
                qualification_sha256=sha(path),sbf_evidence_sha256=sha(sbf_path),
                image_integrity_verified=False)
    if 'image_evidence' in q:
        image=bound_artifact(path.parent,q['image_evidence'])
        # Image reports have several independently reviewed schemas. Bind the
        # bytes but require explicit ownership of their interpretation here.
        require(q.get('owner_attests_complete_slot_readback') is True,
                'Image report supplied without full-slot readback attestation')
        require(type(q.get('slot')) is int and q['slot']>=0,'Image slot missing')
        result.update(image_integrity_verified=True,image_evidence_sha256=sha(image),slot=q['slot'],
                      image_qualification='Owner attests complete slot readback; report hashed, schema not reinterpreted')
    return result


def phase_intervals(decoded):
    """Use only unique width-decoded events; do not fill an unknown final pulse."""
    by_id={}
    for p in decoded['pulses']:
        if p.get('event_id') is not None: by_id.setdefault(p['event_id'],[]).append(p)
    times={i:v[0]['start_s'] for i,v in by_id.items() if len(v)==1}
    pairs=[('receiver_to_strobe',1,2),('strobe_to_frame',2,3),
           ('sd_initialize',4,5),('sd_ready_to_first_payload',5,6),
           ('payload_through_padded_tail_ready',6,7),('full_commit',7,8),
           ('deinitialize',8,9),('deinitialize_to_pre_wfi',9,10)]
    intervals={name:(times[b]-times[a])*1000 if a in times and b in times and times[b]>=times[a]
               else None for name,a,b in pairs}
    resets=decoded.get('reset_rises_s',[])
    reference=resets[0] if len(resets)==1 else None
    reset_times={str(i):(t-reference)*1000 for i,t in times.items()
                 if reference is not None and t>=reference}
    overlap=None
    if all(i in times for i in (2,3,4,5)):
        overlap=max(0,min(times[3],times[5])-max(times[2],times[4]))*1000
    return dict(strict_decode_passed=decoded['decode_passed'],interval_ms=intervals,
                since_reset_ms=reset_times,capture_sd_init_overlap_ms=overlap,
                unknown_pulse_count=sum(p.get('event_id') is None for p in decoded['pulses']),
                interpretation='Independent width-decoded events only; overlapping intervals are not additive')


def distribution(values):
    return dict(n=len(values),median=statistics.median(values),minimum=min(values),maximum=max(values))


def summarize(spec_path,out):
    spec_path=Path(spec_path).resolve(); spec=read(spec_path); out=Path(out).resolve()
    require(spec.get('schema')==1,'Expected summary specification schema1')
    require(not out.exists(),'Output directory must be new')
    require(sha(ENERGY)==ENERGY_SHA and sha(BASE/'summary.json')==BASE_SHA,
            'Frozen v66c analysis dependency changed')
    baseline=read(BASE/'summary.json')
    loader=importlib.util.spec_from_file_location('raw_frozen_cycle_energy',ENERGY)
    energy=importlib.util.module_from_spec(loader);loader.loader.exec_module(energy)
    build=resolve(spec_path.parent,spec['build']); m=read(build/'manifest.json')
    staged=read(build/'staged/manifest.json'); sector=staged['program_sha256']
    prefix=staged['stage1_raw_sha256']
    require(m.get('kind')=='raw-slots' and m.get('flash') is True and m.get('standby') is True,
            'Expected RAW Standby build')
    require(sha(build/'capture.bin')==m['binary_sha256']==staged['stage2_full_sha256'] and
            sha(build/'manifest.json')==staged['stage2_manifest_sha256'] and
            sha(build/'staged/stage1.bin')==prefix and
            sha(build/'staged/capture_sector_0.bin')==sector,'Build bytes differ from identity')
    require(isinstance(spec.get('cycles'),list) and bool(spec['cycles']),'No cycles')
    names=[v['name'] for v in spec['cycles']]
    require(len(names)==len(set(names)) and all(n.replace('-','').replace('_','').isalnum() for n in names),
            'Cycle names must be distinct simple identifiers')
    # Preflight all small records before any large hashing/output creation.
    prepared=[]
    for item in spec['cycles']:
        source=resolve(spec_path.parent,item['recording']); r=read(source/'result.json')
        rm=read(source/'raw/manifest.json')
        require(r.get('recording_complete') is True and r.get('expected_end')=='standby' and
                r.get('sector_sha256')==sector and sha(source/'raw/manifest.json')==r['raw_manifest_sha256'],
                'Cycle recording identity differs')
        require(rm.get('finalized') is True,'Recorder is not finalized')
        require(sha(source/'phase-summary.json')==r['phase_summary_sha256'],'Persisted phase summary changed')
        decoded=summarize_folder(source/'phase',standby=True,protocol=m['phase_markers'])
        # JSON persists tuple precedence edges as lists; normalize only their
        # representation, never widths, event labels or pass/fail values.
        require(json.loads(json.dumps(decoded))==read(source/'phase-summary.json'),
                'Phase reanalysis differs from original result')
        q=dict(terminal_state_qualified=False,image_integrity_verified=False,
               qualification='Current signature only; no complete-cycle or Standby claim')
        if item.get('qualification'):
            q=qualification(resolve(spec_path.parent,item['qualification']),cycle_name=item['name'],
                recording_result=source/'result.json',sector=sector,prefix=prefix)
        prepared.append((item,source,r,rm,decoded,q))
    out.mkdir(parents=True)
    records=[]
    for item,source,r,rm,decoded,q in prepared:
        dest=out/item['name'];dest.mkdir()
        context=dict(schema=1,cycle=item['name'],sector_sha256=sector,
            recording_result_sha256=sha(source/'result.json'),**q)
        write(dest/'context.json',context)
        with energy.Archive(source/'raw') as archive:
            require(archive.rate==2000000 and archive.decimation==1,'Expected native 2 MHz JS samples')
            # Same fixed-window recipe as v66c: skip first five seconds of
            # initial powered setup; retain the subsequent measured off baseline.
            window=dict(name=item['name'],start_sample_id=archive.start+10000000,
                end_sample_id=archive.end,terminal_state_qualified=q['terminal_state_qualified'],
                terminal_evidence=str(dest/'context.json'))
            result=energy.analyze_cycle(archive,window,baseline['same_boundary_criteria'],
                allow_unqualified_plateau=not q['terminal_state_qualified'])
        write(dest/'energy.json',result); timing=phase_intervals(decoded)
        write(dest/'phase.json',timing)
        records.append(dict(name=item['name'],onset_to_plateau_s=result['onset_to_plateau_s'],
            onset_to_plateau_energy_j=result['onset_to_plateau_energy_j'],
            plateau_confirmation_energy_j=result['plateau_confirmation_energy_j'],
            plateau_mean_current_a=result['plateau']['mean_current_a'],
            peak_current_a=result['peak_current_a'],phase=timing,**q))
    qualified=all(r['terminal_state_qualified'] for r in records)
    summary=dict(schema=1,sector_sha256=sector,prefix_sha256=prefix,cycles=records,
        terminal_state_qualified=qualified,image_integrity_verified=all(r['image_integrity_verified'] for r in records),
        energy_j=distribution([r['onset_to_plateau_energy_j'] for r in records]),
        current_onset_to_plateau_s=distribution([r['onset_to_plateau_s'] for r in records]),
        same_boundary_criteria=baseline['same_boundary_criteria'],
        v66c_baseline_sha256=BASE_SHA,energy_analyzer_sha256=ENERGY_SHA,
        v66c_energy_j=baseline['energy_j'],v66c_current_onset_to_plateau_s=baseline['current_onset_to_plateau_s'],
        limits=['Native JS current boundaries and Saleae markers use independent clocks; no per-phase energy is inferred.',
                'One-second plateau confirmation energy is reported separately and excluded from the headline energy.',
                'Measured JS board-branch energy includes Nucleo overhead and omits unmeasured bypass paths.',
                'Different scenes, formats and card latencies prevent isolating a single cause of improvement.',
                'SBF evidence needs root attribution; stored image integrity is a separate readback test.',
                'A failed strict pulse remains unknown; intervals use only unique directly decoded endpoints.'])
    if qualified:
        summary['observed_median_energy_reduction_fraction']=1-summary['energy_j']['median']/baseline['energy_j']['median']
        summary['observed_median_time_reduction_fraction']=1-summary['current_onset_to_plateau_s']['median']/baseline['current_onset_to_plateau_s']['median']
    write(out/'summary.json',summary)
    lines=['# Packed RAW capture cycle measurements','',
        'Qualified complete-cycle measurements.' if qualified else 'Signature-only results; completion qualification is incomplete.','',
        '| Cycle | Current onset → plateau (s) | Energy (J) | Plateau (mA) | Strict phase decode | SBF attributed | Image readback |',
        '|---|---:|---:|---:|---|---|---|']
    for r in records:
        lines.append(f"| {r['name']} | {r['onset_to_plateau_s']:.6f} | {r['onset_to_plateau_energy_j']:.6f} | {r['plateau_mean_current_a']*1000:.3f} | {r['phase']['strict_decode_passed']} | {r['terminal_state_qualified']} | {r['image_integrity_verified']} |")
    lines+=['','Overlapping timing intervals (ms); blanks have an unidentified endpoint.','',
        '| Interval | '+' | '.join(r['name'] for r in records)+' |',
        '|---|'+'---:|'*len(records)]
    for key in records[0]['phase']['interval_ms']:
        cells=[r['phase']['interval_ms'][key] for r in records]
        lines.append('| '+key+' | '+' | '.join('—' if v is None else f'{v:.3f}' for v in cells)+' |')
    lines+=['','Limitations:','']+['- '+v for v in summary['limits']]
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(out/'manifest.json',dict(schema=1,spec_sha256=sha(spec_path),files={
        p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--recorders-stopped',action='store_true')
    a=p.parse_args()
    if not a.recorders_stopped: p.error('Confirm recorders stopped before large offline hashing')
    result=summarize(a.spec,a.out)
    print(json.dumps({k:result[k] for k in ('terminal_state_qualified','energy_j','current_onset_to_plateau_s')},indent=2))


if __name__=='__main__':main()
