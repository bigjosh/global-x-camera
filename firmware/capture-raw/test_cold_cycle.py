"""No-device binding and power-state regression tests for RAW cold recording."""
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import cold_cycle as cycle
import phase_decode
from phase_protocol import PHASE_PROTOCOL, LEGACY_PROTOCOL


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.build=self.root/'build'
        staged=self.build/'staged'; staged.mkdir(parents=True)
        self.now=datetime(2026,10,24,tzinfo=timezone.utc)
        late=dict(early_bytes=15804,after_arm=True,interrupts_enabled=True,
                  layout_audit=dict(vectors_early=True,early_irq_symbols=True))
        code=b'RAW receiver'; (self.build/'capture.bin').write_bytes(code)
        receiver=dict(kind='raw-slots',flash=True,standby=True,frame_bytes=1909600,
            binary_sha256=hashlib.sha256(code).hexdigest(),binary_bytes=len(code),
            phase_markers=PHASE_PROTOCOL,late_load=late)
        (self.build/'manifest.json').write_text(json.dumps(receiver))
        prefix=b'prefix'; (staged/'stage1.bin').write_bytes(prefix)
        sector=bytes(65536); (staged/'capture_sector_0.bin').write_bytes(sector)
        self.digest=hashlib.sha256(sector).hexdigest()
        self.staged=dict(program_sha256=self.digest,completion_policy='Standby after complete RAW slot',
            stage2_manifest_sha256=cycle.sha_file(self.build/'manifest.json'),
            stage2_full_sha256=receiver['binary_sha256'],late_load=late,
            stage1_raw_sha256=hashlib.sha256(prefix).hexdigest(),checked_recovery_literal_offsets=[1])
        (staged/'manifest.json').write_text(json.dumps(self.staged))
        evidence=self.root/'idle.json'; evidence.write_text('{"idle":true}')
        self.proof=dict(schema=1,bench_owner='root',start_kind='nor-maintenance-complete',
            observed_utc=self.now.isoformat(),safe_to_remove_power=True,nor_idle=True,
            storage_idle=True,no_active_clients=True,current_a=.075,input_voltage_v=4.9,
            sector_sha256=self.digest,evidence=[dict(path='idle.json',sha256=cycle.sha_file(evidence))])
        self.path=self.root/'proof.json'
    def validate(self):
        return cycle.validate_proof(self.path,self.build,now=self.now,raw=json.dumps(self.proof))
    def test_exact_build_and_root_idle_proof(self):
        self.assertEqual(self.validate()['sector_sha256'],self.digest)
        self.proof.update(start_kind='standby-plateau',current_a=.008)
        self.validate()
    def test_missing_idle_stale_or_forged_binding_rejected(self):
        for field,value in [('storage_idle',False),('nor_idle',False),('no_active_clients',False),
                ('bench_owner','other'),('sector_sha256','0'*64),
                ('observed_utc',(self.now-timedelta(seconds=601)).isoformat())]:
            original=self.proof[field]; self.proof[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): self.validate()
            self.proof[field]=original
    def test_modified_payload_or_evidence_rejected(self):
        (self.build/'capture.bin').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'receiver differs'): self.validate()
    def test_manifest_binding_required(self):
        p=self.build/'manifest.json'; data=json.loads(p.read_text()); data['standby']=False
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'protocol'): self.validate()
    def test_awake_requires_explicit_matching_build(self):
        path=self.build/'manifest.json'; data=json.loads(path.read_text()); data['standby']=False
        path.write_text(json.dumps(data))
        self.staged.update(completion_policy='Awake RAW terminal park',
            stage2_manifest_sha256=cycle.sha_file(path))
        (self.build/'staged/manifest.json').write_text(json.dumps(self.staged))
        with self.assertRaisesRegex(ValueError,'protocol'): self.validate()
        cycle.validate_proof(self.path,self.build,now=self.now,raw=json.dumps(self.proof),expected_end='awake')


class PhaseTests(unittest.TestCase):
    def write(self, folder, ids, malformed=False, step=2e-6, overhead=0.):
        times=[]
        for i,ident in enumerate(ids):
            at=.01+i*.001; times += [at,at+ident*step+overhead+(.6e-6 if malformed and i==0 else 0)]
        raw=struct.pack('<8siiIddQ',b'<SALEAE>',0,0,0,0.,1.,len(times))
        raw+=struct.pack('<'+'d'*len(times),*times)
        (folder/'digital_1.bin').write_bytes(raw)
    def test_concurrent_order_allowed_but_not_invented(self):
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path); self.write(folder,[1,4,2,3,5,6,7,8,9,10])
            self.assertTrue(phase_decode.summarize_folder(folder)['decode_passed'])
            self.write(folder,[1,4,2,3,5,6,7,8,9,10],malformed=True)
            result=phase_decode.summarize_folder(folder)
            self.assertFalse(result['decode_passed']); self.assertIsNone(result['pulses'][0]['event_id'])
    def test_commit_before_frame_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path); self.write(folder,[1,4,2,5,6,7,3,8,9,10])
            self.assertFalse(phase_decode.summarize_folder(folder)['decode_passed'])
    def test_awake_requires_nine_phases_and_no_pre_wfi(self):
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path); self.write(folder,[1,4,2,3,5,6,7,8,9])
            self.assertTrue(phase_decode.summarize_folder(folder,standby=False)['decode_passed'])
            self.assertFalse(phase_decode.summarize_folder(folder)['decode_passed'])
    def test_new_spacing_handles_measured_overhead_without_changing_legacy(self):
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path); ids=[1,2,4,3,5,6,7,8,9]
            self.write(folder,ids,step=.5e-6,overhead=.24e-6)
            result=phase_decode.summarize_folder(folder,standby=False,protocol=LEGACY_PROTOCOL)
            self.assertFalse(result['decode_passed'])
            self.assertTrue(all(p['event_id'] is None for p in result['pulses']))
            self.write(folder,ids,step=2e-6,overhead=.24e-6)
            self.assertTrue(phase_decode.summarize_folder(folder,standby=False)['decode_passed'])
            with self.assertRaisesRegex(ValueError,'Unknown'):
                phase_decode.summarize_folder(folder,protocol=dict(PHASE_PROTOCOL,pulse_width_tolerance_us=1.))


class NoDeviceTests(unittest.TestCase):
    def test_pinned_owner_and_dry_run(self):
        self.assertEqual(cycle.sha_file(cycle.OWNER_SOURCE),cycle.OWNER_SHA)
        self.assertEqual(cycle.owner_module().ROOT,cycle.ROOT)
        output=cycle.ROOT/'tmp/raw-cold-no-device-test'
        self.assertFalse(output.exists())
        with patch.object(sys,'argv',['cold','--out',str(output),'--build','missing',
                '--safe-start-proof','missing']), patch.object(subprocess,'Popen',
                side_effect=AssertionError('No process permitted')),redirect_stdout(io.StringIO()):
            self.assertEqual(cycle.main(),0)
        self.assertFalse(output.exists())


if __name__=='__main__': unittest.main()
