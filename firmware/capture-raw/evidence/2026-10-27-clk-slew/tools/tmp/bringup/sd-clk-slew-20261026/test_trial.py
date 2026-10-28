"""Offline trial guard tests; no instrument API or real subprocess is called."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('clk_trial_under_test', HERE/'run_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def operation(manifest, number=1, slot=4, offset=0, count=512):
    return dict(passed=True, binary_sha256=manifest['binary_sha256'], request_words=[],
        proof=dict(operation=number, slot=slot, result=0, media_idle=1, initialized=0,
            controller_owned=0, cleanup_error=0, read_lba=slot*trial.SECTORS+offset,
            read_count=count),
        card=dict(media_idle=1, initialized=0, controller_owned=0, cleanup_error=0,
            error=0, clock_hz=25000000, sector_count=122507264,
            cid0=83, cid1=1146433824, cid2=269787418, cid3=1979815748,
            bus_width_proof=dict(negotiated_width=4, configured_clkcr=0x34003),
            clk_gpio_speed_proof=dict(magic=0x314B4C43,version=1,
                requested_speed=manifest['sd_clk_gpio_speed'],clk_mask=0x30,c_mask=0xFF3,e_mask=0x300,
                applied=1,c_before=0,c_configured=0xFF3,
                c_after=(0xFF3&~0x30)|(manifest['sd_clk_gpio_speed']<<4),e_before=0,e_after=0x300)))


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='clk-trial-offline-')
        self.root = Path(self.temporary.name)
        self.args = SimpleNamespace(build=self.root/'build', out=self.root/'out',
            prior=None, recovery_build=self.root/'installed', execute=True)
        self.manifest = dict(binary_sha256='test-image', sd_clk_gpio_speed=2, cycle_trace=False)
        self.bench = SimpleNamespace(validate=Mock())

    def tearDown(self):
        self.temporary.cleanup()

    def test_plan_only_never_invokes_subprocess_or_creates_output(self):
        self.args.execute = False
        with patch.object(trial, 'admission', return_value=(self.manifest, self.bench)), \
                patch.object(trial.subprocess, 'run') as command, \
                contextlib.redirect_stdout(io.StringIO()):
            plan = trial.run(self.args)
        command.assert_not_called()
        self.assertFalse(self.args.out.exists())
        self.assertFalse(plan['execute'])
        self.assertFalse(plan['automatic_retry'])

    def test_existing_output_rejected_before_loading_build(self):
        self.args.out.mkdir()
        with patch.object(trial, 'load') as loader:
            with self.assertRaisesRegex(ValueError, 'existing trial'):
                trial.admission(self.args)
        loader.assert_not_called()

    def test_ambiguous_or_missing_source_rejected(self):
        for prior, recovery in ((None, None), (self.root/'prior.json', self.root/'installed')):
            self.args.prior, self.args.recovery_build = prior, recovery
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                trial.admission(self.args)

    def test_failed_park_stops_with_artifacts_and_no_retry(self):
        failure = subprocess.CalledProcessError(1, ['mock-only'])
        with patch.object(trial, 'admission', return_value=(self.manifest, self.bench)), \
                patch.object(trial.subprocess, 'run', side_effect=failure) as command, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                trial.run(self.args)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.kwargs['timeout'], 90)
        failed = trial.read(self.args.out/'failed.json')
        self.assertEqual(failed['stage'], 'park')
        self.assertIsNone(failed['original_frame'])
        self.assertTrue(failed['failed_stage_is_not_idle_proof'])
        self.assertFalse((self.args.out/'summary.json').exists())

    def test_capture_timeout_stops_preserves_partial_frame_and_flags_child_risk(self):
        frame = b'partially-downloaded-camera-data'
        def fake(command, **kwargs):
            if 'capture' in command:
                target = self.args.out/'capture/frame.bin'
                target.parent.mkdir()
                target.write_bytes(frame)
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return SimpleNamespace(returncode=0)
        with patch.object(trial, 'admission', return_value=(self.manifest, self.bench)), \
                patch.object(trial.subprocess, 'run', side_effect=fake) as command, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.TimeoutExpired):
                trial.run(self.args)
        self.assertEqual(command.call_count, 2)
        failed = trial.read(self.args.out/'failed.json')
        self.assertEqual(failed['stage'], 'capture')
        self.assertEqual(failed['original_frame']['sha256'], hashlib.sha256(frame).hexdigest())
        self.assertTrue(failed['timeout_may_leave_child_programmer'])
        self.assertFalse((self.args.out/'readback').exists())

    def test_operation_rejects_width_clock_identity_and_ownership_changes(self):
        clean = operation(self.manifest)
        identity = trial.check_operation(clean, self.manifest, self.bench)
        bads = []
        for key, value in (('clock_hz',12500000), ('error',14), ('cleanup_error',10),
                           ('media_idle',0), ('controller_owned',1), ('cid0',99)):
            candidate = operation(self.manifest)
            candidate['card'][key] = value
            bads.append(candidate)
        candidate = operation(self.manifest)
        candidate['card']['bus_width_proof']['configured_clkcr'] = 0x24003
        bads.append(candidate)
        for candidate in bads:
            with self.assertRaises(ValueError):
                trial.check_operation(candidate, self.manifest, self.bench, identity)

    def test_gpio_proof_rejects_wrong_clk_or_other_pin_changes(self):
        for key, value in (('requested_speed',3), ('c_after',0xFF3), ('e_after',0x100),
                           ('c_before',0x10000), ('applied',0), ('magic',0)):
            proof = operation(self.manifest)
            proof['card']['clk_gpio_speed_proof'][key] = value
            with self.assertRaisesRegex(ValueError,'CLK-only GPIO'):
                trial.check_operation(proof,self.manifest,self.bench)

    def prepare_artifacts(self):
        out = self.args.out
        frame = bytes(range(256))*(trial.FRAME_BYTES//256) + bytes(range(trial.FRAME_BYTES%256))
        (out/'capture').mkdir(parents=True)
        (out/'capture/frame.bin').write_bytes(frame)
        capture = operation(self.manifest)
        capture['frame_sha256'] = hashlib.sha256(frame).hexdigest()
        dump(out/'capture/verified.json', capture)
        obj = b'GXR2'+bytes(152)+frame+b'GXRE'
        for offset in range(0, trial.SECTORS, 512):
            count = min(512,trial.SECTORS-offset)
            part = out/f'readback/payload-{offset:04d}'
            part.mkdir(parents=True)
            data = obj[offset*512:(offset+count)*512]
            (part/'sectors.bin').write_bytes(data)
            proof = operation(self.manifest, 3, offset=offset, count=count)
            proof['read_sha256'] = hashlib.sha256(data).hexdigest()
            dump(part/'verified.json',proof)
        (out/'readback/slot.bin').write_bytes(obj)
        (out/'readback/scene.png').write_bytes(b'fake-offline-png')
        dump(out/'readback/scr-source.json',{})
        dump(out/'readback/readback-validation.json',{})
        dump(out/'readback/summary.json',dict(prior=str(out/'readback/payload-3584/verified.json')))
        reader = SimpleNamespace(validate=Mock(return_value=dict(passed=True,
            original_sensor_frame_comparison=True,
            source_reference_comparison=dict(bytes_equal=True),png_samples_match_read_raw=True)))
        return reader

    def test_full_object_and_all_eight_chunks_verified(self):
        reader = self.prepare_artifacts()
        with patch.object(trial,'load',return_value=reader):
            report = trial.verify_artifacts(self.args.out,self.manifest,self.bench)
        self.assertTrue(report['entire_object_equal'])
        self.assertEqual(report['object_bytes'],trial.SECTORS*512)
        self.assertEqual(len(report['read_proofs']),8)
        reader.validate.assert_called_once()

    def test_reserved_metadata_corruption_rejected_even_when_chunks_and_hashes_agree(self):
        reader = self.prepare_artifacts()
        out = self.args.out
        obj = bytearray((out/'readback/slot.bin').read_bytes())
        obj[5] = 55
        (out/'readback/slot.bin').write_bytes(obj)
        part = out/'readback/payload-0000'
        (part/'sectors.bin').write_bytes(obj[:512*512])
        proof = trial.read(part/'verified.json')
        proof['read_sha256'] = trial.sha(part/'sectors.bin')
        dump(part/'verified.json',proof)
        with patch.object(trial,'load',return_value=reader):
            with self.assertRaisesRegex(ValueError,'Entire stored object'):
                trial.verify_artifacts(out,self.manifest,self.bench)
        reader.validate.assert_not_called()

    def test_wrong_readback_lba_rejected(self):
        self.prepare_artifacts()
        path=self.args.out/'readback/payload-0512/verified.json'
        proof=trial.read(path)
        proof['proof']['read_lba']+=1
        dump(path,proof)
        with self.assertRaisesRegex(ValueError,'coverage differs'):
            trial.verify_artifacts(self.args.out,self.manifest,self.bench)

    def test_png_verification_is_required(self):
        reader=self.prepare_artifacts()
        reader.validate.return_value['png_samples_match_read_raw']=False
        with patch.object(trial,'load',return_value=reader):
            with self.assertRaisesRegex(ValueError,'PNG verification'):
                trial.verify_artifacts(self.args.out,self.manifest,self.bench)

    def test_success_sequence_is_bounded_and_final_idle_is_required(self):
        reader=self.prepare_artifacts()
        # Move prepared mock artifacts away: run refuses an existing output.
        prepared=self.root/'prepared'
        self.args.out.rename(prepared)
        def fake(command, **kwargs):
            self.assertGreater(kwargs['timeout'],0)
            if 'capture' in command:
                import shutil
                shutil.copytree(prepared/'capture',self.args.out/'capture')
            elif 'read-slots' in command:
                import shutil
                shutil.copytree(prepared/'readback',self.args.out/'readback')
            elif str(command[1]).endswith('fresh_idle.py'):
                dump(self.args.out/'final-idle/verified.json',dict(passed=True))
            return SimpleNamespace(returncode=0)
        with patch.object(trial,'admission',return_value=(self.manifest,self.bench)), \
                patch.object(trial,'load',return_value=reader), \
                patch.object(trial.subprocess,'run',side_effect=fake) as command, \
                contextlib.redirect_stdout(io.StringIO()):
            result=trial.run(self.args)
        self.assertTrue(result['passed'])
        self.assertEqual(command.call_count,4) # park,capture,readback,fresh idle
        self.assertTrue((self.args.out/'summary.json').is_file())
        self.assertFalse((self.args.out/'failed.json').exists())


if __name__=='__main__':
    unittest.main()
