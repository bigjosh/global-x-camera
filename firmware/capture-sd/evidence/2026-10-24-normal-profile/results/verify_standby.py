"""Verify compact cold-cycle records and separate history binding; offline."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def verify(run):
    root=HERE/run;index=read(root/'index.json');summary=read(root/'summary.json')
    for entry in index['files']:
        path=(root/entry['archived_path']).resolve()
        assert path.is_relative_to(root.resolve())
        raw=path.read_bytes();assert len(raw)==entry['bytes'] and sha(raw)==entry['sha256']
        assert path.suffix.lower() not in ('.sal','.f32','.png')
    cycle=read(root/(run+'-cycle/result.json'))
    park=read(root/(run+'-park/result.json'))
    sbf=read(root/(run+'-sbf/result.json'))
    attestation=(root/summary['owner_attestation_reference']).resolve()
    assert attestation.is_relative_to(HERE.parent.resolve())
    assert sha(attestation.read_bytes())==summary['owner_attestation_sha256']
    assert read(attestation)['owner_attests_no_intervening_poweroff'] is True
    assert cycle['sector_sha256']==summary['sector_sha256']
    assert cycle['recording_complete'] and not cycle['phase_decode_passed']
    assert park['passed'] and park['vcp_status']['request']==1
    assert park['vcp_status']['bad_pulses']==0
    assert sbf['passed'] and sbf['sbf'] and not sbf['trial_entry_proven']
    assert sbf['fresh_park_result_sha256']==sha((root/(run+'-park/result.json')).read_bytes())
    assert not any(sbf[k] for k in ('cpucr_written','reset_or_power_changed','ram_writes','nor_commands'))
    assert summary['original_sbf_trial_entry_proven'] is False
    assert summary['strict_marker_width_qualification'] is False
    return dict(run=run,indexed_files=len(index['files']),sbf_observed=True,
                separate_owner_history_bound=True,original_reader_trial_entry_proven=False,
                image_decoding_replayed=False,hardware_accessed=False)

if __name__=='__main__':print(json.dumps([verify(x) for x in ('standby02','standby03','standby04')],indent=2))
