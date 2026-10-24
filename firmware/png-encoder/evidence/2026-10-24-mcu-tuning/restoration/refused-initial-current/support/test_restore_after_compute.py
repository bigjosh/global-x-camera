"""No-device sequencing tests for the one-shot compute teardown."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import restore_after_compute as run

sys.path.insert(0,str(run.COLD.parent))
from test_single_cycle import Clock,Owner
from test_phase_cold_cycle import Phase
from single_cycle import fresh_sample

ACTUAL=run.ROOT/'tmp/bringup/png-tune-20261024/mve-pair-o2-hardware'

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter=run.load(run.ADAPTER,'restore_test_adapter',run.ADAPTER_SHA)
        cls.bound=run.checked_run(ACTUAL,cls.adapter)
        cls.protocol=cls.adapter.p
    def raw(self,report):
        p=self.protocol
        return struct.pack('<44I14Q56I',*[report[k] for k in p.U32+p.U64+p.TAIL])
    def bench(self,report=None,request=None,context_error=False):
        report=report or self.bound['last']['report'];calls=[]
        command=self.bound['request'] if request is None else request
        def upload(address,n,name):
            calls.append(('upload',name))
            if address==self.protocol.REPORT:return self.raw(report)
            if address==self.protocol.REQUEST:return command
            raise AssertionError('Unexpected target access')
        def exact(b,code,park,label):
            calls.append(('halt-context',park))
            if context_error:raise ValueError('bad live context')
            return dict(cpacr=report['reserved7'])
        adapter=SimpleNamespace(p=self.protocol,LOAD=self.adapter.LOAD,exact_code_context=exact)
        return SimpleNamespace(upload=upload),adapter,calls
    def test_real_last_proof_and_candidate_validate_offline(self):
        m,code=self.adapter.checked_build(run.BUILD,run.MODULE_SHA)
        self.assertEqual(len(code),20976)
        self.assertEqual(self.bound['last']['repeat'],3)
        self.assertEqual(self.bound['last']['report']['mode'],3)
        self.assertEqual(run.sha_file(run.COLD),run.COLD_SHA)
        for path,digest in run.PINNED.items():self.assertEqual(run.sha_file(path),digest)
    def test_fresh_report_request_before_halt_and_rechecked(self):
        b,a,calls=self.bench();proof=run.fresh_compute(b,a,b'fake-code',self.bound)
        self.assertEqual(calls,[('upload','fresh-report.bin'),('upload','fresh-request.bin'),
            ('halt-context',0x3432003c),('upload','confirmed-report.bin'),('upload','confirmed-request.bin')])
        self.assertEqual(proof['start_kind'],'compute-completed')
    def test_stale_failed_nonce_or_request_never_halts(self):
        original=self.bound['last']['report']
        for field,value in [('nonce',original['nonce']^1),('result',2),('terminal',0),('mode',1),('reserved6',0)]:
            report=deepcopy(original);report[field]=value;b,a,calls=self.bench(report)
            with self.subTest(field=field),self.assertRaises(ValueError):run.fresh_compute(b,a,b'x',self.bound)
            self.assertFalse(any(k=='halt-context' for k,v in calls))
        b,a,calls=self.bench(request=bytes(64))
        with self.assertRaisesRegex(ValueError,'request/nonce'):run.fresh_compute(b,a,b'x',self.bound)
        self.assertFalse(any(k=='halt-context' for k,v in calls))
    def test_exact_context_failure_cannot_produce_safe_start(self):
        b,a,calls=self.bench(context_error=True)
        with self.assertRaisesRegex(ValueError,'bad live context'):run.fresh_compute(b,a,b'x',self.bound)
        self.assertEqual(calls[-1][0],'halt-context')
    def test_changed_pertrial_proof_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);trial=folder/'mode-3-run-03';trial.mkdir()
            for name in ('plan.json','verified.json'):shutil.copyfile(ACTUAL/name,folder/name)
            for name in ('verified.json','request.bin','completed-request.bin'):
                shutil.copyfile(ACTUAL/'mode-3-run-03'/name,trial/name)
            altered=run.read(trial/'verified.json');altered['report']['nonce']^=1
            run.dump(trial/'verified.json',altered)
            with self.assertRaisesRegex(ValueError,'differs from aggregate'):run.checked_run(folder,self.adapter)
    def state(self,**kwargs):
        c=Clock();o=Owner(c,initial=kwargs.pop('initial',.08),**kwargs);p=Phase(c,o)
        proof=dict(start_kind='compute-completed',nonce=123,verified_monotonic_ns=int(c.now()*1e9))
        return c,o,p,proof
    def perform(self,c,o,p,proof):
        return run.perform_cycle(o,p,proof,fresh=fresh_sample,clock=c.now,sleep=c.sleep)
    def test_exact_one_cycle_15s_off_phase_then_six_distinct_quiet(self):
        c,o,p,proof=self.state();result=self.perform(c,o,p,proof)
        self.assertEqual([k for k,t in o.commands],['off','auto'])
        self.assertGreaterEqual(o.commands[1][1]-o.commands[0][1],15.25)
        self.assertLessEqual(p.started,o.commands[1][1])
        self.assertEqual(len({s['sequence'] for s in result['terminal_statistics']}),6)
        for k in ('terminal_state_qualified','image_integrity_verified','sbf_verified'):self.assertIs(result[k],False)
    def test_invalid_expired_or_unstable_start_never_switches(self):
        for mode in ('wrongkind','expired','badcurrent','stale'):
            c,o,p,proof=self.state(initial=.3 if mode=='badcurrent' else .08,stale=mode=='stale')
            if mode=='wrongkind':proof['start_kind']='nor-maintenance-complete'
            if mode=='expired':proof['verified_monotonic_ns']-=61_000_000_000
            with self.subTest(mode=mode),self.assertRaises((ValueError,RuntimeError)):self.perform(c,o,p,proof)
            self.assertEqual(o.commands,[])
    def test_off_or_phase_failure_never_explicit_auto_or_retry(self):
        for mode in ('off','phase'):
            c,o,p,proof=self.state(off_zero=mode!='off');p.fail=mode=='phase'
            with self.subTest(mode=mode),self.assertRaises(RuntimeError):self.perform(c,o,p,proof)
            self.assertEqual([k for k,t in o.commands],['off'])
    def test_absent_active_or_quiet_never_second_cycle(self):
        for mode in ('never-active','never-idle'):
            c,o,p,proof=self.state(on=mode)
            with self.subTest(mode=mode),self.assertRaisesRegex(RuntimeError,'never retry'):self.perform(c,o,p,proof)
            self.assertEqual([k for k,t in o.commands],['off','auto'])
    def test_dryrun_no_process_or_output(self):
        path=run.ROOT/'tmp/restore-after-compute-dryrun-must-not-exist'
        self.assertFalse(path.exists())
        with patch.object(sys,'argv',['restore','--compute-run','missing','--out',str(path)]), \
            patch.object(subprocess,'Popen',side_effect=AssertionError('No process allowed')), \
            redirect_stdout(io.StringIO()):self.assertEqual(run.main(),0)
        self.assertFalse(path.exists())

if __name__=='__main__':unittest.main()
