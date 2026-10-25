"""Stdlib-only replay of compact replacement-card evidence; no hardware imports.

Checks content hashes, recorded format/READ/Standby attribution, card identity,
complete READ extents, and native-sample compact integral sums. It does not
reconstruct private pixels or rerun native onset/plateau classification.
"""
import argparse
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import struct
import zipfile

SECTOR = '174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e'
PREFIX = '9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba'
RAM = '1b96bf02555a33035a6ca4b4fd641409d9e2129274f9dfbf326ae1aa26d51b2f'
SEGMENTS = (('pretrigger_energy_j','integration_start_sample_id','current_onset_sample_id'),
    ('onset_to_plateau_energy_j','current_onset_sample_id','terminal_plateau_start_sample_id'),
    ('plateau_confirmation_energy_j','terminal_plateau_start_sample_id','integration_end_sample_id'),
    ('pretrigger_through_confirmed_plateau_energy_j','integration_start_sample_id','integration_end_sample_id'))

def sha(data): return hashlib.sha256(data).hexdigest()
def js(data): return json.loads(data.decode('utf-8-sig'))
def req(ok, message):
    if not ok: raise ValueError(message)

def pure_guards(source):
    names = {'magic_geometry','frame_layout','magic_layout','capture_geometry','request','validate'}
    tree = ast.parse(source); nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    req({n.name for n in nodes} == names, 'Frozen pure guards differ')
    env = dict(struct=struct, LOAD=0x34300000, FRAME=0x34000000, REQUEST=0x343FD000, PROOF=0x343FD100,
        READ_BUFFER=0x34200000, READ_MAX=262144, FRAME_BYTES=1909600, MAGIC=0x52535731, DONE=0x5253444E,
        MAGIC_FRAME=0x34000010, MAGIC_BUFFER=0x3400000C, SLOT_BYTES=1909760,
        FRONT_MAGIC_FRAME=0x340000A0, FRONT_MAGIC_BUFFER=0x34000004, OPS={'capture':1,'format':2,'read':3})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'archived-pure-guards', 'exec'), env)
    return env

def integrated(rows, start, end, rate):
    selected = [r for r in rows if start <= r[0] and r[1] <= end]
    req(selected and selected[0][0] == start and selected[-1][1] == end and
        all(a[1] == b[0] for a,b in zip(selected,selected[1:])), 'Energy bin boundary/coverage differs')
    return math.fsum(r[9] for r in selected) / rate

def replay(folder):
    folder = Path(folder); index = js((folder/'index.json').read_bytes()); archive = (folder/'objects.zip').read_bytes()
    req(index['schema'] == 1 and sha(archive) == index['objects_zip_sha256'], 'Archive identity differs')
    with zipfile.ZipFile(folder/'objects.zip') as z:
        expected = {'objects/'+v['sha256'] for v in index['files'].values()}
        req(set(z.namelist()) == expected and len(z.namelist()) == len(expected), 'Unexpected/duplicate archive object')
        files = {}
        for name, entry in index['files'].items():
            req(not name.startswith('/') and '..' not in PurePosixPath(name).parts, 'Unsafe logical path')
            raw = z.read('objects/'+entry['sha256'])
            req(sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], 'Object hash/size differs')
            kind = entry['kind']
            if kind == 'json': js(raw)
            elif kind == 'text': raw.decode('utf-8-sig')
            elif kind == 'compact-gzip':
                req(PurePosixPath(name).name in ('power-compact.json.gz','raw-chunks.jsonl.gz'), 'Unapproved gzip')
                gzip.decompress(raw).decode('utf-8')
            else: raise ValueError('Unapproved binary kind')
            files[name] = raw
    get = lambda name: js(files[name])
    if 'recovery/finding.json' in files:
        recovery = get('recovery/finding.json')
        for item in recovery['public_records']:
            req(sha(files['recovery/records/'+item['name']]) == item['sha256'], 'Recovery metadata binding differs')
        park = get('recovery/records/preflight-park-after-baud/result.json')
        req(park['passed'] and park['prefix_sha256'] == PREFIX and
            park['vcp_status']['good_pulses'] == 9 and park['vcp_status']['bad_pulses'] == 0 and
            park['vcp_status']['source_bits'] == 2 and not park['ram_writes'] and not park['nor_commands'],
            'Recorded restored recovery proof differs')
        req(sha(files['recovery/records/preflight-park-after-baud/result.json']) ==
            recovery['successful_park']['source']['sha256'], 'Recovery finding/park attribution differs')
    fm = get('build/flash-manifest.json'); pm = get('build/prefix-manifest.json'); rm = get('build/ram-manifest.json')
    req(pm['program_sha256'] == SECTOR and pm['stage1_raw_sha256'] == PREFIX and rm['binary_sha256'] == RAM,
        'Unreviewed firmware identity')
    req(sha(files['build/flash-manifest.json']) == pm['stage2_manifest_sha256'], 'Flash manifest binding differs')
    for m in (fm, rm):
        req(m['magic_layout_version'] == 2 and m['image_offset'] == 156 and m['metadata_bytes'] == 152 and
            m['frame_bytes'] == 1909600 and m['slot_buffer'] == 0x34000004, 'V18 geometry differs')
    guards = pure_guards(files['tools/bench.py']); guards['magic_layout'](rm)
    erase = get('commission/erase.json'); identity = {k:erase['card'][k] for k in ('sector_count','cid0','cid1','cid2','cid3')}
    def terminal(v):
        req(v['passed'] is True and v['binary_sha256'] == RAM, 'Unrecognized RAM terminal')
        p = v['proof']; guards['validate'](p,rm,v['request_words']); c = v['card']
        req({k:c[k] for k in identity} == identity, 'Card changed between recorded operations')
        req(c['media_idle'] == 1 and c['initialized'] == c['controller_owned'] == c['error'] == c['cleanup_error'] == 0
            and c['last_ready_r1'] & 0x1f00 == 0x900, 'Card terminal ownership/readiness differs')
        return p
    p = terminal(erase); s = erase['magic_format']; wire = bytes(s['scr_wire_bytes']); e = s['erase']
    req(p['operation'] == 2 and len(wire) == 8 and wire[0] >> 4 == 0 and
        s['erased_byte'] == (255 if wire[1] & 128 else 0), 'Erase/SCR identity differs')
    req(e['started'] == e['completed'] == 1 and e['first_lba'] == 0 and e['last_lba'] == identity['sector_count']-1
        and e['last_r1'] & 0x1f00 == 0x900 and not p['card_write_lo'] and not p['card_write_hi'], 'Whole-card erase incomplete')
    if 'commission/preflight.json' in files: terminal(get('commission/preflight.json'))
    summary = get('energy/summary.json'); req(summary == get('analysis/summary.json'), 'Analysis summary differs')
    names = index['cycle_names']; req(len(names) == 3 and len(set(names)) == 3 and
        [r['name'] for r in summary['cycles']] == names, 'Expected three matching cycles')
    compact_manifest = get('energy/manifest.json')
    for name, data in files.items():
        if name.startswith('energy/') and name != 'energy/manifest.json':
            req(sha(data) == compact_manifest['files'][name[7:]], 'Compact manifest mismatch')
    results = []
    for name, row in zip(names, summary['cycles']):
        ck = 'cycles/'+name+'/'; ik = 'images/'+name+'/'; ek = 'energy/'+name+'/'
        cycle = get(ck+'result.json'); phase = get(ck+'phase-summary.json'); response = get(ck+'response.json')
        sbf = get(ck+'sbf.json'); q = get(ck+'qualification.json'); image = get(ik+'readback-validation.json')
        req(cycle['recording_complete'] and cycle['expected_end'] == 'standby' and cycle['sector_sha256'] == SECTOR,
            'Cycle incomplete/wrong firmware')
        req(cycle['phase_summary_sha256'] == sha(files[ck+'phase-summary.json']) and
            cycle['safe_start_proof_sha256'] == sha(files[ck+'safe-start-proof.json']), 'Cycle proof binding differs')
        ids = phase['event_ids']; req(len(ids) == 10 and set(ids[:9]) == set(range(1,10)) and ids[-1] in (None,10),
            'Phase completion event set differs')
        for order in ((1,2,3),(4,5,6,7,8,9),(3,7)):
            req(all(ids.index(a) < ids.index(b) for a,b in zip(order,order[1:])), 'Phase partial order differs')
        req(response['event'] == 'stopped' and response['ok'] and response['range'] == 128 and not response['restore_error'],
            'Recorder did not restore settings cleanly')
        req(sbf['passed'] and sbf['sbf'] and sbf['prefix_sha256'] == PREFIX and not sbf['cpucr_written'] and
            not sbf['reset_or_power_changed'] and sbf['fresh_park_result']['passed'], 'SBF/recovery proof differs')
        req(q['bench_owner'] == 'root' and q['cycle'] == name and q['sector_sha256'] == SECTOR and
            q['owner_attests_no_intervening_poweroff'] and q['owner_attests_sbf_cleared_before_cycle'] and
            q['owner_attests_complete_slot_readback'] and q['recording_result_sha256'] == sha(files[ck+'result.json']) and
            q['sbf_evidence']['sha256'] == sha(files[ck+'sbf.json']) and
            q['image_evidence']['sha256'] == sha(files[ik+'readback-validation.json']), 'Cycle/image attribution differs')
        req(image['passed'] and image['full_slot_read'] and image['full_payload_read'] and image['bytes'] == 1909600 and
            image['slot_bytes'] == 1909760 and image['png_samples_match_read_raw'] and image['slot'] == q['slot'], 'Incomplete recorded image')
        image_summary = get(ik+'summary.json'); image_rows = image_summary['slots']
        req(image_summary['passed'] and len(image_rows) == 1 and image_rows[0]['slot'] == image['slot'] and
            image_rows[0]['validation']['sha256'] == sha(files[ik+'readback-validation.json']),
            'Image summary does not bind this exact slot validation')
        h = image['header']; req(h['state'] == 'COMPLETE' and h['start_magic_valid'] and h['completion_marker_valid'] and
            h['format_revision'] == 2 and h['image_offset'] == 156 and h['trailer_offset'] == 1909756 and
            bytes.fromhex(h['metadata_hex']) == bytes(152), 'GXR2 object geometry/zero metadata differs')
        req(not image['original_sensor_frame_comparison'] and image['source_reference_comparison'] is None,
            'Standby image must not claim lost source-RAM comparison')
        source = get(ik+'scr-source.json')
        req(source['card_identity'] == identity and source['erased_byte'] == s['erased_byte'] and
            source['proof']['sha256'] == sha(files['commission/erase.json']), 'Image SCR provenance differs')
        proof_names = sorted(k for k in files if k.startswith(ik+'payload-') and k.endswith('/verified.json'))
        req(len(proof_names) == 8, 'Eight complete bounded reads required')
        local = get(ik+'private-byte-validation.json')
        req(local['passed'] and local['private_bytes_checked_locally'] and not local['private_bytes_published'] and
            local['concatenated_chunks_equal_slot'] and local['extracted_frame_equal_slot_extent'] and
            local['validation_sha256'] == sha(files[ik+'readback-validation.json']) and local['slot'] == image['slot'] and
            local['slot_bytes'] == 1909760 and local['image_bytes'] == 1909600 and
            all(local[k] == image[k] for k in ('slot_sha256','raw_sha256','png_sha256')) and len(local['chunks']) == 8,
            'Recorded local byte validation binding differs')
        offset = 0
        for key, chunk in zip(proof_names, local['chunks']):
            rp = terminal(get(key)); count = min(512,3730-offset)
            req(rp['operation'] == 3 and rp['read_lba'] == image['slot']*3730+offset and
                rp['read_count'] == count and rp['read_bytes'] == count*512, 'READ extent differs')
            req(chunk['name'] == PurePosixPath(key).parent.name and chunk['read_lba'] == rp['read_lba'] and
                chunk['read_count'] == count and chunk['bytes'] == count*512 and
                chunk['sha256'] == get(key)['read_sha256'] and chunk['proof_sha256'] == sha(files[key]),
                'Recorded local chunk verification differs')
            offset += count
        req(offset == 3730 and image_summary['scr_source'] == get(ik+'scr-source.json'), 'Incomplete slot coverage/SCR binding')
        power = js(gzip.decompress(files[ek+'power-compact.json.gz'])); wrapped = get(ek+'analysis.json')
        native = get(ek+'raw-manifest.json'); analysis, = wrapped['cycles']; rows = power['rows']; bounds = power['boundaries']
        req(power['analysis_sha256'] == sha(files[ek+'analysis.json']) and
            power['raw_manifest_sha256'] == sha(files[ek+'raw-manifest.json']) == cycle['raw_manifest_sha256'] and
            power['raw_files'] == native['files'] and power['cycle_analysis'] == analysis and native['finalized'] and
            native['status']['coverage']['passed'], 'Native compact binding differs')
        req(sha(gzip.decompress(files[ek+'raw-chunks.jsonl.gz'])) == native['chunks_sha256'] == power['raw_chunks_sha256'],
            'Native chunk coverage metadata differs')
        context = get(ek+'context.json')
        expected_context = dict(schema=1,cycle=name,sector_sha256=SECTOR,
            recording_result_sha256=sha(files[ck+'result.json']), terminal_state_qualified=True,
            qualification_sha256=sha(files[ck+'qualification.json']), sbf_evidence_sha256=sha(files[ck+'sbf.json']),
            image_integrity_verified=True, image_evidence_sha256=sha(files[ik+'readback-validation.json']), slot=image['slot'])
        req(all(context.get(k) == v for k,v in expected_context.items()), 'Energy context does not bind this qualified cycle/image')
        req(analysis['name'] == name and analysis['terminal_state_qualified'] is True and
            sha(files[ek+'context.json']) == analysis['terminal_evidence_sha256'], 'Energy terminal evidence differs')
        for field in ('terminal_state_qualified','qualification_sha256','sbf_evidence_sha256',
                      'image_integrity_verified','image_evidence_sha256','slot'):
            req(row.get(field) == context[field], 'Energy summary/context attribution differs: '+field)
        req(power['sample_rate_hz'] == 2000000 and power['decimate_factor'] == 1 and
            all(len(r) == 12 and r[2] == r[1]-r[0] and r[2] > 0 and all(math.isfinite(v) for v in r) for r in rows) and
            all(a[1] == b[0] for a,b in zip(rows,rows[1:])), 'Native bin geometry/coverage differs')
        terms = {}
        for field,a,b in SEGMENTS:
            value = integrated(rows,bounds[a],bounds[b],power['sample_rate_hz'])
            req(math.isclose(value,analysis[field],rel_tol=1e-12,abs_tol=1e-12) and
                math.isclose(value,power['exact_segment_integrals_j'][field],rel_tol=1e-12,abs_tol=1e-12), 'Energy sum differs')
            terms[field] = value
        duration = (bounds['terminal_plateau_start_sample_id']-bounds['current_onset_sample_id'])/2000000
        req(math.isclose(duration,analysis['onset_to_plateau_s'],rel_tol=1e-12,abs_tol=1e-12) and
            analysis['onset_to_plateau_s'] == row['onset_to_plateau_s'] and
            analysis['onset_to_plateau_energy_j'] == row['onset_to_plateau_energy_j'], 'Energy summary differs')
        results.append(dict(name=name, slot=image['slot'], read_sectors=offset, recorded_raw_sha256=image['raw_sha256'],
            current_onset_to_plateau_s=duration, energy_intervals_j=terms, strict_phase_decode=phase['decode_passed'],
            sbf_attributed=True, recorded_image_validation=True, pixels_redecoded=False))
    req([r['slot'] for r in results] == [0,1,2], 'Freshly erased card must attribute three distinct consecutive slots 0,1,2')
    for key, field in (('energy_j','onset_to_plateau_energy_j'),('current_onset_to_plateau_s','onset_to_plateau_s')):
        values = [r[field] for r in summary['cycles']]
        req(summary[key] == dict(n=3,median=statistics.median(values),minimum=min(values),maximum=max(values)), 'Aggregate differs')
    req(summary['same_boundary_criteria'] == get('energy/v66c-summary.json')['same_boundary_criteria'], 'Energy criteria differ')
    req(summary['terminal_state_qualified'] and summary['image_integrity_verified'], 'Group qualification incomplete')
    final = get('final-state.json'); req(final['bench_owner'] == 'root' and final['sector_sha256'] == SECTOR, 'Final identity differs')
    visual = get('visual-review.json') if 'visual-review.json' in files else None
    if visual is not None:
        req(visual['schema'] == 1 and visual['reviewer'] == 'root', 'Visual observation attribution differs')
        for i,name in enumerate(names,1):
            observation = visual['image'+str(i).zfill(2)]; image = get('images/'+name+'/readback-validation.json')
            req(observation['scene_png_viewed'] is True and
                type(observation['coherent_illuminated_scene_verified']) is bool and
                all(observation[k] == image[k] for k in ('minimum_sample','maximum_sample','mean_sample')),
                'Visual observation does not match recorded image sample statistics')
    return dict(schema=1, passed=True, hardware_access=False, card_identity=identity, scr_wire_bytes=list(wire),
        erased_byte=s['erased_byte'], cycles=results, energy_j=summary['energy_j'],
        current_onset_to_plateau_s=summary['current_onset_to_plateau_s'], visual_observations=visual, limits=index['limits'])

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--archive',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path); a=p.parse_args(); result=replay(a.archive)
    text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if a.out:
        with a.out.open('x',encoding='utf-8') as f: f.write(text)
    print(text)

if __name__ == '__main__': main()
