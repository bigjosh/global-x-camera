"""Compare two recorded awake trials without treating different frames as controlled."""
import argparse
import hashlib
import json
from pathlib import Path
from fine_timing import require


def analyze(spec_path):
    spec_path=Path(spec_path)
    spec=json.loads(spec_path.read_text())
    evidence={}
    for key,item in spec['artifacts'].items():
        data=(spec_path.parent/item['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest()==item['sha256'],'Comparison input changed: '+key)
        evidence[key]=json.loads(data)
    old,new=evidence['prior_phase'],evidence['current_phase']
    require(old['ordered_structure_valid'] and new['ordered_structure_valid'], 'Incomplete ordered phases')
    old_edges=old['all_marker_edges_s'][::2]
    new_edges=[e['rising_edge_s'] for e in new['events']]
    require(len(old_edges)==len(new_edges)==10,'Missing phase')
    records={}
    for name,a,b in [('frame_irq_to_save',2,3),('sd_init',3,4),('mount',4,5),
                     ('mount_to_png_return',5,6),('final_flush_and_commit_close',6,7),
                     ('post_commit_to_marker9',7,8),('save_begin_to_marker9',3,8)]:
        before=(old_edges[b]-old_edges[a])*1000
        after=(new_edges[b]-new_edges[a])*1000
        records[name]={'prior_ms':before,'current_ms':after,'observed_reduction_ms':before-after}
    for name,index in [('reset_release_to_first_strobe_irq',1),
                       ('reset_release_to_first_frame_irq',2),
                       ('reset_release_to_awake_checkpoint',9)]:
        before=(old_edges[index]-old['observed_reset_release_s'])*1000
        after=(new_edges[index]-new['reset_release_s'])*1000
        records[name]={'prior_ms':before,'current_ms':after,
                      'observed_reduction_ms':before-after}
    prior=evidence['prior_save'];current=new['save_fine_timing']
    return {'schema':1,'prior':'v60c awake IMG00061.PNG','current':'v64 normal awake IMG00067.PNG',
        'same_frame':False,'controlled_profile_only_comparison':False,
        'external_saleae_intervals':records,
        'nominal_400MHz_save_complete':{'prior_ms':prior['seconds']['complete']*1000,
            'current_ms':current['complete_ms']},
        'png_bytes':{'prior':prior['png_bytes'],'current':current['png_bytes']},
        'input_sha256':{k:v['sha256'] for k,v in spec['artifacts'].items()},
        'limits':['Both external timelines use source-order labels; strict pulse-width qualification remains false.',
                  'STROBE and frame markers are interrupt observations, not exact exposure edges; interrupt latency remains included.',
                  'These are different cold captures, firmware layouts and frame contents. Differences are observations, not a controlled causal benchmark.',
                  'The prior post-commit phase includes diagnostic scans/checks; the normal profile retains essential checks and explicitly skips those bulk diagnostics.',
                  'External Saleae milliseconds and nominal-400MHz DWT milliseconds are separate time bases and are not added.',
                  'Awake current does not independently reveal completion; no complete-cycle energy is assigned to either trial.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=analyze(args.spec)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['external_saleae_intervals'],indent=2))
