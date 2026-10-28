"""Offline standalone isolated-board probe build. No hardware imports."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
for name in ('probe.c','entry.S','probe.ld'):shutil.copyfile(HERE/name,out/name)
cmsis=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'
flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only',
 '-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
 '-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles',
 '-DSTM32N657xx','-I'+str(cmsis/'Include'),'-I'+str(cmsis/'Device/ST/STM32N6xx/Include')]
subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,'-T'+str(out/'probe.ld'),
 str(out/'entry.S'),str(out/'probe.c'),'-Wl,--build-id=none','-o',str(out/'probe.elf')],check=True)
subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'probe.elf'),str(out/'probe.bin')],check=True)
symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(out/'probe.elf')],text=True)
(out/'symbols.txt').write_text(symbols)
(out/'probe.lst').write_text(subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(out/'probe.elf')],text=True))
def sym(n):return int(re.search(r'^([0-9a-f]+) [A-Za-z] '+n+r'$',symbols,re.M)[1],16)
code=(out/'probe.bin').read_bytes()
assert not subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-u',str(out/'probe.elf')]).strip()
assert len(code)<0x10000 and code[sym('isolated_park')-0x34300000:sym('isolated_park')-0x34300000+2]==b'\xfe\xe7'
fields=[x.strip() for x in re.search(r'enum \{(.*?)\};',(out/'probe.c').read_text(),re.S)[1].split(',')]
assert len(fields)-1<96,'Proof header overlaps RCC inventory'
m=dict(schema=6,kind='isolated-nucleo-power',load=0x34300000,entry=sym('isolated_entry')|1,
 park=sym('isolated_park'),proof=0x343C2000,proof_words=256,request=0x343C1F00,request_words=8,
 stack=0x343B0000,stack_floor=0x343AF000,workload_buffer=0x34310000,workload_bytes=1024,
 fields=fields[:-1],bytes=len(code),sha256=hashlib.sha256(code).hexdigest(),flags=flags,
 markers={'11':'busy_begin','12':'busy_end','13':'sleep_begin','14':'sleep_end'},
 marker_nominal_us_per_id=2,core_hz=400000000,systick_hz=100,dividers=[1,2,4,8],
 rcc_inventory_names=re.findall(r'X\((\w+)\)',re.search(r'#define RCC_INVENTORY\(X\)(.*?)static void inventory',(out/'probe.c').read_text(),re.S)[1]),
 rcc_inventory_before_word=96,rcc_inventory_after_word=160,
 sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('probe.c','entry.S','probe.ld')})
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m))
