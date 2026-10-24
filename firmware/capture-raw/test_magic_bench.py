"""Offline magic-format ownership guards, including pre-halt refusal paths."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
shared=module('magic_test_legacy','test_bench.py')
b=shared.bench
flash=module('magic_test_flash','inspect_flash.py')
flash_tests=module('magic_test_flash_fixture','test_inspect_flash.py')


def magic_manifest():
    return dict(magic_format=True,whole_image_preerase=False,transport='idma',dma_sleep=False,
        chunk_sectors=3730,frame=b.MAGIC_FRAME,frame_bytes=b.FRAME_BYTES,
        slot_buffer=b.MAGIC_BUFFER,original_guard=b.MAGIC_FRAME+b.FRAME_BYTES,
        guard=b.MAGIC_BUFFER+b.SLOT_BYTES,guard_bytes=32,allocation_bytes=b.SLOT_BYTES,
        magic_slots=b.LOAD+0x3000,magic_slots_bytes=576,
        magic_proof=b.LOAD+0x3240,magic_proof_words=8,
        sd_scr=b.LOAD+0x3260,sd_scr_bytes=16,
        sd_erase=b.LOAD+0x3270,sd_erase_bytes=32,
        sd_stream=b.LOAD+0x3290,sd_stream_bytes=44,
        bss_start=b.LOAD+0x2000,bss_end=b.LOAD+0x3300,
        card=b.LOAD+0x2000,slots=b.LOAD+0x2100,
        chunk_trace=0x343FE000,expected_flags=128,immutable_bytes=0x1000)


def fixture(operation=1):
    p,m,q=shared.proof(operation);m.update(magic_manifest())
    p.update(card=m['card'],slots=m['slots'],frame=b.MAGIC_FRAME,flags=128,chunk_sectors=3730,
        generation_lo=0,generation_hi=0)
    if operation==1:
        p.update(payload_lba=p['slot']*3730,card_write_lo=3730,card_read_lo=2,chunk_count=1)
    elif operation==2:
        q=list(struct.unpack('<16I',b.request(2,1234,magic_format=True)))
        p.update(formatted_slots=3,card_write_lo=0,card_read_lo=0,slot=0xFFFFFFFF)
    return p,m,q


def snapshot_data(p,m,*,erased=255):
    scr=bytearray(16);scr[1]=128 if erased else 0;struct.pack_into('<2I',scr,8,1,erased)
    slots=bytearray(576)
    struct.pack_into('<13I',slots,0,m['card'],p['slot_count'],p['slot'],p['payload_lba'],
        erased,1,0,0,0,p['scan_headers'],p['scan_headers'],p['written_sectors'],p['written_sectors'])
    if p['operation']==1:slots[64:68]=bytes([erased])*4
    mirror=bytearray(640)
    struct.pack_into('<16I',mirror,0,m['card'],0,0,0,p['slot_count'],p['slot'],p['payload_lba'],
        p['written_sectors'],1,0,0,0,p['scan_headers'],p['formatted_slots'],0,0)
    stream=struct.pack('<11I',b.LOAD+0x101,0,1,b.SLOT_BYTES,b.SLOT_BYTES,b.SLOT_BYTES,1,0,0,10,10)
    erase=struct.pack('<8I',1,1,0,3*3730+100-1,600000,100,0x900,4)
    sensor=bytearray(128);coarse=m.get('exposure_coarse',1428)
    struct.pack_into('<4I',sensor,18*4,max(4336,coarse+2000),100,coarse,
        230597 if coarse==30000 else 10976)
    return {'x-scr.bin':bytes(scr),'x-magic-slots.bin':bytes(slots),'x-slots-mirror.bin':bytes(mirror),
            'x-stream.bin':stream,'x-erase.bin':erase,'x-sensor-status.bin':bytes(sensor)},dict(sector_count=3*3730+100)


class FakeBench:
    def __init__(self,data):self.data=data
    def upload(self,address,count,name):
        raw=self.data[name]
        if len(raw)!=count:raise AssertionError('Read extent differs')
        return raw


class MagicFormatGuards(unittest.TestCase):
    def test_new_format_request_does_not_weaken_legacy_generation(self):
        self.assertEqual(len(b.request(2,1,magic_format=True)),64)
        with self.assertRaises(ValueError):b.request(2,1)
        for args in ((1,0,0),(0,1,0),(0,0,1)):
            with self.subTest(args=args),self.assertRaises(ValueError):b.request(2,1,*args,magic_format=True)

    def test_capture_erase_and_read_proofs(self):
        for op in (1,2,3):
            with self.subTest(op=op):b.validate(*fixture(op))

    def test_old_geometry_or_generation_is_not_magic_completion(self):
        for field,value in [('frame',b.FRAME),('payload_lba',3740),('card_write_lo',3732),
            ('generation_lo',1),('scan_headers',1),('chunk_count',2),('flags',64)]:
            p,m,q=fixture();p[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):b.validate(p,m,q)

    def test_magic_erase_cannot_claim_sector_writes_or_partial_capacity(self):
        for field,value in [('card_write_lo',1),('card_read_lo',1),('generation_lo',1),
            ('formatted_slots',2),('slot_count',0),('scan_headers',1),('slot',0)]:
            p,m,q=fixture(2);p[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):b.validate(p,m,q)

    def test_explicit_magic_layout_and_nonoverlapping_objects(self):
        m=magic_manifest();b.magic_layout(m)
        for changed in ({'magic_format':1},{'whole_image_preerase':True},{'transport':'pio'},
            {'dma_sleep':True},{'slot_buffer':b.MAGIC_BUFFER+4},{'frame':b.FRAME},
            {'original_guard':0},{'magic_proof_words':7},{'magic_slots_bytes':575},
            {'magic_slots':m['card']},{'sd_stream':m['sd_scr']},{'sd_erase':m['bss_end']},
            {'guard':b.MAGIC_BUFFER+b.SLOT_BYTES+4}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):b.magic_layout(dict(m,**changed))

    def test_full_checked_ram_manifest_accepts_only_new_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);m=shared.ManifestGuards().make_build(folder);m.update(magic_manifest())
            m['immutable_bytes']=248
            (folder/'manifest.json').write_text(json.dumps(m))
            b.checked_build(folder,m['binary_sha256'])
            m['expected_flags']=0;(folder/'manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):b.checked_build(folder,m['binary_sha256'])

    def test_only_flash_can_omit_unreachable_erase_object(self):
        m=dict(magic_manifest(),sd_erase=None,flash=True);b.magic_layout(m)
        m['flash']=False
        with self.assertRaises(ValueError):b.magic_layout(m)

    def test_marker_padding_and_guard_proof(self):
        p,m,_=fixture()
        data={'frame-guard.bin':struct.pack('<8I',*(0xA15A1000+i for i in range(8))),
            'magic-proof.bin':struct.pack('<8I',0x524D4731,3,0,0,0x53525847,0x45525847,152,3730),
            'leading-magic.bin':b'GXRS','trailing-magic.bin':b'GXRE','frame-padding.bin':bytes(152),
            'magic-chunk.bin':struct.pack('<8I',1,2,0,3730,b.FRAME_BYTES,0x900,0,4)}
        self.assertTrue(b.frame_guards(FakeBench(data),m,p)['post_padding_guard_intact'])
        for name in data:
            bad=dict(data);raw=bytearray(bad[name]);raw[0]^=1;bad[name]=bytes(raw)
            # The first trace word is a timestamp, so corrupt the owned count.
            if name=='magic-chunk.bin':raw=bytearray(data[name]);struct.pack_into('<I',raw,12,3729);bad[name]=bytes(raw)
            with self.subTest(name=name),self.assertRaises(ValueError):b.frame_guards(FakeBench(bad),m,p)

    def test_live_magic_scr_stream_and_reporting_mirror(self):
        p,m,_=fixture()
        for erased in (0,255):
            data,card=snapshot_data(p,m,erased=erased)
            result=b.magic_snapshot(FakeBench(data),m,p,'x',card)
            self.assertEqual(result['erased_byte'],erased)
            for name,offset in [('x-scr.bin',8),('x-magic-slots.bin',28),('x-slots-mirror.bin',128),
                ('x-stream.bin',20),('x-stream.bin',32)]:
                bad=dict(data);raw=bytearray(bad[name]);raw[offset]^=1;bad[name]=bytes(raw)
                with self.subTest(name=name,offset=offset),self.assertRaises(ValueError):
                    b.magic_snapshot(FakeBench(bad),m,p,'x',card)

    def test_partial_publication_requires_pio_and_complete_queue(self):
        p,m,_=fixture();data,card=snapshot_data(p,m)
        raw=list(struct.unpack('<11I',data['x-stream.bin']));raw[2]=2;raw[3]=512;raw[6]=100
        data['x-stream.bin']=struct.pack('<11I',*raw)
        self.assertEqual(b.magic_snapshot(FakeBench(data),m,p,'x',card)['stream']['mode'],2)
        raw[2]=1;data['x-stream.bin']=struct.pack('<11I',*raw)
        with self.assertRaises(ValueError):b.magic_snapshot(FakeBench(data),m,p,'x',card)

    def test_sensor_exposure_bound_to_manifest_and_long_frame_margin(self):
        p,m,_=fixture();m['exposure_coarse']=30000
        data,card=snapshot_data(p,m)
        sensor=b.magic_snapshot(FakeBench(data),m,p,'x',card)['sensor']
        self.assertEqual(sensor['exposure_us'],230597)
        self.assertTrue(sensor['nondefault_frame_bound_checked'])
        for word,value in ((18,30000),(18,106),(19,32000),(20,1428),(21,0),(21,230598)):
            bad=dict(data);raw=bytearray(bad['x-sensor-status.bin'])
            struct.pack_into('<I',raw,word*4,value);bad['x-sensor-status.bin']=bytes(raw)
            with self.subTest(word=word,value=value),self.assertRaises(ValueError):
                b.magic_snapshot(FakeBench(bad),m,p,'x',card)

    def test_erase_completion_must_cover_actual_whole_card(self):
        p,m,_=fixture(2);data,card=snapshot_data(p,m)
        self.assertEqual(b.magic_snapshot(FakeBench(data),m,p,'x',card)['erase']['completed'],1)
        for offset,value in ((0,0),(4,0),(8,1),(12,0),(16,1000),(20,600001),(24,0x800),(28,3)):
            bad=dict(data);raw=bytearray(bad['x-erase.bin']);struct.pack_into('<I',raw,offset,value);bad['x-erase.bin']=bytes(raw)
            with self.subTest(offset=offset),self.assertRaises(ValueError):b.magic_snapshot(FakeBench(bad),m,p,'x',card)

    def test_flash_failure_in_new_object_refuses_before_halt(self):
        p,m,code,data=flash_tests.fixture();newp,newm,_=fixture();m.update(newm)
        for k in ('frame','flags','chunk_sectors','generation_lo','generation_hi','payload_lba',
            'card_write_lo','card_read_lo','card','slots'):p[k]=newp[k]
        p.update(pattern=0,nonce=0);m.update(pattern=0)
        names=b.fields(HERE);data['proof-before.bin']=struct.pack('<96I',*(p[n] for n in names))
        # Keep the failure at the real new object gate, before any context call.
        extra,card=snapshot_data(p,m);extra['x-magic-slots.bin']=bytes(576)
        data.update({name.replace('x-','before-'):raw for name,raw in extra.items()})
        with patch.object(flash.bench,'card_snapshot',return_value=card),patch.object(flash.bench.sd,'context_proof') as context:
            with self.assertRaises(ValueError):flash.inspect(FakeBench(data),HERE,m,code)
            context.assert_not_called()


if __name__=='__main__':unittest.main()
