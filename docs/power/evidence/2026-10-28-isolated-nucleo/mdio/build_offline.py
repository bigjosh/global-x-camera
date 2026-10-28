"""Compile/hash the optional MDIO RAM diagnostic. Never touches hardware."""
from pathlib import Path
import hashlib,json,re,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
TC=Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')
CMSIS=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS'
flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-std=c11','-Os','-g0','-Wall','-Wextra',
       '-ffunction-sections','-fdata-sections','-ffreestanding','-fno-builtin','-DSTM32N657xx',
       '-I'+str(CMSIS/'Device/ST/STM32N6xx/Include'),'-I'+str(CMSIS/'Include')]
cmd=[str(TC/'arm-none-eabi-gcc.exe'),*flags,'-nostdlib',str(HERE/'mdio_diag.c'),
     '-T',str(HERE/'mdio_diag.ld'),'-Wl,--gc-sections,--build-id=none',
     '-Wl,-Map='+str(HERE/'mdio_diag.map'),'-o',str(HERE/'mdio_diag.elf')]
p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(HERE/'build.log').write_text(p.stdout)
if p.returncode:raise SystemExit(p.stdout)
subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(HERE/'mdio_diag.elf'),str(HERE/'mdio_diag.bin')],check=True)
symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(HERE/'mdio_diag.elf')],text=True)
(HERE/'symbols.txt').write_text(symbols)
listing=subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(HERE/'mdio_diag.elf')],text=True)
(HERE/'mdio_diag.lst').write_text(listing)
def symbol(name):return int(re.search(r'^([0-9a-f]+) \w '+name+r'$',symbols,re.M)[1],16)
code=(HERE/'mdio_diag.bin').read_bytes()
assert len(code)<0x2000
assert all(x not in symbols for x in ['memset','__aeabi','phy_write'])
m={'schema':1,'load':0x343c4000,'entry':symbol('mdio_diag_entry')|1,'park':symbol('mdio_diag_park'),
   'proof':0x343c6000,'proof_words':512,'bytes':len(code),'sha256':hashlib.sha256(code).hexdigest(),
   'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'mdio_diag.c',HERE/'mdio_diag.ld']},
   'scope':'read-only PHY frames plus GPIO pad toggles; no hardware performed by builder'}
(HERE/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps(m,indent=2))
