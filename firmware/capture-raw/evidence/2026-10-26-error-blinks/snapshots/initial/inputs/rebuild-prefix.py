import sys,json,zlib
from pathlib import Path
sys.path.insert(0,str(Path('firmware/capture-raw').resolve()))
import build,error_build
out=Path('tmp/bringup/error-blinks-20261026/flash-v1'); pd=out/'staged'
s=pd/'stage1.c';s.write_text(s.read_text().replace('    __asm volatile("b.w error_stage1_bridge");\n    __builtin_unreachable();','    for (;;) __asm volatile("b.w error_stage1_bridge");'),newline='\n')
pm=json.loads((build.BASE/'staged/manifest.json').read_text())
pf=[f for f in pm['compile_flags'] if not f.startswith(('-DSTAGE2_BYTES=','-DSTAGE2_EXPECTED_CRC32='))]
pf.insert(0,'-I'+str(pd.resolve()));pf+=['-DSTAGE2_BYTES=15804U','-DSTAGE2_EXPECTED_CRC32=0x3e97c7f7U','-DRAW_PATTERN=0']
code=(out/'capture.bin').read_bytes();src=[pd/Path(p).name for p in pm['sources'] if Path(p).suffix.lower() in ('.c','.s')]+[pd/'error_bridge.c',pd/'error_signal.c']
prefix,size=build.compile_sources(pd,src,pf,pd/'stage1.ld','stage1')
print(size)
print([(hex(i),a,b) for i,(a,b) in enumerate(zip(prefix,(build.BASE/'staged/stage1.bin').read_bytes())) if a!=b][:35])

