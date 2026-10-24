"""Root-owned RAM-only RAW10 experiment. Offline unless --execute.

Starts from installed v66c's exact early recovery, using its qualified SRAM
bridge. No reset, target power, NOR or SD operation is provided here. Every
capture begins by explicitly resetting the sensor through the reviewed code.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import struct
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('raw_capture_bridge', ROOT / 'firmware/capture-sd/low_power/readback_recovery/run.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
sd = bridge.sd
FIELDS = '''magic schema words nonce mode pattern state result expected_bytes frame width height
dma_bytes canary_mask frames errors sensor_format sensor_dt p0ppcr vc0cfgr1 p0fscr
p0fctcr cmsr1 csi_sr0 csi_sr1 post_frame_begin stop_end ccr control ipsr primask fpccr
cpacr systick reset_begin reset_end start_begin start_end terminal pattern_register'''.split()
REQUEST, PROOF, LOAD, FRAME = 0x343FD000, 0x343FD100, 0x34300000, 0x34000000
MAGIC, DONE = 0x52505231, 0x5250444E


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def checked_build(folder, digest):
    m = json.loads((folder / 'manifest.json').read_text())
    code = (folder / 'capture.bin').read_bytes()
    if sha(code) != digest or m['binary_sha256'] != digest or len(code) != m['binary_bytes']:
        raise ValueError('Explicit reviewed executable hash differs')
    required = dict(schema=1, load=LOAD, stack=0x343B0000, request=REQUEST,
        proof=PROOF, proof_words=40, frame=FRAME, width=1120, height=1364,
        sd_commands=False, nor_commands=False, sensor_reset=True,
        cold_start_measurement=False, installed_recovery_unchanged=True)
    if any(m.get(k) != v for k, v in required.items()):
        raise ValueError('Unexpected layout or experiment scope')
    if m['mode'] not in (0, 1) or m['pattern'] not in (0, 1):
        raise ValueError('Unknown packing/pattern configuration')
    if m['frame_bytes'] != 1120*1364*(5 if m['mode'] else 8)//4:
        raise ValueError('Unexpected frame capacity')
    if not 0 < len(code) < 0x20000 or len(code) % 4:
        raise ValueError('Code window overflow')
    if struct.unpack_from('<II', code) != (m['stack'], m['entry']):
        raise ValueError('Entry/vector mismatch')
    if not (LOAD < m['data_start'] == m['system_core_clock'] < m['data_end'] == LOAD+len(code)
            and m['data_end']-m['data_start'] == 4
            and m['data_end'] <= m['bss_end'] < m['stack_floor'] < m['stack']):
        raise ValueError('Mutable data or stack layout differs')
    if m['allocation_bytes'] != 3055360:
        raise ValueError('Full safe padded16 allocation required for both trials')
    for key in ('park', 'reject_park'):
        off = m[key] - LOAD
        if not 0 <= off < len(code)-1 or code[off:off+2] != b'\xfe\xe7':
            raise ValueError('Exact branch-to-self missing')
    for name, expected in m['source_hashes'].items():
        path = (folder/name).resolve()
        path.relative_to(folder.resolve())
        if sha(path.read_bytes()) != expected:
            raise ValueError('Frozen source changed: '+name)
    return m, code


def decode(raw):
    if len(raw) != 160:
        raise ValueError('Incomplete capture proof')
    return dict(zip(FIELDS, struct.unpack('<40I', raw)))


def validate(proof, manifest, nonce):
    expected = dict(magic=MAGIC, schema=1, words=40, nonce=nonce,
        mode=manifest['mode'], pattern=manifest['pattern'], state=3, result=0,
        expected_bytes=manifest['frame_bytes'], dma_bytes=manifest['frame_bytes'],
        frame=FRAME, width=1120, height=1364, frames=1, errors=0, canary_mask=0,
        sensor_format=10, sensor_dt=0x30 if manifest['mode'] else 0x2B,
        control=0, ipsr=0, primask=1, cpacr=0, terminal=DONE,
        pattern_register=0x121 if manifest['pattern'] else 0)
    if any(proof.get(k) != v for k, v in expected.items()):
        raise ValueError('Capture completion proof rejected: '+str(proof))
    if proof['ccr'] & 0x30000 or proof['fpccr'] & 1 or proof['systick'] & 3:
        raise ValueError('Capture left active cache/FP/SysTick context')
    if (proof['p0ppcr'] & 0x20 or proof['p0fctcr'] & 8 or proof['cmsr1'] & 0x8000
            or proof['csi_sr0'] & 0x20000 or proof['p0fscr'] & 0x3F != expected['sensor_dt']):
        raise ValueError('Capture pipe is active or has the wrong data type')
    if proof['vc0cfgr1'] != (0x201 if manifest['mode'] else 0x301):
        raise ValueError('CSI input format differs')
    if (proof['reset_end']-proof['reset_begin']) & 0xFFFFFFFF < 40800:
        raise ValueError('Sensor reset pulse too short')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    m, code = checked_build(a.build.resolve(), a.expected_sha)
    a.out.mkdir(parents=True, exist_ok=False)
    recovery = ROOT/'tmp/bringup/sd-normal-20261024/v66c-normal-standby/staged'
    boot = ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
    _, boot_code = bridge.checked_bridge(boot)
    identity = bridge.checked_recovery(recovery)
    nonce = secrets.randbelow(0xFFFFFFFF) + 1
    request = struct.pack('<4I', 0x52505131, nonce, m['mode'], m['pattern'])
    dump(a.out/'plan.json', dict(execute=a.execute, build=str(a.build.resolve()),
        binary_sha256=sha(code), recovery=identity, request_words=list(struct.unpack('<4I',request)),
        sd_commands=False, nor_commands=False, reset_controller=False, power_switch=False))
    if not a.execute:
        print('Offline plan validated; hardware not accessed')
        return
    b = bridge.bootstrap(SimpleNamespace(recovery_build=recovery, bridge=boot), a.out, boot_code)
    b.call('-halt', '-w', (a.build/'capture.bin').resolve(), hex(LOAD), '-v',
           success='Download verified successfully')
    if b.upload(LOAD,len(code),'capture-readback.bin') != code:
        raise ValueError('Executable readback differs; not executed')
    (b.output/'capture-request.bin').write_bytes(request)
    (b.output/'capture-clear.bin').write_bytes(bytes(160))
    b.call('-halt','-w',b.output/'capture-request.bin',hex(REQUEST),'-v',
           '-w',b.output/'capture-clear.bin',hex(PROOF),'-v',success='Download verified successfully')
    if (b.upload(REQUEST,16,'capture-request-readback.bin') != request or
            b.upload(PROOF,160,'capture-cleared.bin') != bytes(160)):
        raise ValueError('Request/proof memory mismatch; not executed')
    # Reset_Handler sets its own high stack before sensor or capture work.
    b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000',
           '-run',success='Core run')
    for poll in range(20):
        proof = decode(b.upload(PROOF,160,f'capture-proof-{poll:02d}.bin'))
        if proof['magic'] == MAGIC and proof['nonce'] == nonce and proof['terminal'] == DONE:
            break
        time.sleep(.2)
    else:
        dump(a.out/'incomplete.json',proof)
        raise TimeoutError('No completed capture proof; no automatic reset or retry')
    dump(a.out/'proof.json',proof)
    validate(proof,m,nonce)
    context = sd.context_proof(b,{m['park']},'capture-completed')
    live_cpacr,=struct.unpack('<I',b.upload(0xE000ED88,4,'completed-cpacr.bin'))
    if live_cpacr != 0:
        raise ValueError('FP/MVE access was not released')
    raw_proof=list(struct.unpack('<19I',b.upload(0x343F6000,76,'raw10-detail.bin')))
    if (raw_proof[10] or raw_proof[14]&~12 or raw_proof[15]&1
            or raw_proof[16]!=0xF00000 or raw_proof[17]!=0x343AF000
            or not 0x343AF000<raw_proof[18]<=0x343B0000):
        raise ValueError('Capacity guard or owned context cleanup proof differs')
    expected_guard=struct.pack('<8I',*(0xA15A1000+i for i in range(8)))
    for label,offset in [('expected',m['frame_bytes']),('capacity',m['allocation_bytes'])]:
        if b.upload(FRAME+offset,32,label+'-guard.bin')!=expected_guard:
            raise ValueError('Live frame guard differs: '+label)
    immutable_bytes=m['data_start']-LOAD
    if b.upload(LOAD,immutable_bytes,'completed-code.bin') != code[:immutable_bytes]:
        raise ValueError('Executed immutable code changed')
    actual_clock,=struct.unpack('<I', b.upload(m['system_core_clock'],4,'completed-system-clock.bin'))
    if actual_clock != 400000000:
        raise ValueError('SystemCoreClock does not match qualified ROM profile')
    images=[]
    for repeat in range(2):
        image=bytearray()
        for offset in range(0,m['frame_bytes'],262144):
            count=min(262144,m['frame_bytes']-offset)
            image.extend(b.upload(FRAME+offset,count,f'frame-{repeat}-{offset:08x}.bin'))
        images.append(bytes(image))
    if images[0] != images[1]:
        raise ValueError('Completed frame changed between two full reads')
    if decode(b.upload(PROOF,160,'final-proof.bin')) != proof:
        raise ValueError('Completion proof changed during frame read')
    (a.out/'frame.bin').write_bytes(images[0])
    result=dict(passed=True,proof=proof,context=context,raw10_detail=raw_proof,binary_sha256=sha(code),
        frame_sha256=sha(images[0]),frame_bytes=len(images[0]),full_repeat_read_match=True,
        sd_commands=False,nor_commands=False,normal_firmware_unchanged=True)
    dump(a.out/'verified.json',result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()

