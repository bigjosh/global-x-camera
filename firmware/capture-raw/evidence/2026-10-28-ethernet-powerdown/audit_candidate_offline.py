"""Pure file/source audit. Does not create a bench or call an instrument API."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
import bench
import late_build

def sha(b):return hashlib.sha256(b).hexdigest()
def readj(p):return json.loads(p.read_text())
def symbols(p):
    return {m[2]:int(m[1],16) for m in re.finditer(
        r'^([0-9a-f]+) [A-Za-z] (\S+)$',p.read_text(),re.M)}

spec=importlib.util.spec_from_file_location('offline_capture_sd_builder',ROOT/'firmware/capture-sd/build.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

report={'scope':'Offline files only; no hardware or installation qualification','builds':{}}
for name in ('ram-candidate','flash-candidate'):
    p=HERE/name;m=readj(p/'manifest.json');code=(p/'capture.bin').read_bytes()
    assert sha(code)==m['binary_sha256'] and len(code)==m['binary_bytes']
    assert struct.unpack_from('<II',code)==(m['stack'],m['entry'])
    for fn,digest in m['source_hashes'].items():assert sha((p/fn).read_bytes())==digest,fn
    assert bench.board_eth_layout(m,1)
    assert bench.board_eth_layout(m,3)
    bench.diagnostic_layout(m,1)
    if name=='ram-candidate':
        accepted,_=bench.checked_build(p,m['binary_sha256'])
        assert accepted==m
        admission='checked_build RAM/awake passed'
    else:
        assert bench.startup_flash_profile(m)
        # checked_build intentionally admits only RAM/awake. Do not relax it.
        try:bench.checked_build(p,m['binary_sha256'])
        except ValueError as exc:assert str(exc)=='Only reviewed RAM/awake layout is accepted'
        else:raise AssertionError('FLASH unexpectedly admitted to RAM runner')
        admission='FLASH profile/layout/source hashes passed; RAM runner correctly rejects FLASH'
    entry={'binary_sha256':sha(code),'binary_bytes':len(code),'admission':admission,
        'board_eth_proof':hex(m['board_eth_proof']),'board_eth_proof_bytes':m['board_eth_proof_bytes'],
        'bss':[hex(m['bss_start']),hex(m['bss_end'])],'all_frozen_source_hashes_match':True}
    if name=='flash-candidate':
        late=m['late_load'];begin=late['late_address'];end=begin+late['late_bytes']
        entry['fresh_layout_audit']=late_build.audit_layout(code,(p/'symbols.txt').read_text(),
            (p/'capture.lst').read_text(),begin,end)
        syms=symbols(p/'symbols.txt')
        eth={n:hex(a) for n,a in syms.items() if n.startswith('beth_') or n=='board_eth_powerdown_once'}
        assert len(eth)==16 and all(begin<=int(a,16)<end for a in eth.values())
        assert late['early_bytes']==15804 and begin==0x34303DBC and end<=0x3430E000
        assert zlib.crc32(code[begin-m['load']:end-m['load']])==late['late_crc32']
        entry.update(early_bytes=late['early_bytes'],early_immutable_bytes=m['immutable_bytes'],
            early_padding_bytes=late['early_bytes']-m['immutable_bytes']-4,
            late_address=hex(begin),late_end=hex(end),late_bytes=late['late_bytes'],
            ethernet_late_symbols=eth)
    report['builds'][name]=entry

new=HERE/'flash-candidate/staged'
old=ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged'
n=(new/'stage1.bin').read_bytes();o=(old/'stage1.bin').read_bytes()
nm=readj(new/'manifest.json');om=readj(old/'manifest.json')
assert len(n)==len(o)==6720
assert sha(o)=='99dbb0f9ecdd56a9313e4e62bbbfec22ec8e5e5901c852d956315844cd066eba'
allowed={i for off in (0xC9C,0x1354) for i in range(off,off+4)}
diff=[i for i,(a,b) in enumerate(zip(o,n)) if a!=b]
assert diff and set(diff)<=allowed
literals=builder.check_recovery_identity(new,n,o,15804)
assert len(literals)==20 and literals==nm['checked_recovery_literal_offsets']
assert n[:0xAFE]==o[:0xAFE]
for off in literals:assert n[off:off+4]==o[off:off+4]
ns=symbols(new/'symbols.txt');os=symbols(old/'symbols.txt')
for key in ('recovery_gpio_park','stage1_fault','_error_engine_start','_error_engine_end','_error_copy_end'):
    assert ns[key]==os[key]
copy_offset=ns['_error_engine_start']-0x34180400
copy_bytes=ns['_error_copy_end']-ns['_error_engine_start']
engine=n[copy_offset:copy_offset+copy_bytes]
assert copy_bytes==1536 and engine==o[copy_offset:copy_offset+copy_bytes]
assert sha(engine)=='247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e'
receiver=(new/'stage2.bin').read_bytes();full=(new/'stage2-full.bin').read_bytes()
assert len(receiver)==15804 and full==(HERE/'flash-candidate/capture.bin').read_bytes()
assert receiver==full[:15804]
crc=zlib.crc32(receiver)
assert int(nm['stage2_crc32'],16)==crc
for off in (0xC9C,0x1354):assert struct.unpack_from('<I',n,off)[0]==crc
sector=(new/'capture_sector_0.bin').read_bytes();boot=(new/'stage1_boot.bin').read_bytes()
assert len(sector)==65536 and sha(sector)==nm['program_sha256']
assert sector[:len(boot)]==boot and sector[0x2000:0x2000+len(full)]==full
assert sha(n)==nm['stage1_raw_sha256']
assert sha((new/'stage1-unrelocated.bin').read_bytes())==nm['prefix_crc_relocation']['unrelocated_sha256']
assert (new/'stage1-unrelocated.bin').read_bytes()==(old/'stage1-unrelocated.bin').read_bytes()
report['prefix']={'old_sha256':sha(o),'new_sha256':sha(n),'bytes':len(n),
    'changed_byte_offsets':diff,'only_two_receiver_crc_words_changed':True,
    'crc_word_offsets':['0xC9C','0x1354'],'new_receiver_crc32':hex(crc),
    'unrelocated_prefix_identical':True,'complete_guard_identical_through_offset':'0xAFE',
    'referenced_literal_offsets':literals,'referenced_literal_count':len(literals),
    'park':hex(ns['recovery_gpio_park']),'error_engine_identical':True,
    'error_engine_sha256':sha(engine),'error_engine_bytes':copy_bytes,
    'runtime_copy_destination':hex(readj(HERE/'flash-candidate/manifest.json')['error_runtime_copy']['destination']),
    'sector_sha256':sha(sector),'early_receiver_bytes':len(receiver),
    'receiver_sha256':sha(full)}
report['passed']=True
out=HERE/'candidate-offline-audit.json'
if out.exists():raise FileExistsError(out)
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
