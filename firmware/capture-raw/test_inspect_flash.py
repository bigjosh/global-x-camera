"""Offline ownership gates; no programmer or instruments are instantiated."""
import copy
from datetime import datetime,timezone,timedelta
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

HERE=Path(__file__).resolve().parent
def module(name,file):
    s=importlib.util.spec_from_file_location(name,HERE/file)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=module('inspect_flash_tested','inspect_flash.py')
shared=module('raw_flash_test_fixtures','test_bench.py')


def fixture():
    p,m,_=shared.proof(1)
    m.update(expected_flags=0,pattern=0,load=f.bench.LOAD,binary_bytes=4096,
        immutable_ranges=[[f.bench.LOAD,f.bench.LOAD+64],[f.bench.LOAD+2048,f.bench.LOAD+4096]],
        guard=f.bench.FRAME+f.bench.FRAME_BYTES,system_core_clock=0x34301000,
        chunk_trace=0x343FE000,park=0x34300020,line_stream=False,
        late_load=dict(late_address=f.bench.LOAD+2048,late_bytes=2048,late_crc32=123,proof=0x343F9E00))
    p.update(nonce=0,pattern=0,flags=0,chunk_count=1)
    for field in ('begin','arm','frame_done','camera_stop','first_write','commit_done','deinit_done','end'): p[field]=100
    values={name:0 for name in f.bench.sd.CARD_QWORDS+f.bench.sd.CARD_WORDS}
    values.update(sector_count=122507264,read_sectors=p['card_read_lo'],written_sectors=3732,
        media_idle=1,stage=9,last_ready_r1=0x900)
    card=struct.pack('<6Q38I',*(values[n] for n in f.bench.sd.CARD_QWORDS+f.bench.sd.CARD_WORDS))
    slots=bytearray(640);gen=p['generation_lo']|(p['generation_hi']<<32)
    struct.pack_into('<IIQ12I',slots,0,m['card'],m['late_load']['late_address']|1,gen,
        p['slot_count'],p['slot'],p['payload_lba'],3730,1,0,0,0,p['scan_headers'],0,0,3732)
    header=bytearray(512);header[:8]=b'GXRAWSL1'
    struct.pack_into('<IIQ7I',header,8,1,0x4C4C5546,gen,p['slot'],f.bench.FRAME_BYTES,p['payload_lba'],1120,1364,1400,1)
    struct.pack_into('<I',header,88,f.bench.FRAME_BYTES)
    struct.pack_into('<I',header,508,zlib.crc32(header[:508]));slots[128:]=header
    late=m['late_load'];loader=struct.pack('<16I',0x524C4431,1,late['late_address'],2048,2,2048,123,123,10,11,0,0,0,0,0,0x524C4F4B)
    code=bytes((i*7)&255 for i in range(4096))
    names=f.bench.fields(HERE);proof=struct.pack('<96I',*(p[n] for n in names))
    payloads={'proof-before.bin':proof,'before-card.bin':card,'slots-before.bin':bytes(slots),
        'late-loader.bin':loader,'code-0.bin':code[:64],'code-1.bin':code[2048:],
        'frame-guard.bin':struct.pack('<8I',*(0xA15A1000+i for i in range(8))),
        'clock.bin':struct.pack('<I',400000000),'proof-before-halt.bin':proof,
        'chunks.bin':bytes(32),'proof-final.bin':proof}
    return p,m,code,payloads


class FlashGuards(unittest.TestCase):
    def test_loader_checks_every_fifo_level_bit(self):
        _,m,_,data=fixture();f.validate_loader(data['late-loader.bin'],m)
        for bit in range(8,15):
            bad=bytearray(data['late-loader.bin']);struct.pack_into('<I',bad,16,2|(1<<bit))
            with self.subTest(bit=bit),self.assertRaises(ValueError):f.validate_loader(bytes(bad),m)

    def test_camera_telemetry_uses_frozen_names_and_current_fast_count(self):
        names=f.profile_fields(HERE.parent/'capture-sd')
        p={n:0 for n in names};p.update(magic=0x52435032,schema=2,words=32,
            post_frame_begin=100,essential_done=400100,pipe_stop_begin=500000,pipe_stop_done=500400,
            data_off_done=501000,sensor_stop_done=1001000,handoff_ready=1200100)
        cp=struct.pack('<32I',*(p[n] for n in names))
        fast=[0]*544;fast[0]=0x46505931;fast[2]=1;fast[8]=1;fast[32]=430;fast[48]=999
        with tempfile.TemporaryDirectory() as directory:
            class B:
                output=Path(directory)/'inspection'
                def upload(self,address,count,name):
                    return cp if name=='capture-profile.bin' else struct.pack('<544I',*fast)
            result=f.camera_telemetry(B(),HERE.parent/'capture-sd',{})
            self.assertEqual(result['capture_profile_intervals_ms']['essential_checks'],1)
            self.assertIsNone(result['capture_profile_intervals_ms']['optional_frame_scan'])
            self.assertEqual(len(result['fast_records']),1)
            self.assertEqual(result['fast_records'][0]['event'],430)

    def test_full_slot_has_consumed_free_selection(self):
        p,m,_,data=fixture()
        f.validate_slots(data['slots-before.bin'],p,m)
        bad=bytearray(data['slots-before.bin']);struct.pack_into('<I',bad,40,1)
        with self.assertRaises(ValueError):f.validate_slots(bytes(bad),p,m)

    def test_zero_nonce_explicit_flash_and_failed_states_rejected(self):
        p,m,_,_=fixture();f.validate_proof(p,m)
        for field,value in [('nonce',1),('result',1),('stage',5),('media_idle',0),
                            ('completion',1),('camera_stop',0),('capture_error',1),('ccr',0x10000)]:
            bad=dict(p);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):f.validate_proof(bad,m)

    def test_every_pre_halt_gate_refuses_without_context_call(self):
        _,m,code,payloads=fixture()
        for field in ('proof-before.bin','before-card.bin','slots-before.bin','late-loader.bin',
                      'code-0.bin','code-1.bin','frame-guard.bin','clock.bin','proof-before-halt.bin'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                data=dict(payloads);data[field]=bytes(len(data[field]))
                class B:
                    output=Path(directory)/'inspection'
                    def upload(self,address,count,name):return data[name]
                with patch.object(f.bench.sd,'context_proof') as context:
                    with self.assertRaises(ValueError):f.inspect(B(),HERE,m,code)
                    context.assert_not_called()

    def test_success_context_only_after_prechecks(self):
        _,m,code,payloads=fixture();seen=[]
        with tempfile.TemporaryDirectory() as directory:
            class B:
                output=Path(directory)/'inspection'
                def upload(self,address,count,name):seen.append(name);return payloads[name]
            def context(*args):
                self.assertEqual(seen[-1],'proof-before-halt.bin');return {'test':True}
            with patch.object(f.bench.sd,'context_proof',side_effect=context) as call, \
                 patch.object(f,'camera_telemetry',return_value={'test':True}):
                result=f.inspect(B(),HERE,m,code);call.assert_called_once()
            self.assertTrue(result['passed']);self.assertFalse(result['sd_payload_integrity_verified'])

    def test_root_freshness_requires_hash_time_and_evidence(self):
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'evidence').write_bytes(b'cold cycle complete')
            p=dict(schema=1,bench_owner='root',kind='raw-flash-cold-boot',cold_boot_confirmed=True,
                observed_utc=now.isoformat(),binary_sha256='a'*64,sector_sha256='b'*64,
                evidence=[dict(path='evidence',sha256=f.sha((root/'evidence').read_bytes()))])
            token=root/'boot.json';token.write_text(json.dumps(p))
            f.fresh_boot(token,'a'*64,'b'*64,now)
            with self.assertRaises(ValueError):f.fresh_boot(token,'a'*64,'b'*64,now+timedelta(minutes=11))
            (root/'evidence').write_bytes(b'changed')
            with self.assertRaises(ValueError):f.fresh_boot(token,'a'*64,'b'*64,now)


if __name__=='__main__':unittest.main()
