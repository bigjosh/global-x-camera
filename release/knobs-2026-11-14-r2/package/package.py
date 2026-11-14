"""Offline dual-mode package preserving the original capture and UART code.

The one patched DSB becomes B.W to an appended hook, which executes that DSB
and preserves the integer context. Building never operates hardware or admits
an image to the recovery allowlist.

The default uses the sampled-controls helper with a rebuilt dynamic receiver
and CKN1 metadata. --capture-controls is an explicit alias for that default.
--legacy-knobs reproduces the November 14 runtime-patched knob.c profile for
historical analysis only. These profiles are mutually exclusive; the default
never links knob.c or applies exposure_gate.py. Every capture input must match
an independently reviewed full-image identity.

Compiler: the tools in the GLOBAL_X_TOOLCHAIN directory if that variable is
set, else the ST compiler path recorded in build_raw10.py if it exists, else
arm-none-eabi-* on PATH. ST drivers: --hal and --cmsis, else the local SDK copy
under tmp/.
"""
import argparse,copy,hashlib,json,os,re,shutil,struct,subprocess,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC
sys.path.insert(0,str(HERE))
import exposure_gate,knob_tables
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
from add_boot_header import make_image,inspect_image
REFERENCE=ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/flash-standby-v1/staged'
REFERENCE_PREFIX_SHA='6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
REFERENCE_SECTOR_SHA='79a379470927135bc03841098fe070912cad8275e91c5d5985cc066c294cf64e'
# Only reviewed complete capture builds may be composed. These are filled from
# the independently inspected PA2 build, never from a caller's manifest.
HOLD_REFERENCE_PREFIX_SHA='95312a3a9782ddae82157c3d9859c31de157f8a42e4e9cf370ccba93b26acdfc'
HOLD_REFERENCE_SECTOR_SHA='86786daaaa689b1df556603ca3a4df9b09dcff37d1095d56821c6fa01f99ce22'
# November13 independently audited PE9 capture (schema4); historical PA2
# remains inspectable, but cannot be combined with the PE9 USB policy.
D3_REFERENCE_PREFIX_SHA='0b700733636492f866c3be0b64a27c05c4e39f9a4b43c7783b53a5ba608c9ade'
D3_REFERENCE_SECTOR_SHA='8760fc72cf9dd572b050d2d37ace393ea6f64d1fbcd946eab667298bada664f4'
# D8 pin substitution: mandatory build/layout audit only; no new test campaign.
D8_REFERENCE_PREFIX_SHA='eb8a84ac842027877c6e8aa1f72b298f3381e3ddf2470d905a0232d922482c9e'
D8_REFERENCE_SECTOR_SHA='f3bb072804355148349e8e719d332d8783f006abebc336da0026915e5dd91a7b'
CONTROLS_REFERENCE_PREFIX_SHA='8eabee637bec3d54c42dbf725a588c67b65f6d55c52f346d8bbcb73cd0a7bbc7'
CONTROLS_REFERENCE_SECTOR_SHA='d836c5ea1f432ebf63b2fd3759433eb6b240006276ffc54164511e47fbcd533c'
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
 require(hold.get('schema')==4 and hold.get('port')=='GPIOD' and hold.get('pin')==12 and hold.get('mode')=='usb-off' and hold.get('shutdown_proof_schema')==5,'USB must keep PD12 HOLD off, including shutdown refusal and return')
 require(profile in ('pd12-hold','pd12-knob-controls','legacy-october28'),'USB PD12 HOLD must not be combined with a different capture HOLD pin')
 require(not(force_capture and profile in ('pd12-hold','pd12-knob-controls')),'Forced capture is not supported by the PD12 USB-off package; use a cable-absent battery capture')

def validate_controls_profile(profile,capture_controls=True):
 """A default build cannot silently fall back to a different knob algorithm."""
 if capture_controls:
  require(profile=='pd12-knob-controls','Canonical controls require the reviewed pd12-knob-controls capture; --legacy-knobs is only for historical reproduction')
 else:
  require(profile in ('pd12-hold','legacy-october28'),'Legacy knob patches require the reviewed fixed-settings capture; never combine them with CKN1 controls')

def validate_usb_controls_sources(manifest):
 """Do not combine CKN1 capture with an older USB exporter that omits it.

 Source paths are normalized for both archived Windows and portable builds.
 The normal USB image validation separately binds its bytes to this manifest.
 """
 sources=manifest.get('sources',{})
 require(isinstance(sources,dict),'Canonical controls require a USB build with CKN1 metadata support')
 for name in ('capture_controls.h','storage/photo_store.c'):
  key='firmware/usb-ptp/'+name
  bindings=[value for path,value in sources.items() if path.replace('\\','/')==key]
  # Archived Windows manifests hash CRLF files; portable builds may use LF.
  # Accept either encoding of the same source, never a different implementation.
  source=(HERE/name).read_bytes().replace(b'\r\n',b'\n')
  identities={sha(source),sha(source.replace(b'\n',b'\r\n'))}
  require(len(bindings)==1 and bindings[0] in identities,'Canonical controls require the matching CKN1 metadata-capable USB build: '+name)

def validate_reference(original,sector,manifest):
 profile=reference_identity(original,sector)
 require(manifest.get('stage1_raw_sha256')==sha(original) and manifest.get('stage1_raw_bytes')==len(original) and manifest.get('program_sha256')==sha(sector) and manifest.get('program_bytes')==SECTOR_BYTES,'Original manifest is inconsistent with pinned artifacts')
 if profile in ('pa2-hold','pe9-hold','pd12-hold','pd12-knob-controls'):
  hold=manifest.get('raw_slots',{}).get('gpio_hold_contract',{})
  expected={'pa2-hold':(3,'GPIOA',2),'pe9-hold':(4,'GPIOE',9),'pd12-hold':(5,'GPIOD',12),'pd12-knob-controls':(5,'GPIOD',12)}[profile]
  require((hold.get('schema'),hold.get('port'),hold.get('pin'))==expected,'Capture requires its independently reviewed pin/schema HOLD contract')
  require(struct.unpack_from('<I',original,4)[0]==0x34181DF1,'Early HOLD reset vector changed')
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
 if identity==(D3_REFERENCE_PREFIX_SHA,D3_REFERENCE_SECTOR_SHA):return 'pe9-hold'
 if identity==(D8_REFERENCE_PREFIX_SHA,D8_REFERENCE_SECTOR_SHA):return 'pd12-hold'
 if identity==(CONTROLS_REFERENCE_PREFIX_SHA,CONTROLS_REFERENCE_SECTOR_SHA):return 'pd12-knob-controls'
 raise ValueError('Capture bytes differ from independently reviewed reference builds')

def tool(name):
 """Path of one compiler tool; see the module description for the search order."""
 folders=[Path(os.environ['GLOBAL_X_TOOLCHAIN'])] if os.environ.get('GLOBAL_X_TOOLCHAIN') else []
 for candidate in [f/n for f in folders+[TC] for n in (name+'.exe',name)]:
  if candidate.is_file():return str(candidate)
 found=shutil.which(name);require(found is not None,'Compiler tool not found: '+name)
 return found

def recorded(path):
 """Build inputs inside the repository are recorded relative to its root, so a
 package made on one machine can be checked on another."""
 path=path.resolve()
 return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)

def located(path):
 """Inverse of recorded()."""
 return path if Path(path).is_absolute() else ROOT/path

def knob_sites(original):
 """Addresses in the loaded capture prefix that knob.c edits in RAM: the
 manual-exposure register block and the MOVW holding the frame length."""
 manual=knob_tables.manual_block()
 # movw r1,#frame; movs r2,#2; mov.w r0,#0x458: the arguments of write_value(0x0458,frame,2).
 frame=knob_tables.movw_r1(knob_tables.DEFAULT_FRAME)+bytes.fromhex('02224ff48b60')
 require(original.count(manual)==1 and original.count(frame)==1,'Capture prefix exposure or frame-length site is not unique')
 manual_at,frame_at=original.index(manual),original.index(frame)
 require(not frame_at&1 and original.count(struct.pack('<I',PREFIX_BASE+manual_at))==1,'Capture prefix exposure sites are not addressed as expected')
 require(max(manual_at+len(manual),frame_at+4)<=HOOK_BASE-PREFIX_BASE and not manual_at<=PATCH_OFFSET<manual_at+len(manual),'Knob sites overlap the boot hook')
 return PREFIX_BASE+manual_at,PREFIX_BASE+frame_at

def branch_target(instruction,address):
 """Decode only unconditional Thumb-2 B.W; reject BL, BLX and conditional B."""
 require(len(instruction)==4,'Patch must be one four-byte B.W')
 hi,lo=struct.unpack('<HH',instruction)
 require(hi&0xF800==0xF000 and lo&0xD000==0x9000,'Patch must be B.W, never a linking/conditional branch')
 sign=(hi>>10)&1;i1=1^((lo>>13)&1)^sign;i2=1^((lo>>11)&1)^sign
 displacement=(sign<<24)|(i1<<23)|(i2<<22)|((hi&0x3FF)<<12)|((lo&0x7FF)<<1)
 if sign:displacement-=1<<25
 return address+4+displacement

def compose(original,sector,patch,hook,selector,usb,*,capture_controls=True):
 """Build sectors only after validating every fixed-region boundary."""
 profile=reference_identity(original,sector)
 validate_controls_profile(profile,capture_controls)
 require(branch_target(patch,PATCH_ADDRESS)==HOOK_BASE,'Patch target differs from hook')
 require(0<len(hook)<=PREFIX_END-HOOK_BASE and hook[:4]==DSB,'Hook exceeds prefix room or omits displaced DSB')
 require(0<len(selector)<=USB_FLASH-SELECTOR_FLASH,'Selector overlaps USB NOR image')
 require(8<=len(usb)<=USB_MAX_BYTES,'USB image exceeds reserved NOR region')
 base=original
 if capture_controls:
  sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
  import knob_transform
  base,_=knob_transform.patch_prefix(original)
 prefix=base[:PATCH_OFFSET]+patch+base[PATCH_OFFSET+4:]+hook
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

def argument_parser():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--usb',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--force-capture',action='store_true');p.add_argument('--capture',type=Path,required=True,help='Exact reviewed staged capture build; default requires the pd12-knob-controls reference')
 profiles=p.add_mutually_exclusive_group()
 profiles.add_argument('--capture-controls',dest='capture_controls',action='store_true',help='Explicit alias for the default source-built CKN1 controls profile')
 profiles.add_argument('--legacy-knobs',dest='capture_controls',action='store_false',help='Historical reproduction only: runtime prefix edits and the old exposure-check bypass')
 p.set_defaults(capture_controls=True)
 p.add_argument('--hal',type=Path,help='STM32N6xx_HAL_Driver directory, v1.3.0 (default: the SDK copy under tmp/)');p.add_argument('--cmsis',type=Path,help='CMSIS directory (default: the SDK copy under tmp/)')
 return p

def main():
 a=argument_parser().parse_args()
 m=json.loads((a.usb/'manifest.json').read_text(encoding='utf-8'));usb=(a.usb/'usb.bin').read_bytes();validate_usb_image(m,usb)
 original=(a.capture/'stage1.bin').read_bytes();sector=(a.capture/'capture_sector_0.bin').read_bytes();reference_manifest=json.loads((a.capture/'manifest.json').read_text(encoding='utf-8'));profile=validate_reference(original,sector,reference_manifest)
 validate_usb_hold_policy(m,profile,a.force_capture)
 validate_controls_profile(profile,a.capture_controls)
 if a.capture_controls:validate_usb_controls_sources(m)
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 frozen_names=('boot_read.h','boot_hook.c','boot_hook.S','selector.c','vbus.c','usb_hold.h','package.py')
 if a.capture_controls:frozen_names+=('capture_controls.h','capture_controls_map.c','capture_controls_adc.c','capture_controls_sensor.c','controls_entry.S')
 else:frozen_names+=('knob.c','knob_map.h','knob_tables.h','knob_tables.py','exposure_gate.py')
 for n in frozen_names:(out/n).write_bytes((HERE/n).read_bytes())
 (out/'stm32n6xx_hal_conf.h').write_bytes((a.usb/'stm32n6xx_hal_conf.h').read_bytes())
 config=f'#define USB_FLASH_OFFSET {hex(USB_FLASH)}U\n#define USB_BYTES {len(usb)}U\n#define USB_CRC {zlib.crc32(usb)}U\n#define USB_ENTRY {m["entry"]}U\n'
 (out/'boot_config.h').write_text(config,encoding='utf-8')
 if not a.capture_controls:
  manual_address,frame_address=knob_sites(original)
  (out/'knob_config.h').write_text(f'/* Generated by package.py from the capture prefix. */\n#define KNOB_MANUAL_ADDRESS {hex(manual_address)}U\n#define KNOB_FRAME_ADDRESS {hex(frame_address)}U\n',encoding='utf-8')
 sdk=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers';hal=(a.hal or sdk/'STM32N6xx_HAL_Driver').resolve();cmsis=(a.cmsis or sdk/'CMSIS').resolve()
 flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only','-Os','-flto','-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-nostartfiles','-DSTM32N657xx','-DUSE_HAL_DRIVER']
 for d in (out,hal/'Inc',cmsis/'Include',cmsis/'Device/ST/STM32N6xx/Include'):flags+=['-I'+str(d)]
 if a.force_capture:flags+=['-DUSB_BOOT_FORCE_CAPTURE=1']
 flags+=['-DCAPTURE_CONTROLS_ENABLED=1'] if a.capture_controls else ['-DLEGACY_KNOBS_ENABLED=1']
 def build(name,base,sources,entry,bss_limit):
  veneer=''
  if a.capture_controls and name=='selector':
   veneer='.selector_entry : { KEEP(*(.selector_entry)) } ASSERT(SIZEOF(.selector_entry)==4,"selector veneer") .controls_entry 0x34200100 : { KEEP(*(.controls_entry)) } ASSERT(SIZEOF(.controls_entry)==4,"controls veneer")'
  ld=out/(name+'.ld');ld.write_text(f'ENTRY({entry})\nSECTIONS {{ . = {hex(base)}; {veneer} .text : {{ KEEP(*(.text.entry)) KEEP(*(.text.hook)) *(.text*) *(.rodata*) }} .data : {{ *(.data*) }} . = ALIGN(4); __bss_start__ = .; .bss (NOLOAD) : {{ *(.bss*) *(COMMON) }} . = ALIGN(4); __bss_end__ = .; /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} ASSERT(. < {hex(bss_limit)},"overflow") }}',encoding='utf-8')
  subprocess.run([tool('arm-none-eabi-gcc'),*flags,*map(str,sources),'-T'+str(ld),'--specs=nosys.specs','-Wl,--build-id=none,--gc-sections','-o',str(out/(name+'.elf'))],check=True)
  subprocess.run([tool('arm-none-eabi-objcopy'),'-O','binary',str(out/(name+'.elf')),str(out/(name+'.bin'))],check=True)
  symbols=subprocess.check_output([tool('arm-none-eabi-nm'),'-n',str(out/(name+'.elf'))],text=True);(out/(name+'.symbols')).write_text(symbols,encoding='utf-8')
  listing=subprocess.check_output([tool('arm-none-eabi-objdump'),'-d',str(out/(name+'.elf'))],text=True);(out/(name+'.lst')).write_text(listing,encoding='utf-8')
  symbol=re.search(r'^([0-9a-f]+) [A-Za-z] '+re.escape(entry)+'$',symbols,re.M);require(symbol is not None,'Missing linked entry: '+entry)
  address=int(symbol[1],16);image=(out/(name+'.bin')).read_bytes();require(base<=address<base+len(image) and not address&1,'Linked entry outside image')
  return image,address
 selector_sources=[out/'selector.c',out/'vbus.c']
 if not a.capture_controls:selector_sources += [out/'knob.c']
 selector_sources += [hal/'Src/stm32n6xx_hal_adc.c',hal/'Src/stm32n6xx_hal_adc_ex.c',hal/'Src/stm32n6xx_hal_rcc.c']
 if a.capture_controls:selector_sources += [out/n for n in ('capture_controls_map.c','capture_controls_adc.c','capture_controls_sensor.c','controls_entry.S')]
 selector,entry=build('selector',SELECTOR_LOAD,selector_sources,'usb_selector',SELECTOR_LIMIT)
 if a.capture_controls:
  require(entry==SELECTOR_LOAD,'Controls selector veneer moved')
  symbols=(out/'selector.symbols').read_text()
  for name,address in [('capture_controls_sensor_entry',0x34200100)]:
   require(re.search(r'^'+format(address,'08x')+r' T '+name+r'$',symbols,re.M),'Controls helper entry moved')
  for offset,name in [(0,'usb_selector_body'),(0x100,'capture_controls_sensor_apply')]:
   symbol=re.search(r'^([0-9a-f]+) [A-Za-z] '+name+r'$',symbols,re.M)
   require(symbol is not None and branch_target(selector[offset:offset+4],SELECTOR_LOAD+offset)==int(symbol[1],16),'Controls veneer target differs')
 require(0<len(selector)<=USB_FLASH-SELECTOR_FLASH,'Selector overlaps USB NOR image')
 config+=f'#define SELECTOR_BYTES {len(selector)}U\n#define SELECTOR_CRC {zlib.crc32(selector)}U\n#define SELECTOR_ENTRY {entry|1}U\n';(out/'boot_config.h').write_text(config,encoding='utf-8')
 hook,hook_entry=build('hook',HOOK_BASE,[out/'boot_hook.S',out/'boot_hook.c'],'usb_boot_hook',PREFIX_END)
 require(hook_entry==HOOK_BASE,'Hook entry moved from appended prefix start')
 # Assemble through the real linker, then independently decode the result.
 (out/'patch.S').write_text('.syntax unified\n.thumb\n.global patch\npatch:\n b.w '+hex(hook_entry)+'\n',encoding='utf-8')
 subprocess.run([tool('arm-none-eabi-gcc'),'-mcpu=cortex-m55','-mthumb','-nostdlib','-Wl,--build-id=none,-Ttext='+hex(PATCH_ADDRESS)+',-e,patch',str(out/'patch.S'),'-o',str(out/'patch.elf')],check=True)
 subprocess.run([tool('arm-none-eabi-objcopy'),'-O','binary',str(out/'patch.elf'),str(out/'patch.bin')],check=True)
 prefix,boot,sector0,sector1=compose(original,sector,(out/'patch.bin').read_bytes(),hook,selector,usb,capture_controls=a.capture_controls)
 # Only the historical profile needs its fixed-exposure check opened. The
 # controls profile has a rebuilt dynamic receiver and preserves its bytes.
 if not a.capture_controls:
  sector0,gate=exposure_gate.open_gate(sector0,reference_manifest)
  require(exposure_gate.close_gate(sector0,gate)[CAPTURE_OFFSET:]==sector[CAPTURE_OFFSET:] and sector0[:CAPTURE_OFFSET]==boot+sector[len(boot):CAPTURE_OFFSET],'Capture code changed beyond the exposure gate')
 for name,data in (('stage1.bin',prefix),('sector0.bin',sector0),('sector1.bin',sector1)):(out/name).write_bytes(data)
 recovery=out/'recovery';recovery.mkdir();(recovery/'stage1.bin').write_bytes(prefix);(recovery/'capture_sector_0.bin').write_bytes(sector0)
 (recovery/'manifest.json').write_text(json.dumps(recovery_manifest(reference_manifest,prefix,boot,sector0),indent=2)+'\n',encoding='utf-8')
 result=dict(schema=1,usb_sha256=sha(usb),usb_build=recorded(a.usb),prefix_sha256=sha(prefix),prefix_bytes=len(prefix),sector0_sha256=sha(sector0),sector1_sha256=sha(sector1),hook_bytes=len(hook),selector_bytes=len(selector),selector_entry=entry|1,hook_entry=hook_entry,patch_address=PATCH_ADDRESS,patch_encoding='B.W',original_instruction='DSB',resumes_at=RESUME_ADDRESS,original_prefix_sha256=sha(original),original_sector_sha256=sha(sector),uart_guard_unchanged=True,force_capture=a.force_capture,boot=inspect_image(boot),recovery_directory='recovery',recovery_allowlist_admission=False,sources={name:sha((out/name).read_bytes()) for name in frozen_names})
 result.update(capture_build=recorded(a.capture),capture_profile=profile,gpio_hold=copy.deepcopy(reference_manifest.get('raw_slots',{}).get('gpio_hold_contract')),usb_hold_policy=copy.deepcopy(m['gpio_hold']),hardware_status='offline-only-not-installed')
 result['build_profile']='canonical-ckn1' if a.capture_controls else 'historical-runtime-knobs'
 compiler=subprocess.check_output([tool('arm-none-eabi-gcc'),'--version'],text=True).splitlines()[0]
 hal_sources={n:sha((hal/'Src'/n).read_bytes().replace(b'\r\n',b'\n')) for n in ('stm32n6xx_hal_adc.c','stm32n6xx_hal_adc_ex.c','stm32n6xx_hal_rcc.c')}
 result.update(compiler=compiler,hal_sources_lf_sha256=hal_sources)
 if a.capture_controls:
  result['unchanged_capture_from_offset']=CAPTURE_OFFSET
  import knob_transform
  _,controls_patch=knob_transform.patch_prefix(original)
  result['capture_controls']=dict(schema=1,record=0x343F9400,record_bytes=128,manual=0x343F9440,helper=0x34200101,selector_limit=USB_FLASH-SELECTOR_FLASH,settle_ms=10,usb_sampling='confirmed-absent-only',patch=controls_patch)
 else:
  result.update(capture_from_offset=CAPTURE_OFFSET,capture_changes='exposure_gate only',exposure_gate=gate,knob=dict(schema=1,manual_address=manual_address,frame_address=frame_address,proof_pointer_word=9,result_word=10,
   default_lines=knob_tables.DEFAULT_LINES,default_frame=knob_tables.DEFAULT_FRAME,min_lines=knob_tables.MIN_LINES,max_lines=knob_tables.MAX_LINES,frame_margin=knob_tables.FRAME_MARGIN,line_ns=knob_tables.LINE_NS,gain_code_max=knob_tables.GAIN_CODE_MAX,code_low=knob_tables.CODE_LOW,code_high=knob_tables.CODE_HIGH))
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
