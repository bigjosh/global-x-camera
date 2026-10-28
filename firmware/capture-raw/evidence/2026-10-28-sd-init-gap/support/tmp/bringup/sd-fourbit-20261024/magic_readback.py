"""Explicit guarded READs for mixed GXRS/GXR2 slots; dry-run by default.

No reset, power, NOR write, SD write, format or automatic retry is performed.
SCR provenance is required; erased state is never guessed from media contents.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[3]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def bound(path):return dict(path=str(Path(path).resolve()),sha256=sha(Path(path).read_bytes()))
def req(ok,message):
    if not ok:raise ValueError(message)
def save(path,obj):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,allow_nan=False);f.write('\n')
def codec():return load('magic_readback_codec',ROOT/'firmware/raw-slots/magic_slots.py')


def scr_source(path,*,erase_required=False):
    path=Path(path).resolve();v=read(path);p=v['proof'];c=v['card']
    req(v.get('passed') is True and p['operation'] in (1,2) and p['result']==0 and p['state']==3 and
        p['media_idle']==1 and not p['controller_owned'] and not p['initialized'] and not p['cleanup_error'],
        'SCR must come from an exact completed magic operation')
    s=v.get('magic_format',v.get('slots',{}));wire=bytes(s['scr_wire_bytes']);erased=s['erased_byte']
    req(len(wire)==8 and wire[0]>>4==0 and erased==(255 if wire[1]&128 else 0), 'SCR byte order/erased-value mismatch')
    expected=wire+struct.pack('<2I',1,erased)
    candidates=[path.parent/n for n in ('bootstrap/completed-scr.bin','operation/completed-scr.bin','inspection/before-scr.bin')]
    matches=[file for file in candidates if file.is_file() and file.read_bytes()==expected]
    req(len(matches)==1,'SCR binary source missing or ambiguous')
    if erase_required:
        e=s.get('erase',{})
        req(p['operation']==2 and not p['card_write_lo'] and not p['card_write_hi'] and
            e.get('started')==e.get('completed')==1 and e['first_lba']==0 and
            e['last_lba']==c['sector_count']-1 and e['last_r1']&0x1f00==0x900,
            'Completed explicit whole-card erase proof required')
    identity={key:c[key] for key in ('sector_count','cid0','cid1','cid2','cid3')}
    return dict(proof=bound(path),scr_binary=bound(matches[0]),erased_byte=erased,card_identity=identity,
                erase_required=erase_required)


def validate(folder,index,source,reference=None,reference_kind='preservation'):
    import numpy as np
    from PIL import Image
    folder=Path(folder);fmt=codec();layout=fmt.layout(source['card_identity']['sector_count'],source['erased_byte'])
    req(0<=index<layout['slot_count'],'Slot outside card geometry')
    data=(folder/'slot.bin').read_bytes();raw=(folder/'frame.bin').read_bytes()
    record=fmt.parse_slot(data,index=index,erased_byte=source['erased_byte'])
    req(record['state']=='COMPLETE' and record['start_magic_valid'] and record['completion_marker_valid'],
        'Incomplete or unrecognized magic object')
    image_offset,trailer_offset=record['image_offset'],record['trailer_offset']
    req(len(data)==fmt.PADDED_BYTES and len(raw)==fmt.IMAGE_BYTES and
        data[image_offset:trailer_offset]==raw and data[trailer_offset:trailer_offset+4]==b'GXRE',
        'Malformed magic image extent')
    if record['format_revision']==1:
        req(data[:4]==b'GXRS' and image_offset==4 and record['tail_padding_zero'] and
            data[trailer_offset+4:]==bytes(152),'Legacy padding/offset differs')
    else:
        req(record['format_revision']==2 and data[:4]==b'GXR2' and image_offset==156 and
            trailer_offset+4==len(data) and record['metadata_bytes']==152 and
            record['metadata_hex']==data[4:156].hex(),'Front metadata layout differs')
    # Independent packing arithmetic and decoder; no use of codec.unpack_raw10.
    groups=np.frombuffer(raw,dtype=np.uint8).reshape(-1,5).astype(np.uint16)
    expected=np.empty((len(groups),4),dtype=np.uint16)
    for i in range(4):expected[:,i]=((groups[:,i]<<2)|((groups[:,4]>>(2*i))&3))<<6
    expected=expected.reshape(fmt.HEIGHT,fmt.WIDTH)
    encoded=fmt.png16(raw,record);png=folder/'scene.png'
    if png.exists():req(png.read_bytes()==encoded,'Existing PNG differs')
    else:png.write_bytes(encoded)
    decoded=np.asarray(Image.open(io.BytesIO(encoded)))
    req(np.array_equal(decoded,expected),'Independent PNG/raw sample comparison failed')
    comparison=None
    if reference:
        reference=Path(reference);req(reference.read_bytes()==raw,'Reference/source camera RAM differs')
        comparison=dict(source=bound(reference),kind=reference_kind,bytes_equal=True)
    return dict(schema=1,format=record['format'],passed=True,slot=index,layout=layout,header=record,
        full_payload_read=True,full_slot_read=True,bytes=len(raw),slot_bytes=len(data),
        start_magic_valid=True,completion_marker_valid=True,padding_zero=record.get('tail_padding_zero'),
        payload_checksum_available=False,on_media_metadata=record['metadata_bytes']>0,png_samples_match_read_raw=True,
        source_reference_comparison=comparison,original_sensor_frame_comparison=bool(comparison and reference_kind=='sensor-ram'),
        source_comparison_limit=None if comparison else 'Original capture RAM not provided; recovered image only',
        minimum_sample=int(expected.min())>>6,maximum_sample=int(expected.max())>>6,mean_sample=float(expected.mean())/64,
        raw_sha256=sha(raw),slot_sha256=sha(data),png_sha256=sha(encoded),scr_source=source,
        artifacts=[bound(folder/name) for name in ('slot.bin','frame.bin','scene.png')],
        limits=['Markers indicate completion, not payload checksum or power-loss atomicity.'])


class Reader:
    def __init__(self,args,source):
        self.a=args;self.source=source;self.prior=args.prior.resolve()
        self.bench=load('magic_readback_bench',ROOT/'firmware/capture-raw/bench.py')
        self.m=read(args.build/'manifest.json')
        req(self.m.get('magic_format') is True and self.m.get('flash') is False,'Exact RAM magic build required')
        self.bench.checked_build(args.build,self.m['binary_sha256'])
    def operation(self,out,lba,count):
        self.bench.run(SimpleNamespace(build=self.a.build,expected_sha=self.m['binary_sha256'],operation='read',
            out=out,prior=self.prior,bridge_proof=None,recovery_build=None,execute=True,download_frame=False,
            lba=lba,count=count,generation=None,slot_limit=0))
        self.prior=out/'verified.json';v=read(self.prior);c=v['card']
        req({k:c[k] for k in self.source['card_identity']}==self.source['card_identity'],'Card identity/capacity changed since SCR/erase')
        raw=(out/'sectors.bin').read_bytes();req(len(raw)==count*512,'Incomplete block read')
        return raw


def run(a):
    plan=dict(plan_only=not a.execute,action=a.action,build=str(a.build),prior=str(a.prior),out=str(a.out),
        scr_proof=str(a.scr_proof),slots=getattr(a,'slot',None),hardware_scope='READ only; no reset, power, writes or retries')
    if not a.execute:return plan
    req(a.action in ('read-slots','read-headers'),'Unsupported READ action')
    source=scr_source(a.scr_proof)
    a.out.mkdir(parents=True,exist_ok=False);save(a.out/'scr-source.json',source)
    reader=Reader(a,source);fmt=codec();layout=fmt.layout(source['card_identity']['sector_count'],source['erased_byte'])
    if a.action=='read-headers':
        req(len(a.slot)==len(set(a.slot)) and all(0<=index<layout['slot_count'] for index in a.slot),'Invalid/repeated slot')
        items=[]
        for index in a.slot:
            folder=a.out/f'slot-{index}'
            raw=reader.operation(folder,index*fmt.STRIDE,1)
            record=fmt.parse_header(raw,index=index,erased_byte=source['erased_byte'])
            req(not record['completion_checked'] and record['completion_marker_valid'] is None,
                'First-sector listing cannot qualify trailing completion')
            items.append(dict(slot=index,header=record,data=bound(folder/'sectors.bin'),proof=bound(folder/'verified.json')))
        result=dict(passed=True,read_sectors=len(items),one_sector_per_slot=True,layout=layout,slots=items,
                    prior=str(reader.prior.resolve()),scr_source=source,
                    limits='First-sector listing proves occupancy and metadata only; completion requires the final sector.')
    else:
        req(len(a.slot)==len(set(a.slot)) and all(0<=index<layout['slot_count'] for index in a.slot),'Invalid/repeated slot')
        req(not a.reference or len(a.slot)==1,'One source RAM reference can bind only one slot')
        items=[]
        for index in a.slot:
            folder=a.out if len(a.slot)==1 else a.out/f'slot-{index}'
            if folder!=a.out:folder.mkdir()
            parts=[]
            for off in range(0,fmt.STRIDE,512):
                parts.append(reader.operation(folder/f'payload-{off:04d}',index*fmt.STRIDE+off,min(512,fmt.STRIDE-off)))
            data=b''.join(parts);(folder/'slot.bin').write_bytes(data)
            record=fmt.parse_slot(data,index=index,erased_byte=source['erased_byte'])
            req(record.get('start_magic_valid') and record.get('state')=='COMPLETE',
                'Refusing unrecognized/incomplete slot before extracting image bytes')
            (folder/'frame.bin').write_bytes(data[record['image_offset']:record['trailer_offset']])
            save(folder/'scr-source.json',source) if folder!=a.out else None
            report=validate(folder,index,source,a.reference,a.reference_kind)
            save(folder/'readback-validation.json',report)
            items.append(dict(slot=index,validation=bound(folder/'readback-validation.json'),prior=str(reader.prior.resolve())))
        result=dict(passed=True,layout=layout,slots=items,prior=str(reader.prior.resolve()),scr_source=source)
    save(a.out/'summary.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for name in ('read-slots','read-headers'):
        q=s.add_parser(name);q.add_argument('--build',type=Path,required=True);q.add_argument('--prior',type=Path,required=True)
        q.add_argument('--scr-proof',type=Path,required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--execute',action='store_true')
        q.add_argument('--slot',type=int,action='append',required=True)
        if name=='read-slots':
            q.add_argument('--reference',type=Path)
            q.add_argument('--reference-kind',choices=('preservation','sensor-ram'),default='preservation')
    q=s.add_parser('validate');q.add_argument('--folder',type=Path,required=True);q.add_argument('--slot',type=int,required=True)
    q.add_argument('--reference',type=Path);q.add_argument('--reference-kind',choices=('preservation','sensor-ram'),default='preservation')
    q.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='validate':
        result=validate(a.folder,a.slot,read(a.folder/'scr-source.json'),a.reference,a.reference_kind);save(a.out,result)
    else:result=run(a)
    print(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
