"""Read-only integrity check of this compact, image-free experiment archive."""
import hashlib
import json
from pathlib import Path


def verify(root):
    root=Path(root).resolve()
    count=0
    for name in ('baseline-index.json','candidate-index.json'):
        for item in json.loads((root/name).read_text())['files']:
            path=(root/item['path']).resolve()
            assert path.is_relative_to(root)
            data=path.read_bytes()
            assert len(data)==item['bytes']
            assert hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
            count+=1
    q=json.loads((root/'qualification.json').read_text())
    assert q['tests_passed']==26 and q['sanitizer_actual_c_cases']==648
    assert q['hardware_access'] is False and q['selected_save_mode_changed'] is False
    for key,name in [('candidate_index_sha256','candidate-index.json'),('baseline_index_sha256','baseline-index.json')]:
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==q[key]
    report=json.loads((root/'host-screen.json').read_text())
    assert report['private_raw_included'] is False and report['hardware_access'] is False
    assert len(report['records'])==48 and all(r['exact_pixels'] for r in report['records'])
    replay=json.loads((root/'portable-check.json').read_text())
    assert replay['passed'] and replay['synthetic_variant_records']==32 and not replay['timing_reproduction_claimed']
    return {'passed':True,'source_files_checked':count,'host_screen_records':48,
            'portable_synthetic_records':32,'hardware_access':False}


if __name__=='__main__':print(json.dumps(verify(Path(__file__).parent),indent=2))
