"""Replay compact phase/CPU timing evidence, without instruments or image data."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
import phase_timing
import receiver_timing
import compare_awake
from fine_timing import analyze_report, validate_raw_report, require


def replay(root):
    root=Path(root)
    checked=[]
    phase_results={}
    for spec_path in sorted(root.glob('records/*/phase-spec.json')):
        folder=spec_path.parent
        actual=phase_timing.analyze(spec_path)
        phase_results[folder.name]=actual
        require(actual==json.loads((folder/'phase-analysis.json').read_text()),
                'Phase replay differs: '+folder.name)
        record={'trial':folder.name,'phase_replayed':True}
        receiver=folder/'receiver-spec.json'
        if receiver.exists():
            actual_receiver=receiver_timing.analyze(receiver)
            require(actual_receiver==json.loads((folder/'receiver-analysis.json').read_text()),
                    'Receiver timing replay differs')
            record['receiver_timing_replayed']=True
        if actual['completion_kind']=='awake':
            fine=json.loads((folder/'fine-analysis.json').read_text())
            require(all(fine.get(k)==v for k,v in actual['save_fine_timing'].items()),
                    'Fine timing replay differs')
            record['fine_timing_replayed']=True
        add_path=folder/'verification-addendum.json'
        if add_path.exists():
            add=json.loads(add_path.read_text())
            verified={}
            for key in ('verification_input','frame_metadata_input'):
                item=add[key];data=(folder/item['path']).read_bytes()
                require(hashlib.sha256(data).hexdigest()==item['sha256'], 'Verification identity differs')
                verified[key]=json.loads(data)
            png=verified['verification_input'];frame=verified['frame_metadata_input']
            require(add['image_readback_verified'] is True and
                png['all_png_chunk_crcs_valid'] is True and
                png['exact_pixels_sample_shift_left_6'] is True and
                png['pixels']==add['pixels']==1527680 and png['sBIT']==add['sBIT']==10 and
                png['bytes']==add['png_bytes']==actual['save_fine_timing']['png_bytes'] and
                png['frame_sha256']==add['raw_frame_sha256']==frame['raw_sha256'] and
                png['sha256']==add['png_sha256'], 'Image verification metadata differs')
            record['separate_image_verification_metadata_replayed']=True
            record['image_pixels_replayed']=False
        checked.append(record)
    require(checked, 'No phase records found')
    comparison=root/'comparison-awake-spec.json'
    comparison_replayed=False
    if comparison.exists():
        require(compare_awake.analyze(comparison)==json.loads((root/'comparison-awake.json').read_text()),
                'Awake comparison replay differs')
        comparison_replayed=True
    phase_summary=root/'phase-summary.json'
    if phase_summary.exists():
        summary=json.loads(phase_summary.read_text())
        pairs=[('reset_to_strobe_irq',None,1),('reset_to_frame_irq',None,2),
            ('frame_irq_to_save',2,3),('sd_init',3,4),('mount',4,5),
            ('mount_to_png_return',5,6),('final_flush_commit',6,7),('final_checks',7,8),
            ('late_load_and_peripheral_shutdown_to_pre_wfi',8,9),('reset_to_pre_wfi',None,9)]
        for key,a,b in pairs:
            values={}
            for name,sha in summary['input_sha256'].items():
                require(hashlib.sha256((root/'records'/name/'phase-analysis.json').read_bytes()).hexdigest()==sha,
                        'Phase summary input identity differs')
                phase=phase_results[name]
                values[name]=(phase['events'][b]['rising_edge_s']-
                    (phase['reset_release_s'] if a is None else phase['events'][a]['rising_edge_s']))*1000
            require(summary['intervals'][key]=={'trial_ms':values,'median_ms':statistics.median(values.values()),
                    'minimum_ms':min(values.values()),'maximum_ms':max(values.values())}, 'Phase aggregate differs')
    energy=None
    if (root/'energy/manifest.json').exists():
        import energy_replay
        energy=energy_replay.replay(root/'energy')
    return {'schema':1,'passed':True,'records':checked,
            'awake_comparison_replayed':comparison_replayed,
            'energy_replay':energy,
            'limits':['Image payloads and full raw power samples are not read by this replay.',
                      'Fine timing uses nominal 400 MHz; external marker timing remains a separate clock.',
                      'Source-order phase labels do not repair failed pulse-width qualification.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=replay(args.root)
    if args.out:args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
