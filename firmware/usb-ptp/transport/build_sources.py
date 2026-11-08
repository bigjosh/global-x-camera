"""Offline build inputs for the PTP USB transport; never touches instruments."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SDK=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers'
HAL=SDK/'STM32N6xx_HAL_Driver'
CMSIS=SDK/'CMSIS'
CORE=HERE/'vendor/st-usbd/Core'

def sources():
    """Add these seven sources to the application's existing HAL/platform build."""
    return [HERE/'usb_ptp_transport.c',*sorted((CORE/'Src').glob('*.c')),
            *[HAL/'Src'/x for x in ('stm32n6xx_hal_pcd.c','stm32n6xx_hal_pcd_ex.c','stm32n6xx_ll_usb.c')]]

def includes():
    return [HERE,CORE/'Inc',HAL/'Inc',CMSIS/'Include',CMSIS/'Device/ST/STM32N6xx/Include']

def defines():
    return ['USE_USB_HS','HAL_PCD_MODULE_ENABLED']

def verify_vendor():
    manifest=json.loads((HERE/'vendor/st-usbd/UPSTREAM.json').read_text())
    for rel,digest in manifest['files'].items():
        if hashlib.sha256((HERE/'vendor/st-usbd'/rel).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Modified vendor core: {rel}')
    return manifest['commit']

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gcc',type=Path)
    a=parser.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    compiler=a.gcc
    if compiler is None:
        import sys
        sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
        from build_raw10 import TC
        compiler=TC/'arm-none-eabi-gcc.exe'
    revision=verify_vendor()
    shutil.copyfile(ROOT/'tmp/bringup/x-cube-n6-camera-capture/Inc/stm32n6xx_hal_conf.h',out/'stm32n6xx_hal_conf.h')
    flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only',
           '-Os','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections',
           '-Wall','-Wextra','-Werror','-DSTM32N657xx','-DUSE_HAL_DRIVER','-DUSE_USB_HS']
    flags+=['-I'+str(x) for x in [out,*includes()]]
    for profile,extra in [('irq',[]),('poll',['-DUSB_PTP_USE_IRQ=0']),('fs',['-DUSB_PTP_FORCE_FS=1'])]:
        for src in sources():
            obj=out/(profile+'-'+src.stem+'.o')
            subprocess.run([str(compiler),*flags,*extra,'-c',str(src),'-o',str(obj)],check=True)
    result={'compiled_sources':len(sources()),'profiles':['irq','poll','fs'],'vendor_commit':revision,
            'hardware_executed':False,'sources':[str(x) for x in sources()]}
    (out/'compile.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
