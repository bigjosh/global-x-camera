"""Offline guard tests. No instruments, programmer or physical disks accessed."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("capture_raw_bench_tested", HERE / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def words(op, nonce=1234, *args):
    return list(struct.unpack("<16I", bench.request(op, nonce, *args)))


def proof(operation):
    m = dict(card=0x3430C000, slots=0x3430C100, pattern=1,
             transport="idma", chunk_sectors=1024)
    p = {name: 0 for name in bench.fields(HERE)}
    p.update(magic=bench.MAGIC, schema=1, words=96, nonce=1234, operation=operation,
             state=3, result=0, stage=8, terminal=bench.DONE, frame=bench.FRAME,
             bytes=bench.FRAME_BYTES, width=1120, height=1364, card=m["card"],
             card_size=200, slots=m["slots"], slots_size=640, media_idle=1,
             last_ready=0x900, primask=1, pattern=1, transport=1,
             chunk_sectors=1024, slot_count=3, generation_lo=0x12345678,
             generation_hi=0xABCDEF01, clock_hz=25000000)
    if operation == 1:
        q = words(1)
        p.update(camera_ready=bench.FRAME_BYTES, dma_bytes=bench.FRAME_BYTES,
                 frames=1, format=10, data_type=0x30, vc0cfgr1=0x201,
                 written_sectors=3730, slot=1, payload_lba=9 + 3731,
                 card_write_lo=3732, card_read_lo=3, scan_headers=2)
    elif operation == 2:
        q = words(2, 1234, 0x12345678, 0xABCDEF01, 3)
        p.update(formatted_slots=3, card_write_lo=5, card_read_lo=3, slot=0xFFFFFFFF)
    else:
        q = words(3, 1234, 9, 4, 0)
        p.update(read_lba=9, read_count=4, read_bytes=2048,
                 read_dest=bench.READ_BUFFER, card_read_lo=4,
                 slot_count=0, generation_lo=0, generation_hi=0)
    return p, m, q


class RequestGuards(unittest.TestCase):
    def test_valid_requests_and_max_read_boundary(self):
        self.assertEqual(len(bench.request(1, 1)), 64)
        self.assertEqual(len(bench.request(2, 1, 1, 0, 0)), 64)
        self.assertEqual(len(bench.request(3, 1, 2**32 - 512, 512, 0)), 64)

    def test_reject_invalid_requests(self):
        invalid = [(0, 1), (4, 1), (1, 0), (1, 2**32), (1, 1, 1),
                   (2, 1, 0, 0), (3, 1, 0, 0), (3, 1, 0, 513),
                   (3, 1, 2**32 - 1, 2), (3, 1, 0, 1, 1),
                   (3, 1, -1, 1), (3, 1, 1.5, 1)]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                bench.request(*args)


class DmaWaitTelemetry(unittest.TestCase):
    def test_both_frozen_layouts_and_fault_decode(self):
        for size in (20,24):
            m=dict(dma_wait=0x34301000,dma_wait_bytes=size,bss_start=0x34301000,
                   bss_end=0x34301000+size,dma_wait_clock=0x34300001)
            raw=struct.pack('<6I',0x34300001,0,0,0,0,0xE00)[:size]
            class B:
                def upload(self,address,count,name):
                    self_address=address;self_count=count
                    assert (self_address,self_count)==(m['dma_wait'],size)
                    return raw
            actual,result=bench.dma_wait_snapshot(B(),m)
            self.assertEqual(actual,raw)
            self.assertEqual(result['bytes'],size)
            self.assertEqual(result['context_fault_names'],None if size==20 else
                ['ram_sleep_clocks','rif_sleep_clocks','sd_sleep_clock'])

    def test_bad_extent_and_wrong_callback(self):
        m=dict(dma_wait=0x34301000,dma_wait_bytes=24,bss_start=0x34301000,
               bss_end=0x34301018,dma_wait_clock=0x34300001)
        class B:
            def upload(self,address,count,name):return bytes(count)
        for changed in ({'dma_wait_bytes':28},{'bss_end':0x34301017},{}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                bench.dma_wait_snapshot(B(),dict(m,**changed))


class TerminalProofGuards(unittest.TestCase):
    def test_valid_capture_format_read(self):
        for op in (1, 2, 3):
            with self.subTest(operation=op):
                bench.validate(*proof(op))

    def test_wrong_nonce_incomplete_and_unsafe_context(self):
        mutations = dict(nonce=9, state=2, result=1, stage=7, terminal=0,
                         media_idle=0, initialized=1, controller_owned=1,
                         cleanup_error=1, sd_error=1, ccr=0x10000,
                         fpccr=1, cpacr=0xF00000, control=12, ipsr=3,
                         primask=0, systick=3, last_ready=0x800,
                         card_size=199, slots_size=639)
        for key, value in mutations.items():
            p, m, q = proof(1)
            p[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                bench.validate(p, m, q)

    def test_camera_completion_counts_and_exact_writes(self):
        mutations = dict(camera_ready=bench.FRAME_BYTES - 512,
                         dma_bytes=bench.FRAME_BYTES - 1, frames=2, errors=1,
                         canary=1, format=8, data_type=0x2B, vc0cfgr1=0x301,
                         written_sectors=3729, capture_error=1, slot=3,
                         payload_lba=123, card_write_lo=3731, card_write_hi=1,
                         p0fctcr=8, cmsr1=0x8000, csi_sr0=0x20000)
        for key, value in mutations.items():
            p, m, q = proof(1)
            p[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                bench.validate(p, m, q)

    def test_format_incomplete_or_wrong_generation(self):
        for key, value in dict(formatted_slots=2, slot_count=0,
                               generation_lo=1, generation_hi=0,
                               card_write_lo=4, card_write_hi=1).items():
            p, m, q = proof(2)
            p[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                bench.validate(p, m, q)

    def test_read_is_read_only_and_stays_in_reserved_buffer(self):
        for key, value in dict(read_lba=10, read_count=3, read_bytes=2047,
                               read_dest=bench.FRAME, card_write_lo=1,
                               card_write_hi=1, camera_ready=1,
                               card_read_lo=3, card_read_hi=1).items():
            p, m, q = proof(3)
            p[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                bench.validate(p, m, q)

    def test_prior_request_shape_is_revalidated(self):
        for mutate in (lambda q: q.__setitem__(0, 0),
                       lambda q: q.__setitem__(6, 1),
                       lambda q: q.__setitem__(1, 0),
                       lambda q: q.__setitem__(2, 4),
                       lambda q: q.__setitem__(4, 513)):
            p, m, q = proof(3)
            mutate(q)
            p["nonce"], p["operation"] = q[1], q[2]
            if q[4] == 513:
                p.update(read_count=513, read_bytes=513 * 512, card_read_lo=513)
            with self.subTest(request=q), self.assertRaises(ValueError):
                bench.validate(p, m, q)

    def test_decode_requires_complete_report(self):
        for size in (0, 380, 388):
            with self.assertRaises(ValueError):
                bench.decode(bytes(size), bench.fields(HERE))

    def test_live_card_deinitialized_and_within_capacity(self):
        names = ("sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles "
                 "initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 "
                 "csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command "
                 "last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error "
                 "transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr "
                 "vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned").split()
        base = {name: 0 for name in names}
        base.update(sector_count=8 + 3 * 3731, read_sectors=3, written_sectors=3732,
                    media_idle=1, stage=9, last_ready_r1=0x900,clock_hz=25000000)
        class FakeBench:
            def __init__(self, state):
                self.state = state
            def upload(self, address, count, filename):
                if count != 200:
                    raise AssertionError("unbounded live card read")
                return struct.pack("<6Q38I", *(self.state[name] for name in names))
        p, m, q = proof(1)
        bench.card_snapshot(FakeBench(base), m, p, "snapshot")
        for key, value in dict(initialized=1, controller_owned=1, error=1,
                               cleanup_error=1, timer_owned=1, media_idle=0,
                               stage=8, last_ready_r1=0x800, written_sectors=3731,
                               read_sectors=2, sector_count=8 + 3 * 3731 - 1).items():
            state = dict(base, **{key: value})
            with self.subTest(field=key), self.assertRaises(ValueError):
                bench.card_snapshot(FakeBench(state), m, p, "snapshot")

    def test_terminal_gate_rejects_changed_proof_before_halt(self):
        p, m, q = proof(1)
        code = b"known executable"
        prior = dict(proof=copy.deepcopy(p), binary_sha256=bench.sha(code), request_words=q)
        p["media_idle"] = 0
        raw = struct.pack("<96I", *(p[name] for name in bench.fields(HERE)))
        class FakeBench:
            def upload(self, address, length, filename):
                self.assertion = (address, length)
                return raw
        with patch.object(bench.sd, "context_proof") as halt:
            with self.assertRaises(ValueError):
                bench.terminal_gate(FakeBench(), HERE, m, code, prior, "before")
            halt.assert_not_called()


class ManifestGuards(unittest.TestCase):
    def make_build(self, root):
        code = bytearray(256)
        struct.pack_into("<II", code, 0, 0x343B0000, bench.LOAD + 9)
        code[32:34] = code[40:42] = b"\xfe\xe7"
        (root / "capture.bin").write_bytes(code)
        (root / "runtime.h").write_bytes((HERE / "runtime.h").read_bytes())
        m = dict(schema=1, kind="raw-slots", load=bench.LOAD, stack=0x343B0000,
                 stack_floor=0x343AF000, request=bench.REQUEST, request_words=16,
                 proof=bench.PROOF, proof_words=96, read_buffer=bench.READ_BUFFER,
                 read_buffer_bytes=bench.READ_MAX, frame=bench.FRAME,
                 frame_bytes=bench.FRAME_BYTES, width=1120, height=1364,
                 guard=bench.FRAME + bench.FRAME_BYTES, guard_bytes=32,
                 allocation_bytes=bench.FRAME_BYTES, flash=False, standby=False,
                 binary_sha256=bench.sha(code), binary_bytes=len(code),
                 entry=bench.LOAD + 9, data_start=bench.LOAD + 248,
                 data_end=bench.LOAD + 256, system_core_clock=bench.LOAD + 248,
                 bss_start=bench.LOAD + 256, card=bench.LOAD + 256,
                 slots=bench.LOAD + 480, bss_end=bench.LOAD + 1120,
                 park=bench.LOAD + 32, reject_park=bench.LOAD + 40,
                 immutable_bytes=248, pattern=1, transport="idma", chunk_sectors=1024,
                 source_hashes={"runtime.h": bench.sha((root / "runtime.h").read_bytes())})
        (root / "manifest.json").write_text(json.dumps(m))
        return m

    def test_valid_offline_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            m = self.make_build(folder)
            actual, code = bench.checked_build(folder, m["binary_sha256"])
            self.assertEqual(actual, m)
            self.assertEqual(len(code), 256)

    def test_immutable_extent_and_full_object_bounds(self):
        for field, value in (("immutable_bytes", 0), ("immutable_bytes", 249),
                             ("card", bench.LOAD + 1119), ("slots", bench.LOAD + 1119)):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                m = self.make_build(folder)
                m[field] = value
                (folder / "manifest.json").write_text(json.dumps(m))
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    bench.checked_build(folder, m["binary_sha256"])

    def test_code_digest_change_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            m = self.make_build(folder)
            code = bytearray((folder / "capture.bin").read_bytes())
            code[100] ^= 1
            (folder / "capture.bin").write_bytes(code)
            with self.assertRaises(ValueError):
                bench.checked_build(folder, m["binary_sha256"])


class WholeImageGuards(unittest.TestCase):
    def fixture(self):
        m=dict(whole_image_preerase=True,transport='idma',dma_sleep=False,chunk_sectors=3730,
               original_guard=bench.FRAME+bench.FRAME_BYTES,whole_proof_words=8,
               whole_proof=bench.LOAD+0x2000,bss_start=bench.LOAD+0x2000,bss_end=bench.LOAD+0x2020,
               guard=bench.FRAME+1909760,chunk_trace=0x343FE000)
        p=dict(chunk_count=1,chunk_overflow=0)
        data={'frame-guard.bin':struct.pack('<8I',*(0xA15A1000+i for i in range(8))),
              'whole-proof.bin':struct.pack('<8I',0x52575031,3,0,0,bench.FRAME_BYTES,1909760,160,3730),
              'frame-padding.bin':bytes(160),
              'whole-chunk.bin':struct.pack('<8I',1,2,0,3730,bench.FRAME_BYTES,0x900,0,4)}
        return m,p,data

    def test_guards_transition_padding_and_single_transaction(self):
        m,p,data=self.fixture()
        class B:
            def upload(self,address,count,name):
                assert count==len(data[name]);return data[name]
        result=bench.frame_guards(B(),m,p)
        self.assertTrue(result['original_guard_checked_before_zero_padding'])
        self.assertTrue(result['post_padding_guard_intact'])
        for name in data:
            original=data[name]
            data[name]=bytes(len(original)) if any(original) else bytes([1])*len(original)
            with self.subTest(name=name),self.assertRaises(ValueError):bench.frame_guards(B(),m,p)
            data[name]=original
        for changed in ({'chunk_count':2},{'chunk_count':0},{'chunk_overflow':1}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):bench.frame_guards(B(),m,dict(p,**changed))

    def test_whole_layout_requires_reviewed_dma_and_explicit_proof(self):
        m,_,_=self.fixture();bench.whole_layout(m)
        for changed in ({'transport':'pio'},{'dma_sleep':True},{'chunk_sectors':1024},
                        {'original_guard':0},{'whole_proof_words':7},{'whole_proof':0}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):bench.whole_layout(dict(m,**changed))


if __name__ == "__main__":
    unittest.main()
