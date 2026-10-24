"""Archive closed v66c cold cycles without reading large raw recordings."""
from pathlib import Path
import hashlib,json
from archive_installation import HERE, copy_groups, read

SECTOR='8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'
PREFIX='247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58'
def sha(raw):return hashlib.sha256(raw).hexdigest()

def archive(run):
    root=copy_groups(run,[run+'-cycle',run+'-vcp',run+'-park',run+'-sbf'])
    cycle=read(root/(run+'-cycle/result.json'))
    sbf=read(root/(run+'-sbf/result.json'))
    park=read(root/(run+'-park/result.json'))
    assert cycle['recording_complete'] and cycle['sector_sha256']==SECTOR
    assert cycle['phase_decode_passed'] is False
    assert park['passed'] and park['prefix_sha256']==PREFIX
    assert park['vcp_status']['request']==1 and park['vcp_status']['bad_pulses']==0
    assert sbf['passed'] and sbf['sbf'] and sbf['trial_entry_proven'] is False
    assert sbf['prefix_sha256']==PREFIX
    assert sbf['fresh_park_result_sha256']==sha((root/(run+'-park/result.json')).read_bytes())
    for name in ('reset_or_power_changed','ram_writes','nor_commands','cpucr_written'):
        assert sbf[name] is False
    attestation=HERE.parent/'analysis/records'/run/'phase-spec.json'
    spec=read(attestation)
    assert spec['owner_attests_no_intervening_poweroff'] is True
    summary=dict(run=run,build='v66c-normal-standby',sector_sha256=SECTOR,
        recording_closed=True,strict_marker_width_qualification=False,
        first_attempt_warm_uart_recovery=True,exact_recovery_park=True,
        sbf_observed=True,original_sbf_trial_entry_proven=False,
        original_sbf_result=run+'-sbf/result.json',
        owner_attestation_reference='../../analysis/records/'+run+'/phase-spec.json',
        owner_attestation_sha256=sha(attestation.read_bytes()),
        owner_reported_history='Exact v66c stayed installed; no SWD during capture/plateau; warm UART recovery and SBF read followed the plateau with no intervening power-off',
        interpretation='Bind observed SBF to this cycle only through the separately recorded hardware-owner history; original reader result remains conservative',
        png_readback_verified_here=False,image_contents_archived=False,raw_streams_archived=False,
        hardware_accessed_by_archiver=False)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return dict(run=run,indexed_files=len(read(root/'index.json')['files']),sbf_observed=True)

if __name__=='__main__':
    print(json.dumps([archive(x) for x in ('standby02','standby03','standby04')],indent=2))
