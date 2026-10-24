"""Independent offline tests; does not call any bench/hardware API."""
import copy
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('packed_capture_audit_target', HERE/'run_capture.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture(mode=0):
    code = bytearray(64)
    struct.pack_into('<II', code, 0, 0x343B0000, runner.LOAD+9)
    code[32:34] = b'\xfe\xe7'
    code[34:36] = b'\xfe\xe7'
    digest = hashlib.sha256(code).hexdigest()
    manifest = dict(schema=1, load=runner.LOAD, stack=0x343B0000,
        entry=runner.LOAD+9, request=runner.REQUEST, proof=runner.PROOF,
        proof_words=40, frame=runner.FRAME, width=1120, height=1364,
        sd_commands=False, nor_commands=False, sensor_reset=True,
        cold_start_measurement=False, installed_recovery_unchanged=True,
        mode=mode, pattern=1, frame_bytes=1120*1364*(5 if mode else 8)//4,
        park=runner.LOAD+32, reject_park=runner.LOAD+34,
        data_start=runner.LOAD+60,data_begin=runner.LOAD+60,
        system_core_clock=runner.LOAD+60,data_end=runner.LOAD+64,
        bss_end=runner.LOAD+128,stack_floor=0x343AF000,
        allocation_bytes=3055360,
        binary_bytes=len(code), binary_sha256=digest,
        source_hashes={'example.c':hashlib.sha256(b'example').hexdigest()})
    return manifest, bytes(code), digest


def valid_proof(manifest, nonce=123):
    proof = dict.fromkeys(runner.FIELDS, 0)
    proof.update(magic=runner.MAGIC, schema=1, words=40, nonce=nonce,
        mode=manifest['mode'], pattern=manifest['pattern'], state=3,
        expected_bytes=manifest['frame_bytes'], dma_bytes=manifest['frame_bytes'],
        frame=runner.FRAME, width=1120, height=1364, frames=1,
        sensor_format=10, sensor_dt=0x30 if manifest['mode'] else 0x2B,
        p0fscr=0x30 if manifest['mode'] else 0x2B,
        vc0cfgr1=0x201 if manifest['mode'] else 0x301,
        reset_end=40800,pattern_register=0x121 if manifest['pattern'] else 0,
        primask=1,cpacr=0, terminal=runner.DONE)
    return proof


class RunnerAudit(unittest.TestCase):
    def check_fixture(self, manifest, code, digest):
        with tempfile.TemporaryDirectory(prefix='raw10-runner-offline-', dir=HERE) as name:
            folder = Path(name)
            (folder/'capture.bin').write_bytes(code)
            (folder/'manifest.json').write_text(json.dumps(manifest))
            (folder/'example.c').write_bytes(b'example')
            return runner.checked_build(folder, digest)

    def test_valid_modes_and_field_wire_order(self):
        self.assertEqual(len(runner.FIELDS),40)
        for mode in (0,1):
            m,c,d = fixture(mode)
            self.assertEqual(self.check_fixture(m,c,d),(m,c))
            proof = valid_proof(m)
            wire = struct.pack('<40I',*(proof[k] for k in runner.FIELDS))
            self.assertEqual(runner.decode(wire),proof)
            runner.validate(proof,m,123)

    def test_truncated_and_extended_proof(self):
        for size in (0,156,159,161,164):
            with self.subTest(size=size), self.assertRaises(ValueError):
                runner.decode(bytes(size))

    def test_corrupt_code_digest_and_source(self):
        m,c,d=fixture()
        with self.assertRaises(ValueError): self.check_fixture(m,c[:-1]+b'x',d)
        with self.assertRaises(ValueError): self.check_fixture(m,c,'0'*64)
        m['source_hashes']['example.c']='0'*64
        with self.assertRaises(ValueError): self.check_fixture(m,c,d)

    def test_scope_layout_rejections(self):
        m,c,d=fixture()
        for key,value in dict(load=0x34000000,stack=0x341B8000,
            request=runner.PROOF,proof=runner.FRAME,proof_words=39,
            frame_bytes=1,mode=2,pattern=2,sd_commands=True,nor_commands=True,
            sensor_reset=False,installed_recovery_unchanged=False,
            cold_start_measurement=True,allocation_bytes=1909600,
            data_start=runner.LOAD,system_core_clock=runner.LOAD+56,
            bss_end=0x343B1000,stack_floor=0x34300001).items():
            altered=copy.deepcopy(m);altered[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check_fixture(altered,c,d)

    def test_park_rejections(self):
        m,c,d=fixture()
        for key in ('park','reject_park'):
            for value in (runner.LOAD-2,runner.LOAD+len(c),runner.LOAD+8):
                altered=copy.deepcopy(m);altered[key]=value
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    self.check_fixture(altered,c,d)

    def test_terminal_and_capture_contract(self):
        m,_,_=fixture()
        for key,value in dict(nonce=124,state=2,result=1,terminal=0,frames=2,
            errors=1,dma_bytes=1,canary_mask=1,sensor_format=8,sensor_dt=0x30,
            control=4,ipsr=1,primask=0,cpacr=0xF00000,pattern_register=0).items():
            proof=valid_proof(m);proof[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.validate(proof,m,123)

    def test_cache_fp_and_tick_rejections(self):
        m,_,_=fixture()
        for key,value in [('ccr',0x10000),('ccr',0x20000),('fpccr',1),
                           ('systick',1),('systick',2)]:
            proof=valid_proof(m);proof[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                runner.validate(proof,m,123)

    def test_pipe_and_sensor_reset_checks(self):
        m,_,_=fixture()
        for key,value in [('p0ppcr',0x20),('p0fctcr',8),('cmsr1',0x8000),
                           ('csi_sr0',0x20000),('p0fscr',0x30),
                           ('vc0cfgr1',0x201),('reset_end',40799)]:
            proof=valid_proof(m);proof[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                runner.validate(proof,m,123)

    def test_sensor_reset_wrap_is_accepted(self):
        m,_,_=fixture()
        proof=valid_proof(m)
        proof['reset_begin']=0xfffff000
        proof['reset_end']=(proof['reset_begin']+40800)&0xffffffff
        runner.validate(proof,m,123)

    def test_real_frozen_builds(self):
        builds=list((HERE/'experiment').glob('*-v4/manifest.json'))
        self.assertTrue(builds,'Need finished reviewed build manifests')
        for path in builds:
            m=json.loads(path.read_text())
            with self.subTest(build=path.parent.name):
                checked,_=runner.checked_build(path.parent,m['binary_sha256'])
                self.assertEqual(m,checked)

    def test_saved_native_v4_terminal_proof(self):
        m=json.loads((HERE/'experiment/native10-diagonal-v4/manifest.json').read_text())
        proof=json.loads((HERE/'bench/native-pattern02/proof.json').read_text())
        runner.validate(proof,m,proof['nonce'])
        self.assertEqual(proof['control'],0)
        self.assertEqual(proof['cpacr'],0)

    def test_actual_inline_owned_context_guard(self):
        # Exercise the real runner's inline guard without invoking main or a bench.
        tree=ast.parse((HERE/'run_capture.py').read_text())
        clauses=[node for node in ast.walk(tree) if isinstance(node,ast.If)
                 and any(isinstance(v,ast.Constant) and
                         v.value=='Capacity guard or owned context cleanup proof differs'
                         for child in node.body for v in ast.walk(child))]
        self.assertEqual(len(clauses),1)
        guard=compile(ast.fix_missing_locations(ast.Module(body=clauses,type_ignores=[])),
                      '<real-runner-context-guard>','exec')
        raw=[0]*19
        raw[14]=12;raw[15]=0xC000001C;raw[16]=0xF00000
        raw[17]=0x343AF000;raw[18]=0x343AFFA0
        for control in (0,4,8,12):
            good=list(raw);good[14]=control
            exec(guard,{'raw_proof':good})
        for index,value in [(10,1),(14,1),(14,2),(14,16),(15,1),
                            (16,0),(17,0x341B6000),(18,0x343AF000),
                            (18,0x343B0004)]:
            bad=list(raw);bad[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                exec(guard,{'raw_proof':bad})

    def test_live_cpacr_guard(self):
        tree=ast.parse((HERE/'run_capture.py').read_text())
        clauses=[node for node in ast.walk(tree) if isinstance(node,ast.If)
                 and any(isinstance(v,ast.Constant) and v.value=='FP/MVE access was not released'
                         for child in node.body for v in ast.walk(child))]
        self.assertEqual(len(clauses),1)
        guard=compile(ast.fix_missing_locations(ast.Module(body=clauses,type_ignores=[])),
                      '<real-runner-cpacr-guard>','exec')
        exec(guard,{'live_cpacr':0})
        for value in (1,0x300000,0xF00000):
            with self.subTest(value=value),self.assertRaises(ValueError):
                exec(guard,{'live_cpacr':value})


if __name__=='__main__':
    unittest.main(verbosity=2)
