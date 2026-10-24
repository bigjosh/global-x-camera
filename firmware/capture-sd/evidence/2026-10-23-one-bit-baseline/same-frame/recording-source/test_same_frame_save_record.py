"""Mock-only recorder ordering, cleanup and no-power-command checks."""
from contextlib import redirect_stdout
import io,json
from pathlib import Path
import subprocess,sys,tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import same_frame_save_record as run

class FakeOwner:
    def __init__(self,out,events):self.out=out;self.events=events
    def start(self):self.events.append('js-start');self.out.mkdir()
    def stop(self):self.events.append('js-stop')
    def command(self,*a):raise AssertionError('No power/control commands permitted')

class FakeAPI:
    LogicDeviceConfiguration=SimpleNamespace;CaptureConfiguration=SimpleNamespace
    ManualCaptureMode=SimpleNamespace
    def __init__(self,events,fail_start=False,fail_stop=False):
        self.events=events;self.fail_start=fail_start;self.fail_stop=fail_stop
        self.Manager=SimpleNamespace(connect=self.connect)
    def connect(self,**kwargs):self.events.append('connect');return self
    def __enter__(self):return self
    def __exit__(self,*a):self.events.append('close')
    def get_devices(self):return [SimpleNamespace(device_id=run.DEVICE,is_simulation=False)]
    def start_capture(self,**kwargs):
        self.events.append('capture-start');self.config=kwargs
        if self.fail_start:raise RuntimeError('start failed')
        return self
    def stop(self):
        self.events.append('capture-stop')
        if self.fail_stop:raise RuntimeError('stop failed')
    def wait(self):raise AssertionError('Manual mode must not call wait')
    def save_capture(self,path):self.events.append('save-capture');Path(path).write_bytes(b'mock')
    def export_raw_data_binary(self,path,**kwargs):
        self.events.append('export')
        for ch in kwargs['digital_channels']:(Path(path)/f'digital_{ch}.bin').write_bytes(b'mock')

class Tests(unittest.TestCase):
    def run_case(self,code=0,raises=False,fail_start=False,fail_stop=False):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        out=Path(td.name)/'new';events=[];owner=FakeOwner(out,events)
        api=FakeAPI(events,fail_start,fail_stop)
        def runner(command,output):
            events.append('bench')
            if raises:raise RuntimeError('bench timeout; remains active')
            return code
        return out,events,owner,api,runner
    def test_order_and_manual_configuration(self):
        out,e,o,a,r=self.run_case();run.record(o,out,['guarded-save'],api=a,runner=r)
        self.assertEqual(e,['js-start','connect','capture-start','bench','capture-stop','js-stop','save-capture','export','close','close'])
        self.assertEqual(a.config['device_configuration'].enabled_digital_channels,[0,1,4,6])
        self.assertEqual(a.config['device_configuration'].digital_sample_rate,100000000)
        result=json.loads((out/'recording-result.json').read_bytes())
        self.assertTrue(result['guarded_save_process_succeeded'])
        self.assertFalse(result['image_integrity_verified'])
        self.assertFalse(result['power_switch_sent'])
    def test_failed_bench_still_stops_and_preserves_capture_no_retry(self):
        for kw in (dict(code=1),dict(raises=True)):
            out,e,o,a,r=self.run_case(**kw)
            with self.subTest(kw=kw),self.assertRaises(RuntimeError):run.record(o,out,[],api=a,runner=r)
            self.assertEqual(e.count('bench'),1);self.assertEqual(e.count('js-stop'),1)
            self.assertEqual(e.count('capture-stop'),1);self.assertIn('export',e)
    def test_capture_start_failure_prevents_save_and_restores_owner(self):
        out,e,o,a,r=self.run_case(fail_start=True)
        with self.assertRaisesRegex(RuntimeError,'start failed'):run.record(o,out,[],api=a,runner=r)
        self.assertNotIn('bench',e);self.assertEqual(e.count('js-stop'),1)
    def test_stop_failure_never_retries_stop_or_exports(self):
        out,e,o,a,r=self.run_case(fail_stop=True)
        with self.assertRaisesRegex(RuntimeError,'stop failed'):run.record(o,out,[],api=a,runner=r)
        self.assertEqual(e.count('capture-stop'),1);self.assertEqual(e.count('js-stop'),1)
        self.assertNotIn('export',e)
    def test_timeout_does_not_kill_bench(self):
        with tempfile.TemporaryDirectory() as td:
            proc=SimpleNamespace(pid=123,wait=lambda **kw:(_ for _ in ()).throw(subprocess.TimeoutExpired('bench',180)))
            with patch.object(subprocess,'Popen',return_value=proc),self.assertRaisesRegex(RuntimeError,'remains active'):
                run.run_bench(['dummy'],Path(td))
            self.assertTrue((Path(td)/'bench-process-timeout.json').is_file())
    def test_dryrun_no_process_or_output(self):
        out=run.ROOT/'tmp'/'same-frame-offline-nonexistent-test';self.assertFalse(out.exists())
        with patch.object(sys,'argv',['runner','--out',str(out)]), \
             patch.object(subprocess,'Popen',side_effect=AssertionError('No process')),redirect_stdout(io.StringIO()):
            self.assertEqual(run.main(),0)
        self.assertFalse(out.exists());run.owner_module()

if __name__=='__main__':unittest.main()
