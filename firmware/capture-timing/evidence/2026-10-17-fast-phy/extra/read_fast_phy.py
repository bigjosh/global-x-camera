"""Bench-owner read of the fixed v35 high-SRAM diagnostic region."""
import argparse, hashlib, importlib.util, json, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
from nor_bench import Bench
spec=importlib.util.spec_from_file_location('fast_decoder',ROOT/'firmware/capture-timing/fast_phy/inspect.py')
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();m=json.loads((a.build/'manifest.json').read_text())
receiver=(a.build/'capture.bin').read_bytes()
if hashlib.sha256(receiver).hexdigest()!=m['raw_sha256'] or len(receiver)!=m['raw_bytes']:
    raise ValueError('Frozen receiver differs from manifest')
b=Bench(a.out)
enabled,=struct.unpack('<I',b.upload(0x5602824C,4,'memory-enable.bin'))
if enabled&15!=15:raise ValueError('Expanded SRAM is not enabled; no high-SRAM access')
raw=b.upload(decoder.ADDRESS,decoder.WORDS*4,'fast.bin')
result=decoder.decode(raw,m)
if m.get('shutdown_data_off'):
    proof=b.upload(0x343F8900,64,'shutdown.bin')
    result['shutdown_proof']=decoder.decode_shutdown(proof,m,result)
result['receiver_sha256']=m['raw_sha256']
result['raw_error_records']=[dict(event=r['event'],name=r['name'],sr0=hex(r['sr0']),sr1=hex(r['sr1']),strobes=r['strobe_ordinal']) for r in result['records'] if r['csi_read'] and (r['sr0']&0x7F200000 or r['sr1']&0x1F1F)]
(a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('words','records','header')},indent=2))
