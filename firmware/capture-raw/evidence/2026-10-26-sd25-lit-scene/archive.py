"""Offline single lit-scene addendum; never changes the frozen twenty-image run.

Private camera/SD/PNG bytes are compared locally, then represented by hashes.
No debugger, instrument, serial, subprocess, power or network access is used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[4]
BASE_SHA = '39391fb566ee839d91ace743bf0e7bcf77a9c5b372905c69013bc4479cbbb7b0'
BASE_PATH = Path(__file__).with_name('base_archive.py')
if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Frozen independent verifier changed')
spec = importlib.util.spec_from_file_location('lit_scene_base', BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def attempts(folder):
    """Count every capture/read directory, including failed or unfinished attempts."""
    result = []
    candidates = {p for p in folder.rglob('*') if p.is_dir()
                  and (p.name.startswith('capture') or p.name.startswith('payload-'))}
    for path in sorted(candidates):
        proof = next((path / name for name in ('verified.json', 'proof.json', 'incomplete.json')
                      if (path / name).exists()), None)
        item = dict(folder=str(path), verified=proof is not None and proof.name == 'verified.json')
        try:
            value = base.read(proof)
            p, c = value.get('proof', value), value.get('card', {})
            item.update(source=base.bound(proof), passed=value.get('passed'),
                result=p.get('result'), sd_error=p.get('sd_error'), cleanup_error=p.get('cleanup_error'),
                card_error=c.get('error'), card_cleanup_error=c.get('cleanup_error'),
                error_stage=c.get('error_stage'), error_command=c.get('error_command'),
                error_sta=c.get('error_sta'),
                command_crc_flag=bool(c.get('error_sta', 0) & 1) or c.get('error') == 8,
                data_crc_flag=bool(c.get('error_sta', 0) & 2))
        except Exception as error:
            item['parse_error'] = str(error)
        result.append(item)
    return result


def input_paths(source):
    paths = list((source / 'lit-scene01').rglob('*')) + list((source / 'ram25-scene').rglob('*'))
    for path in sorted(paths):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        keep = path.suffix.lower() in ('.json', '.jsonl') and not path.name.startswith('independent-')
        keep |= path.name in ('cycle-trace.bin', 'producer.bin')
        keep |= rel.parts[0] == 'ram25-scene' and (path.suffix.lower() in ('.c', '.h', '.s', '.ld') or path.name == 'capture.bin')
        if keep:
            yield path


def collect(source):
    source = Path(source).resolve()
    folder = source / 'lit-scene01'
    manifest = base.check_build(source / 'ram25-scene', 'ram25-scene')
    cycle = base.verify_cycle(source, 'lit-scene01', {'ram25-scene': manifest}, 'ram25-scene')
    prior = base.read(ROOT / 'firmware/capture-raw/evidence/2026-10-26-sd25-twenty/summary.json')
    if cycle['passed']:
        base.require(cycle['card_identity'] == prior['card_identity'], 'Lit scene used a different card')
        used = {c['slot'] for c in prior['cycles'] + prior['supplemental_captures'] if c['passed']}
        base.require(cycle['slot'] not in used, 'Lit scene overwrote an earlier verified slot')
    observed = attempts(folder)
    errors = [v for v in observed if any(v.get(k) not in (0, None) for k in
              ('result', 'sd_error', 'cleanup_error', 'card_error', 'card_cleanup_error'))
              or v.get('command_crc_flag') or v.get('data_crc_flag') or v.get('parse_error')]
    unfinished = [v for v in observed if not v['verified'] or v.get('passed') is not True]
    failures = [dict(source=base.bound(p), record=base.read(p)) for p in sorted(folder.rglob('*failed.json'))]
    final = dict(passed=False, status='awaiting_bench_owner_final_state')
    state_path, gate_path = folder / 'final-state.json', folder / 'final-idle/verified.json'
    if state_path.exists() and gate_path.exists():
        state, gate = base.read(state_path), base.read(gate_path)
        last_path = folder / 'readback/payload-3584/verified.json'
        last = base.read(last_path)
        base.check_proof(last, manifest, 3, prior['card_identity'])
        base.require(gate['binary_sha256'] == state['binary_sha256'] == manifest['binary_sha256'],
                     'Final build identity differs')
        base.require((ROOT / gate['prior']).resolve() == last_path.resolve(), 'Fresh gate uses a stale prior')
        context = gate['context']
        base.require(context['registers']['PC'] == manifest['park']
                     and context['registers']['PRIMASK'] == 1 and context['registers']['CONTROL'] == 0
                     and not context['ccr'] & 0x30000 and not context['fpccr'] & 1,
                     'Final idle context differs')
        base.require((folder / state['final_proof']).resolve() == last_path.resolve()
                     and (folder / state['fresh_gate']).resolve() == gate_path.resolve()
                     and state['nor_unchanged'] is True and state['capture_workflow_exit_code'] == 0
                     and state['com8_closed_break_released'] is True
                     and state['joulescope_session_opened'] is False,
                     'Final-state proof/workflow/NOR identity differs')
        for key, expected in dict(result=0, media_idle=1, initialized=0, controller_owned=0,
                                  cleanup_error=0, caches_enabled=False).items():
            base.require(state[key] == expected, 'Final-state ownership differs: ' + key)
        final = dict(passed=True, status='bench_owner_final_state_and_fresh_gate_verified',
                     state=base.bound(state_path), fresh_gate=base.bound(gate_path),
                     terminal_proof=base.bound(last_path))
    recovery = []
    for p in sorted(folder.rglob('result.json')):
        value = base.read(p)
        if 'prefix_sha256' in value:
            base.require(value['prefix_sha256'] == base.PREFIX_SHA and value.get('passed') is True,
                         'Recovery proof differs')
            recovery.append(dict(source=base.bound(p), record=value))
    complete = cycle['passed'] and len(observed) == 9 and not errors and not unfinished and not failures and final['passed']
    return dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(), hardware_access=False,
        complete=complete, scope='One additional real-scene capture after the user illuminated the scene; not part of the original twenty.',
        source=str(source), cycle=cycle, attempts=observed, errors=errors,
        unfinished_attempts=unfinished, failures=failures, final=final, recovery=recovery,
        prior_summary=base.bound(ROOT / 'firmware/capture-raw/evidence/2026-10-26-sd25-twenty/summary.json'),
        input_sources=[base.bound(path) for path in input_paths(source)],
        build_artifacts={name: base.bound(source / 'ram25-scene' / name) for name in ('manifest.json', 'capture.bin')},
        host_verifier_source=base.bound(ROOT / 'firmware/capture-raw/cycle_trace.py'),
        installed_nor_changed=False, installed_nor_checkpoint_sha256=base.NOR_SHA,
        installed_nor_identity_scope='Prior independent NOR identity; no new NOR read/program in this addendum.',
        limits=prior['limits'])


def markdown(summary):
    c = summary['cycle']
    verdict = 'Passed' if summary['complete'] else 'Incomplete'
    lines = ['# Additional illuminated-scene capture at 25 MHz', '',
        f"**{verdict}.** One extra real-scene image follows the [completed twenty-image campaign](../2026-10-26-sd25-twenty/README.md). The user illuminated the scene after that campaign; its frozen records and twenty-image count are unchanged.", '']
    if c['passed']:
        t = c['timing']['durations_ms']
        lines += [f"Slot **{c['slot']}** passed exact comparison of all **{c['image_bytes']:,} original camera-RAM bytes**, the complete **{c['slot_bytes']:,}-byte / {c['sectors']:,}-sector** stored object, and independently decoded PNG samples. Both write and every readback used four-bit **25 MHz** on the same card. GXR2/GXRE markers and all 152 reserved metadata bytes were checked.", '',
            f"The actual write path was **{c['stream_mode']}**, using one preannouncement and one CMD25. Readback used eight guarded operations containing 59 PIO multiblock transactions. All nine capture/read operation records have zero retained command/data CRC flags, operation errors and cleanup errors. The image spans **{c['image_min']}–{c['image_max']}** with **{c['distinct_image_levels']} distinct 10-bit levels**; its sample mean is {c['image_mean']:.3f}.", '',
            '| Measured interval | Time |', '| --- | ---: |',
            f"| Sensor exposure | {c['exposure_us']/1000:.3f} ms |",
            f"| SD initialization | {t['sd_init']:.3f} ms |",
            f"| Slot write | {t['slot_write']:.3f} ms |",
            f"| Readback data transactions, summed | {t['readback_data_transactions']:.3f} ms |",
            f"| Eight readback reinitializations, summed | {t['readback_eight_reinitializations']:.3f} ms |", '',
            'These are nominal 400 MHz counter intervals. Readback data time excludes debugger/host gaps and the separately reported initializations. Transfer intervals include card/controller stalls and do not isolate physical flash programming or energy.', '']
    else:
        lines += [f"Verification status: `{c['status']}`. See summary.json for missing or failed inputs.", '']
    lines += ['The bench-owner [final state](inputs/lit-scene01/final-state.json) and [fresh exact idle gate](inputs/lit-scene01/final-idle/verified.json) are preserved. The installed NOR remains the reviewed 12.5 MHz startup/no-tail Standby firmware; this additional test runs awake from RAM.', '',
        'The bench owner visually inspected the reconstructed PNG and recognized ceiling beams, a hanging fixture and a patterned screen, with shadow detail and bright openings. No Joulescope session or new current/energy measurement was performed for this addendum.', '',
        '## Limits', '']
    lines += ['- ' + item for item in summary['limits']]
    lines += ['', '## Offline replay', '',
        'The original image, SD-sector and PNG bytes remain private. The public bundle retains hashes, exact code/source, operation/clock/ownership proofs, trace telemetry, recovery and final-state records.', '',
        '```text', 'python -B archive.py inspect --source <private campaign folder> --out <report.json>',
        'python -B archive.py freeze --source <private campaign folder> --out <new evidence folder>',
        'python -B archive.py verify --out <frozen evidence folder>', '```', '',
        'Freeze requires the image comparisons, all nine operations and the separate final-state gate to pass. Full pixel replay requires the private source data. The pinned base verifier is copied unchanged from the prior campaign.', '']
    return '\n'.join(lines)


def freeze(source, out, summary):
    base.require(summary['complete'], 'Image or final bench state is not completely verified')
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    base.require({p.name for p in out.iterdir()} <= {'archive.py', 'base_archive.py'}, 'Refusing to overwrite evidence bundle')
    def check(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                base.require(base.bound(value['path']) == value, 'Source changed while verifying: ' + value['path'])
            for v in value.values():
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)
    check(summary)
    copies = []
    source = Path(source).resolve()
    for item in summary['input_sources']:
        path = Path(item['path'])
        rel = path.relative_to(source)
        dest = out / 'inputs' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        dest.write_bytes(raw)
        copies.append(dict(source=str(path), path=dest.relative_to(out).as_posix(), bytes=len(raw), sha256=base.digest(raw)))
    for name, path in (('archive.py', Path(__file__)), ('base_archive.py', BASE_PATH),
                       ('host-source/cycle_trace.py', ROOT / 'firmware/capture-raw/cycle_trace.py')):
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != dest.resolve():
            shutil.copyfile(path, dest)
    base.write(out / 'summary.json', summary)
    base.write(out / 'source-copies.json', copies)
    (out / 'README.md').write_text(markdown(summary), encoding='utf-8')
    entries = [dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size, sha256=base.digest(p.read_bytes()))
               for p in sorted(out.rglob('*')) if p.is_file()]
    base.write(out / 'SHA256SUMS.json', dict(schema=1, files=entries))
    return base.verify_bundle(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'freeze', 'verify'))
    parser.add_argument('--source', type=Path, default=ROOT / 'tmp/bringup/sd25-stress-20261026')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'verify':
        result = base.verify_bundle(args.out)
    else:
        summary = collect(args.source)
        if args.action == 'inspect':
            base.write(args.out, summary)
            result = dict(complete=summary['complete'], image_passed=summary['cycle']['passed'],
                          final_passed=summary['final']['passed'], observed_operations=len(summary['attempts']))
        else:
            result = freeze(args.source, args.out, summary)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
