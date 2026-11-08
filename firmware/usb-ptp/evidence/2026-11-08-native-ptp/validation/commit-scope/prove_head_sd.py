from pathlib import Path
import hashlib, json, shutil, subprocess, sys
root=Path.cwd();campaign=root/'tmp/bringup/usb-ptp-commit-20261108';shadow=campaign/'head-sd-source';out=campaign/'head-sd-build'
shadow.mkdir(exist_ok=False);out.mkdir(exist_ok=False)
ref=root/'tmp/bringup/usb-ptp-20261108/ram08'
m=json.loads((ref/'manifest.json').read_text())
# Mirror only source, never mutable working-tree firmware outside the USB owner.
for original in (root/'firmware/usb-ptp').rglob('*'):
    rel=original.relative_to(root/'firmware/usb-ptp')
    if not original.is_file() or any(x in rel.parts for x in ('evidence','__pycache__')):continue
    if original.suffix.lower() not in ('.c','.h','.s','.ld'):continue
    dest=shadow/'firmware/usb-ptp'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original.read_bytes())
tracked=['firmware/sd-storage/sd_card.c','firmware/sd-storage/sd_card.h','firmware/raw-slots/magic_slots.h']
for name in tracked:
    data=subprocess.check_output(['git','show','HEAD:'+name],cwd=root)
    dest=shadow/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
(out/'stm32n6xx_hal_conf.h').write_bytes((ref/'stm32n6xx_hal_conf.h').read_bytes())
sys.path.insert(0,str(root/'firmware/capture-timing'));from build_raw10 import TC
flags=[]
for flag in m['flags']:
    if flag.startswith('-I'):
        path=Path(flag[2:])
        if path==ref:path=out
        elif path.is_relative_to(root/'firmware/usb-ptp'):path=shadow/path.relative_to(root)
        flag='-I'+str(path)
    flags.append(flag)
sources=[]
for name in m['sources']:
    if Path(name).suffix not in ('.c','.S'):continue
    path=root/name
    if path.is_relative_to(root/'firmware'):path=shadow/name
    sources.append(path)
argv=[str(TC/'arm-none-eabi-gcc.exe'),*flags,*map(str,sources),'-T'+str(shadow/'firmware/usb-ptp/usb.ld'),'-Wl,--build-id=none,--gc-sections','--specs=nosys.specs','-o',str(out/'usb.elf')]
(campaign/'head-sd-build-command.json').write_text(json.dumps(argv,indent=2)+'\n')
p=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);p.check_returncode()
subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'usb.elf'),str(out/'usb.bin')],check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
code=(out/'usb.bin').read_bytes();expected=(ref/'usb.bin').read_bytes()
report={'schema':1,'head_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'original_usb_sha256':sha(ref/'usb.bin'),'head_sd_usb_sha256':sha(out/'usb.bin'),'bytes':len(code),'exact_match':code==expected,'head_sources':{n:sha(shadow/n) for n in tracked},'working_tree_sd_unchanged':True,'hardware_access':False,'build_command':'head-sd-build-command.json'}
(campaign/'head-sd-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert report['exact_match']
