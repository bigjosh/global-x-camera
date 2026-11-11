"""Offline dual-mode package preserving the original capture and UART code.

The one patched DSB becomes B.W to an appended hook, which executes that DSB
and preserves the integer context. Building never operates hardware or admits
an image to the recovery allowlist.
"""
import argparse,copy,hashlib,json,re,struct,subprocess,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
from add_boot_header import make_image,inspect_image
REFERENCE=ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/flash-standby-v1/staged'
REFERENCE_PREFIX_SHA='6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
REFERENCE_SECTOR_SHA='79a379470927135bc03841098fe070912cad8275e91c5d5985cc066c294cf64e'
# Only reviewed complete capture builds may be composed. These are filled from
# the independently inspected PA2 build, never from a caller's manifest.
HOLD_REFERENCE_PREFIX_SHA='95312a3a9782ddae82157c3d9859c31de157f8a42e4e9cf370ccba93b26acdfc'
HOLD_REFERENCE_SECTOR_SHA='86786daaaa689b1df556603ca3a4df9b09dcff37d1095d56821c6fa01f99ce22'
PREFIX_BASE=0x34180400;PATCH_ADDRESS=0x34180E26;PATCH_OFFSET=PATCH_ADDRESS-PREFIX_BASE
RESUME_ADDRESS=PATCH_ADDRESS+4;HOOK_BASE=0x34181E40;PREFIX_END=0x34182000
DSB=bytes.fromhex('bff34f8f');SECTOR_BYTES=0x10000;CAPTURE_OFFSET=0x2000
SELECTOR_LOAD=0x34200000;SELECTOR_LIMIT=0x34210000;SELECTOR_FLASH=0x10000
USB_FLASH=0x12000;USB_LOAD=0x34300000;USB_MAX_BYTES=0xD000
USB_BSS_LIMIT=0x343E0000;USB_STACK=0x343F0000

def sha(data):return hashlib.sha256(data).hexdigest()

def require(condition,message):
 # Package safety checks must survive python -O.
 if not condition:raise ValueError(message)

def integer(mapping,key):
 value=mapping.get(key)
 require(type(value) is int,'Missing/non-integer manifest field: '+key)
 return value

def validate_usb_image(manifest,image):
 require(manifest.get('schema')==1 and manifest.get('kind')=='usb-ptp-ram','Unsupported USB build schema/kind')
 require(8<=len(image)<=USB_MAX_BYTES,'USB image exceeds reserved NOR region')
 require(integer(manifest,'bytes')==len(image) and manifest.get('sha256')==sha(image),'USB image length/hash mismatch')
 require(integer(manifest,'load')==USB_LOAD,'Unexpected USB load address')
 entry=integer(manifest,'entry')
 require(entry&1 and USB_LOAD<=(entry&~1)<USB_LOAD+len(image),'USB entry must be Thumb code inside image')
 require(integer(manifest,'stack')==USB_STACK,'Unexpected USB stack')
 require(struct.unpack_from('<II',image)==(USB_STACK,entry),'USB vector table differs from manifest')
 park=integer(manifest,'park')
 require(not park&1 and USB_LOAD<=park<=USB_LOAD+len(image)-2 and image[park-USB_LOAD:park-USB_LOAD+2]==b'\xfe\xe7','USB park is not an in-image branch-to-self')
 start,end=integer(manifest,'bss_start'),integer(manifest,'bss_end')
 require(not (start|end)&3 and USB_LOAD+len(image)<=start<=end<USB_BSS_LIMIT,'USB BSS overlaps image, stack, or reserved records')
 require(integer(manifest,'proof')==0x343F8000 and integer(manifest,'proof_words')==64 and integer(manifest,'request')==0x343F7F00,'Unexpected USB proof/request layout')

def validate_usb_hold_policy(manifest,profile,force_capture=False):
 hold=manifest.get('gpio_hold',{})
 require(hold.get('schema')==2 and hold.get('port')=='GPIOA' and hold.get('pin')==2 and hold.get('mode')=='usb-off' and hold.get('shutdown_proof_schema')==3,'USB must keep PA2 HOLD off, including shutdown refusal and return')
 require(not(force_capture and profile=='pa2-hold'),'Forced capture is not supported by the PA2 USB-off package; use a cable-absent battery capture')

def validate_reference(original,sector,manifest):
 profile=reference_identity(original,sector)
 require(manifest.get('stage1_raw_sha256')==sha(original) and manifest.get('stage1_raw_bytes')==len(original) and manifest.get('program_sha256')==sha(sector) and manifest.get('program_bytes')==SECTOR_BYTES,'Original manifest is inconsistent with pinned artifacts')
 if profile=='pa2-hold':
  hold=manifest.get('raw_slots',{}).get('gpio_hold_contract',{})
  require(hold.get('schema')==3 and hold.get('port')=='GPIOA' and hold.get('pin')==2,'PA2 capture requires the reviewed schema 3 HOLD contract')
  require(struct.unpack_from('<I',original,4)[0]==0x34181DF1,'PA2 early HOLD reset vector changed')
  legacy=json.loads((REFERENCE/'manifest.json').read_text(encoding='utf-8'))
  for key in ('recovery_gpio','recovery_vcp'):
   require(manifest.get(key)==legacy.get(key),'Early UART recovery metadata changed: '+key)
 require(original[PATCH_OFFSET:PATCH_OFFSET+4]==DSB,'Displaced instruction is not DSB')
 boot=make_image(original)
 require(sector[:len(boot)]==boot,'Original boot header/prefix embedding differs')
 return profile

def reference_identity(original,sector):
 require(len(original)==HOOK_BASE-PREFIX_BASE and len(sector)==SECTOR_BYTES,'Capture reference dimensions changed')
 identity=(sha(original),sha(sector))
 if identity==(REFERENCE_PREFIX_SHA,REFERENCE_SECTOR_SHA):return 'legacy-october28'
 if identity==(HOLD_REFERENCE_PREFIX_SHA,HOLD_REFERENCE_SECTOR_SHA):return 'pa2-hold'
 raise ValueError('Capture bytes differ from independently reviewed reference builds')

def branch_target(instruction,address):
 """Decode only unconditional Thumb-2 B.W; reject BL, BLX and conditional B."""
 require(len(instruction)==4,'Patch must be one four-byte B.W')
 hi,lo=struct.unpack('<HH',instruction)
 require(hi&0xF800==0xF000 and lo&0xD000==0x9000,'Patch must be B.W, never a linking/conditional branch')
 sign=(hi>>10)&1;i1=1^((lo>>13)&1)^sign;i2=1^((lo>>11)&1)^sign
 displacement=(sign<<24)|(i1<<23)|(i2<<22)|((hi&0x3FF)<<12)|((lo&0x7FF)<<1)
 if sign:displacement-=1<<25
 return address+4+displacement

def compose(original,sector,patch,hook,selector,usb):
 """Build sectors only after validating every fixed-region boundary."""
 reference_identity(original,sector)
 require(branch_target(patch,PATCH_ADDRESS)==HOOK_BASE,'Patch target differs from hook')
 require(0<len(hook)<=PREFIX_END-HOOK_BASE and hook[:4]==DSB,'Hook exceeds prefix room or omits displaced DSB')
 require(0<len(selector)<=USB_FLASH-SELECTOR_FLASH,'Selector overlaps USB NOR image')
 require(8<=len(usb)<=USB_MAX_BYTES,'USB image exceeds reserved NOR region')
 prefix=original[:PATCH_OFFSET]+patch+original[PATCH_OFFSET+4:]+hook
 boot=make_image(prefix);require(len(boot)<=CAPTURE_OFFSET,'Boot image overwrites capture stage 2')
 sector0=boot+sector[len(boot):]
 require(len(sector0)==SECTOR_BYTES and sector0[CAPTURE_OFFSET:]==sector[CAPTURE_OFFSET:],'Capture code or preserved sector tail changed')
 sector1=bytearray(b'\xff'*SECTOR_BYTES);sector1[:len(selector)]=selector
 usb_offset=USB_FLASH-SELECTOR_FLASH;sector1[usb_offset:usb_offset+len(usb)]=usb
 require(len(sector1)==SECTOR_BYTES,'NOR sector size changed')
 return prefix,boot,sector0,bytes(sector1)

def recovery_manifest(reference_manifest,prefix,boot,sector0):
 """Compatible check_park metadata, without automatic allowlist admission."""
 result=copy.deepcopy(reference_manifest)
 result.update(hardware_status='untested-usb-package',stage1=inspect_image(boot),stage1_raw_bytes=len(prefix),stage1_raw_sha256=sha(prefix),program_bytes=len(sector0),program_sha256=sha(sector0),usb_boot_package=dict(schema=1,original_prefix_sha256=reference_manifest['stage1_raw_sha256'],original_sector_sha256=reference_manifest['program_sha256'],patch_address=hex(PATCH_ADDRESS),resumes_at=hex(RESUME_ADDRESS),recovery_allowlist_admission=False))
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--usb',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--force-capture',action='store_true');p.add_argument('--capture',type=Path,required=True,help='Reviewed staged capture build; use PA2 HOLD build for the canonical wiring');a=p.parse_args()
 m=json.loads((a.usb/'manifest.json').read_text(encoding='utf-8'));usb=(a.usb/'usb.bin').read_bytes();validate_usb_image(m,usb)
 original=(a.capture/'stage1.bin').read_bytes();sector=(a.capture/'capture_sector_0.bin').read_bytes();reference_manifest=json.loads((a.capture/'manifest.json').read_text(encoding='utf-8'));profile=validate_reference(original,sector,reference_manifest)
 validate_usb_hold_policy(m,profile,a.force_capture)
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 frozen_names=('boot_read.h','boot_hook.c','boot_hook.S','selector.c','vbus.c','usb_hold.h','package.py')
 for n in frozen_names:(out/n).write_bytes((HERE/n).read_bytes())
 (out/'stm32n6xx_hal_conf.h').write_bytes((a.usb/'stm32n6xx_hal_conf.h').read_bytes())
 config=f'#define USB_FLASH_OFFSET {hex(USB_FLASH)}U\n#define USB_BYTES {len(usb)}U\n#define USB_CRC {zlib.crc32(usb)}U\n#define USB_ENTRY {m["entry"]}U\n'
 (out/'boot_config.h').write_text(config,encoding='utf-8')
 sdk=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers';hal=sdk/'STM32N6xx_HAL_Driver';cmsis=sdk/'CMSIS'
 flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only','-Os','-flto','-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-nostartfiles','-DSTM32N657xx','-DUSE_HAL_DRIVER']
 for d in (out,hal/'Inc',cmsis/'Include',cmsis/'Device/ST/STM32N6xx/Include'):flags+=['-I'+str(d)]
 if a.force_capture:flags+=['-DUSB_BOOT_FORCE_CAPTURE=1']
 def build(name,base,sources,entry,bss_limit):
  ld=out/(name+'.ld');ld.write_text(f'ENTRY({entry})\nSECTIONS {{ . = {hex(base)}; .text : {{ KEEP(*(.text.entry)) KEEP(*(.text.hook)) *(.text*) *(.rodata*) }} .data : {{ *(.data*) }} . = ALIGN(4); __bss_start__ = .; .bss (NOLOAD) : {{ *(.bss*) *(COMMON) }} . = ALIGN(4); __bss_end__ = .; /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} ASSERT(. < {hex(bss_limit)},"overflow") }}',encoding='utf-8')
  subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,*map(str,sources),'-T'+str(ld),'--specs=nosys.specs','-Wl,--build-id=none,--gc-sections','-o',str(out/(name+'.elf'))],check=True)
  subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/(name+'.elf')),str(out/(name+'.bin'))],check=True)
  symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(out/(name+'.elf'))],text=True);(out/(name+'.symbols')).write_text(symbols,encoding='utf-8')
  listing=subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(out/(name+'.elf'))],text=True);(out/(name+'.lst')).write_text(listing,encoding='utf-8')
  symbol=re.search(r'^([0-9a-f]+) [A-Za-z] '+re.escape(entry)+'$',symbols,re.M);require(symbol is not None,'Missing linked entry: '+entry)
  address=int(symbol[1],16);image=(out/(name+'.bin')).read_bytes();require(base<=address<base+len(image) and not address&1,'Linked entry outside image')
  return image,address
 selector,entry=build('selector',SELECTOR_LOAD,[out/'selector.c',out/'vbus.c',hal/'Src/stm32n6xx_hal_adc.c',hal/'Src/stm32n6xx_hal_adc_ex.c',hal/'Src/stm32n6xx_hal_rcc.c'],'usb_selector',SELECTOR_LIMIT)
 require(0<len(selector)<=USB_FLASH-SELECTOR_FLASH,'Selector overlaps USB NOR image')
 config+=f'#define SELECTOR_BYTES {len(selector)}U\n#define SELECTOR_CRC {zlib.crc32(selector)}U\n#define SELECTOR_ENTRY {entry|1}U\n';(out/'boot_config.h').write_text(config,encoding='utf-8')
 hook,hook_entry=build('hook',HOOK_BASE,[out/'boot_hook.S',out/'boot_hook.c'],'usb_boot_hook',PREFIX_END)
 require(hook_entry==HOOK_BASE,'Hook entry moved from appended prefix start')
 # Assemble through the real linker, then independently decode the result.
 (out/'patch.S').write_text('.syntax unified\n.thumb\n.global patch\npatch:\n b.w '+hex(hook_entry)+'\n',encoding='utf-8')
 subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),'-mcpu=cortex-m55','-mthumb','-nostdlib','-Wl,--build-id=none,-Ttext='+hex(PATCH_ADDRESS)+',-e,patch',str(out/'patch.S'),'-o',str(out/'patch.elf')],check=True)
 subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'patch.elf'),str(out/'patch.bin')],check=True)
 prefix,boot,sector0,sector1=compose(original,sector,(out/'patch.bin').read_bytes(),hook,selector,usb)
 for name,data in (('stage1.bin',prefix),('sector0.bin',sector0),('sector1.bin',sector1)):(out/name).write_bytes(data)
 recovery=out/'recovery';recovery.mkdir();(recovery/'stage1.bin').write_bytes(prefix);(recovery/'capture_sector_0.bin').write_bytes(sector0)
 (recovery/'manifest.json').write_text(json.dumps(recovery_manifest(reference_manifest,prefix,boot,sector0),indent=2)+'\n',encoding='utf-8')
 result=dict(schema=1,usb_sha256=sha(usb),usb_build=str(a.usb.resolve()),prefix_sha256=sha(prefix),prefix_bytes=len(prefix),sector0_sha256=sha(sector0),sector1_sha256=sha(sector1),hook_bytes=len(hook),selector_bytes=len(selector),selector_entry=entry|1,hook_entry=hook_entry,patch_address=PATCH_ADDRESS,patch_encoding='B.W',original_instruction='DSB',resumes_at=RESUME_ADDRESS,original_prefix_sha256=sha(original),original_sector_sha256=sha(sector),unchanged_capture_from_offset=CAPTURE_OFFSET,uart_guard_unchanged=True,force_capture=a.force_capture,boot=inspect_image(boot),recovery_directory='recovery',recovery_allowlist_admission=False,sources={name:sha((out/name).read_bytes()) for name in frozen_names})
 result.update(capture_build=str(a.capture.resolve()),capture_profile=profile,gpio_hold=copy.deepcopy(reference_manifest.get('raw_slots',{}).get('gpio_hold_contract')),usb_hold_policy=copy.deepcopy(m['gpio_hold']),hardware_status='offline-only-not-installed')
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
