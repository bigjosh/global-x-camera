"""Offline build; no instrument imports."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC
src=ROOT/'tmp/bringup/power-ablation-20261028/ram-hold'
for name in ('phase_gpio.c','phase_gpio.h'):(HERE/name).write_bytes((src/name).read_bytes())
includes=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'
flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfpu=fpv5-d16','-mfloat-abi=hard','-Os',
 '-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror',
 '-DSTM32N657xx','-I'+str(HERE),'-I'+str(includes/'Include'),
 '-I'+str(includes/'Device/ST/STM32N6xx/Include')]
for name in ('probe','phase_gpio'):
 subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,'-c',str(HERE/(name+'.c')),'-o',str(HERE/(name+'.o'))],check=True)
subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,'-nostdlib','-Wl,--gc-sections',
 '-T'+str(HERE/'probe.ld'),str(HERE/'probe.o'),str(HERE/'phase_gpio.o'),'-o',str(HERE/'probe.elf')],check=True)
subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(HERE/'probe.elf'),str(HERE/'probe.bin')],check=True)
listing=subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(HERE/'probe.elf')],text=True)
(HERE/'probe.lst').write_text(listing)
symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(HERE/'probe.elf')],text=True)
(HERE/'symbols.txt').write_text(symbols)
def symbol(name):return int(re.search(r'^([0-9a-f]+) [A-Za-z] '+name+r'$',symbols,re.M)[1],16)
raw=(HERE/'probe.bin').read_bytes()
assert len(raw)<0x1000 and not re.search(r'^\s*U ',symbols,re.M)
fields=[x.strip() for x in re.search(r'enum \{(.*?)\};',(HERE/'probe.c').read_text(),re.S)[1].split(',')]
m=dict(schema=1,load=0x343C1000,entry=symbol('power_sleep_entry')|1,proof=0x343C2000,proof_words=128,
 fields=fields,refused=symbol('power_sleep_refused'),wfi=symbol('power_sleep_wfi'),after_wfi=symbol('power_sleep_after_wfi'),
 bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
 sources={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('probe.c','probe.ld','phase_gpio.c','phase_gpio.h')})
(HERE/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m))
