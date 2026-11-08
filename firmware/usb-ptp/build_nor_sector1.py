"""Build the existing v2 NOR programmer with one fixed address relocation.

The command ABI remains unchanged; the only allowed physical write window is
now [0x10000,0x20000). Relative RAM buffers, sixteen-sector planning, fresh
WIP/WEL completion and all verification remain unchanged. This is a separate
helper; it cannot program sector0 or take an arbitrary host-selected address.
"""
from pathlib import Path
import argparse,importlib.util,json,sys,hashlib,re
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'firmware/boot-timing/experiments/rom-nor-programmer-v2'
SOURCE_SHA256='5204c6c6a83ed5205549ca6b292103b32db8ca2ef4077934a61610c7809365f9'
def transform(text):
 # Bind the complete reviewed input, not merely the known replacement sites.
 # Otherwise an added seventh addressed command could escape relocation.
 if hashlib.sha256(text.encode('utf-8')).hexdigest()!=SOURCE_SHA256:
  raise ValueError('NOR programmer source differs from the reviewed fixed-window input')
 replacements={
 'transfer(c, 0x0B, 1, 0, 65536, 1, OUTPUT)':'transfer(c, 0x0B, 1, 65536, 65536, 1, OUTPUT)',
 'transfer(c, 0x20, 1, base, 0, 0, 0)':'transfer(c, 0x20, 1, 65536+base, 0, 0, 0)',
 'transfer(c, 0x0B, 1, base, 4096, 1, OUTPUT+base)':'transfer(c, 0x0B, 1, 65536+base, 4096, 1, OUTPUT+base)',
 'transfer(c, 0x02, 1, page, 256, 0, INPUT+page)':'transfer(c, 0x02, 1, 65536+page, 256, 0, INPUT+page)',
 'transfer(c, 0x0B, 1, page, 256, 1, OUTPUT+page)':'transfer(c, 0x0B, 1, 65536+page, 256, 1, OUTPUT+page)',
 }
 for before,after in replacements.items():
  if text.count(before)!=(2 if ', 0, 65536,' in before else 1):
   raise ValueError('NOR addressed transfer sites differ from the reviewed relocation')
  text=text.replace(before,after)
 if len(re.findall(r'transfer\(c,\s*0x[0-9A-Fa-f]+,\s*1,',text))!=6:
  raise ValueError('Expected exactly six addressed NOR transfer sites')
 return text
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();src=out/'source';src.mkdir(parents=True,exist_ok=False)
 for name in ('programmer.c','entry.S','programmer.ld','completion_poll.h'):(src/name).write_bytes((SOURCE/name).read_bytes())
 (src/'programmer.c').write_text(transform((SOURCE/'programmer.c').read_text(encoding='utf-8')),encoding='utf-8')
 spec=importlib.util.spec_from_file_location('nor_sector1_builder',SOURCE/'build.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.SOURCE=src
 sys.argv=['build','--out',str(out)];mod.main()
 m=json.loads((out/'manifest.json').read_text());m['fixed_flash_base']=65536;m['physical_write_window']=[65536,131072];m['source_transform']='exact six addressed transfers only; RAM indices and status addresses remain relative';m['transformation_source_sha256']=SOURCE_SHA256
 (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
 print('Fixed sector1 helper:',m['binary_sha256'])
if __name__=='__main__':main()
