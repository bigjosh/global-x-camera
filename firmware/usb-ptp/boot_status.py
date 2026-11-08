"""Read-only proof of a persistent USB boot and create a bench session record."""
import argparse,hashlib,json,struct
from pathlib import Path
import bench
def main():
 p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 package=json.loads((a.package/'manifest.json').read_text(encoding='utf-8'));build=Path(package['usb_build']);m=json.loads((build/'manifest.json').read_text(encoding='utf-8'))
 code=(build/'usb.bin').read_bytes()
 if hashlib.sha256(code).hexdigest()!=package['usb_sha256']:raise ValueError('USB build differs')
 b=bench.nor_bench.Bench(a.out/'operations')
 status=struct.unpack('<64I',b.upload(0x343F8000,256,'status.bin'));selector=struct.unpack('<16I',b.upload(0x343F9000,64,'selector.bin'))
 result=dict(status=status,selector=selector)
 bench.save(a.out/'result.json',result)
 if status[:4]!=(0x31505450,1,4,0) or selector[:2]!=(0x31534255,4):raise ValueError('Persistent USB boot not in service state; inspect records')
 if b.upload(m['load'],len(code),'live-code.bin')!=code:raise ValueError('Live USB code differs')
 if 0x34200000<=selector[4]<0x34210000:
  result['vbus']=struct.unpack('<16I',b.upload(selector[4],64,'selector-vbus.bin'))
 result['selector_to_usb_ms']=((selector[6]-selector[2])&0xFFFFFFFF)/400000
 bench.save(a.out/'result.json',result);bench.save(a.out/'session.json',dict(build=str(build.resolve()),manifest=m,nonce=0))
 print(json.dumps(result))
if __name__=='__main__':main()
