"""Build matched native-v25 follower early/late PHY diagnostics; offline only."""
import argparse
import copy
import json
import re
from pathlib import Path
import struct
import zlib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transforms import transform_capture,transform_sensor
from build_raw10 import (ROOT, HERE, FLASH_OFFSET, checked_manifest, compile_sources,
                        make_image, inspect_image, replace, sha, write_manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phy-release',choices=('early','late'),required=True)
    p.add_argument('--sensor-clock',choices=('continuous','noncontinuous'),default='continuous')
    p.add_argument('--second-trigger',action='store_true',help='Late noncontinuous diagnostic: capture second sensor frame')
    p.add_argument('--delayed-data-lanes',action='store_true',help='Early continuous PHY clock, data modules enabled after STREAMING')
    a=p.parse_args()
    if a.second_trigger and (a.phy_release!='late' or a.sensor_clock!='noncontinuous'):
        p.error('--second-trigger requires late PHY and noncontinuous clock')
    if a.delayed_data_lanes and (a.phy_release!='early' or a.sensor_clock!='continuous' or a.second_trigger):
        p.error('--delayed-data-lanes requires early PHY, continuous clock and a single trigger')
    base,out=a.base.resolve(),a.output.resolve()
    rm,pm=(checked_manifest(base/name) for name in ('receiver','staged'))
    assert rm['parameters']['raw10_relocated'] and pm['trim_sensor']
    assert pm['program_sha256']=='c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817'
    assert rm['raw_sha256']==pm['stage2_sha256']
    assert sha((base/'receiver/capture.bin').read_bytes())==rm['raw_sha256']
    saved=a.snapshot.read_bytes()
    assert len(saved)==65536 and sha(saved)==pm['snapshot_sha256']
    out.mkdir(parents=True,exist_ok=False)
    rdir,pdir=out/'receiver',out/'staged'
    rdir.mkdir();pdir.mkdir()
    sources=[]
    for path in rm['sources']:
        source=ROOT/path
        target=rdir/source.name
        if source.name=='capture.c':
            text=transform_capture(source.read_text(),a.sensor_clock,a.second_trigger,a.delayed_data_lanes)
            target.write_text(text,encoding='utf-8',newline='\n')
        elif source.name=='hal_dcmipp.c':
            text=source.read_text()
            text=replace(text,'extern void bench_delay_us(unsigned int us);',
                         'extern void bench_delay_us(unsigned int us);\nextern void late_phy_hook(unsigned int id);')
            text=replace(text,'  /* Configure the Lane Merger */',
                         '  late_phy_hook(303);\n  /* Configure the Lane Merger */')
            text=replace(text,'  /* Enable the CSI */',
                         '  late_phy_hook(304);\n  /* Enable the CSI */')
            text=replace(text,'  SET_BIT(csi_instance->PRCR, CSI_PRCR_PEN);',
                         '  late_phy_hook(305);\n  SET_BIT(csi_instance->PRCR, CSI_PRCR_PEN);\n  late_phy_hook(306);')
            target.write_text(text,encoding='utf-8',newline='\n')
        else:target.write_bytes(source.read_bytes())
        sources.append(target)
    flags=list(rm['compile_flags'])+[f'-DLATE_PHY_MODE={1 if a.phy_release=="late" else 0}']
    raw,size=compile_sources(rdir,[s for s in sources if s.suffix!='.ld'],flags,
                             rdir/'capture.ld','capture',libc=True)
    sp,entry=struct.unpack_from('<II',raw)
    vectors=struct.unpack_from('<198I',raw)
    assert sp==0x343B0000
    assert all(v==0 or (v&1 and 0x34300000<=v-1<0x34300000+len(raw)) for v in vectors[1:])
    assert len(raw)<65536-FLASH_OFFSET
    park=int(re.search(r'^([0-9a-fA-F]+) [Tt] late_failure_idle$',
                       (rdir/'symbols.txt').read_text(),re.M).group(1),16)
    assert park%2==0 and raw[park-0x34300000:park-0x34300000+2]==bytes.fromhex('fee7')
    manifest=copy.deepcopy(rm)
    manifest.update(hardware_status='untested',raw_bytes=len(raw),raw_sha256=sha(raw),
                    size=size,entry_point=hex(entry),compile_flags=flags,
                    late_phy_status_address='0x343f8000',late_phy_status_words=1568,
                    late_phy_status_schema=1,failure_recovery_schema=1,
                    late_phy_header_words=32,late_phy_record_words=12,late_phy_max_records=128,
                    phy_release_mode=a.phy_release,
                    frozen_receiver_manifest_sha256=sha((base/'receiver/manifest.json').read_bytes()),
                    generator_sha256=sha(Path(__file__).read_bytes()))
    manifest['generator_inputs']={str(f.relative_to(ROOT)):sha(f.read_bytes())
        for f in [Path(__file__),Path(__file__).with_name('transforms.py'),
                  Path(__file__).with_name('receiver_helpers.inc'),
                  Path(__file__).with_name('main_sequence.inc')]}
    if a.second_trigger:
        f=Path(__file__).with_name('second_trigger.inc')
        manifest['generator_inputs'][str(f.relative_to(ROOT))]=sha(f.read_bytes())
    manifest['parameters']['late_phy_experiment']=True
    manifest['parameters']['i2c_follower']=True
    manifest['parameters']['sensor_clock_mode']=a.sensor_clock
    manifest['parameters']['sensor_dphytx_ctrl']='0x0c' if a.sensor_clock=='noncontinuous' else '0x1c'
    manifest['parameters']['captured_sensor_frame']=2 if a.second_trigger else 1
    manifest['parameters']['first_frame_latency_eligible']=not a.second_trigger
    manifest['parameters']['data_lane_enable']='after_sensor_streaming' if a.delayed_data_lanes else 'with_phy_release'
    manifest['failure_park_symbol']='late_failure_idle'
    manifest['failure_park_address']=hex(park)
    manifest['failure_park_bytes']='fee7'
    write_manifest(rdir,manifest,sources)
    psources=[]
    for path in pm['sources']:
        source=ROOT/path;target=pdir/source.name
        if source.name=='stage1_sensor.c':
            target.write_text(transform_sensor(source.read_text(),a.sensor_clock),encoding='utf-8',newline='\n')
        else: target.write_bytes(source.read_bytes())
        psources.append(target)
    crc=zlib.crc32(raw)&0xFFFFFFFF
    pflags=[f for f in pm['compile_flags']
            if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(raw)}U',f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    prefix,size=compile_sources(pdir,[s for s in psources if s.suffix!='.ld'],pflags,
                                pdir/'stage1.ld','stage1')
    boot=make_image(prefix)
    assert len(boot)<=FLASH_OFFSET
    (pdir/'stage1_boot.bin').write_bytes(boot);(pdir/'stage2.bin').write_bytes(raw)
    combined=bytearray(saved)
    combined[:len(boot)]=boot;combined[FLASH_OFFSET:FLASH_OFFSET+len(raw)]=raw
    assert combined[len(boot):FLASH_OFFSET]==saved[len(boot):FLASH_OFFSET]
    assert combined[FLASH_OFFSET+len(raw):]==saved[FLASH_OFFSET+len(raw):]
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    manifest=copy.deepcopy(pm)
    manifest.update(hardware_status='untested',stage1=inspect_image(boot),
                    stage1_raw_bytes=len(prefix),stage1_raw_sha256=sha(prefix),
                    stage2_bytes=len(raw),stage2_crc32=f'0x{crc:08x}',stage2_sha256=sha(raw),
                    stage2_build_manifest=str(rdir/'manifest.json'),
                    stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
                    program_sha256=sha(combined),size=size,compile_flags=pflags,
                    late_phy_status_address='0x343f8000',late_phy_status_words=1568,
                    phy_release_mode=a.phy_release,
                    sensor_clock_mode=a.sensor_clock,
                    sensor_dphytx_ctrl='0x0c' if a.sensor_clock=='noncontinuous' else '0x1c',
                    captured_sensor_frame=2 if a.second_trigger else 1,
                    first_frame_latency_eligible=not a.second_trigger,
                    data_lane_enable='after_sensor_streaming' if a.delayed_data_lanes else 'with_phy_release',
                    frozen_prefix_manifest_sha256=sha((base/'staged/manifest.json').read_bytes()))
    write_manifest(pdir,manifest,psources)
    print(json.dumps(dict(receiver=str(rdir),staged=str(pdir),receiver_bytes=len(raw),
                          receiver_sha256=sha(raw),prefix_boot_bytes=len(boot),
                          program_sha256=sha(combined),status='built; untested')))


if __name__=='__main__':main()
