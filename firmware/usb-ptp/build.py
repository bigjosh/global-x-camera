"""Build USB PTP SRAM firmware; never accesses instruments."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--test-read-fault-lba',type=int,default=0);a=p.parse_args()
 if not 0<=a.test_read_fault_lba<0xFFFFFFFF:p.error('test LBA must fit uint32')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 sdk=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers';hal=sdk/'STM32N6xx_HAL_Driver';cmsis=sdk/'CMSIS'
 conf=(ROOT/'tmp/bringup/x-cube-n6-camera-capture/Inc/stm32n6xx_hal_conf.h').read_text(encoding='utf-8')
 for name in ('PCD','RCC','PWR','GPIO','CORTEX','ADC'):conf=conf.replace('// #define HAL_'+name+'_MODULE_ENABLED','#define HAL_'+name+'_MODULE_ENABLED')
 (out/'stm32n6xx_hal_conf.h').write_text(conf,encoding='utf-8')
 src=[HERE/n for n in ('entry.S','main.c','vbus.c','shutdown.c','ptp.c','storage/photo_store.c','thumbnail/thumbnail_bmp.c','transport/usb_ptp_transport.c')]
 src+=[ROOT/'firmware/sd-storage/sd_card.c']
 src+=list((HERE/'transport/vendor/st-usbd/Core/Src').glob('*.c'))
 src+=[hal/'Src'/n for n in ('stm32n6xx_hal_adc.c','stm32n6xx_hal_adc_ex.c')]
 src+=[hal/'Src'/n for n in ('stm32n6xx_hal_pcd.c','stm32n6xx_hal_pcd_ex.c','stm32n6xx_ll_usb.c','stm32n6xx_hal_rcc.c','stm32n6xx_hal_rcc_ex.c','stm32n6xx_hal_pwr.c','stm32n6xx_hal_pwr_ex.c','stm32n6xx_hal_cortex.c','stm32n6xx_hal_gpio.c','stm32n6xx_hal_rif.c')]
 flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-nostartfiles','-DSTM32N657xx','-DUSE_HAL_DRIVER','-DUSE_USB_HS','-DUSB_PTP_USE_IRQ=0','-DSD_BUS_WIDTH=4','-DSD_REVIEW_PROFILE=1','-DSD_STARTUP_OPT=1','-DSD_CLOCK_NEGEDGE=1','-DSD_CLOCK_NEGEDGE_INIT=1']
 flags+=['-DUSB_TEST_READ_FAULT_LBA='+str(a.test_read_fault_lba)+'U']
 for d in (out,HERE,HERE/'transport',HERE/'transport/vendor/st-usbd/Core/Inc',hal/'Inc',cmsis/'Include',cmsis/'Device/ST/STM32N6xx/Include'):flags+=['-I'+str(d)]
 subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,*map(str,src),'-T'+str(HERE/'usb.ld'),'-Wl,--build-id=none,--gc-sections','--specs=nosys.specs','-o',str(out/'usb.elf')],check=True)
 subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'usb.elf'),str(out/'usb.bin')],check=True)
 symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(out/'usb.elf')],text=True);(out/'symbols.txt').write_text(symbols,encoding='utf-8')
 def sym(n):return int(re.search(r'^([0-9a-f]+) [A-Za-z] '+n+'$',symbols,re.M)[1],16)
 code=(out/'usb.bin').read_bytes()
 frozen=out/'source'
 for source in src+[HERE/'usb.ld',HERE/'build.py',HERE/'ptp.h',HERE/'shutdown.h',HERE/'usb_hold.h',HERE/'capture_controls.h',HERE/'storage/photo_store.h',HERE/'transport/usb_ptp_transport.h',HERE/'transport/usbd_conf.h',HERE/'thumbnail/thumbnail_bmp.h',ROOT/'firmware/sd-storage/sd_card.h']:
  target=frozen/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
 m=dict(schema=1,kind='usb-ptp-ram',load=0x34300000,entry=sym('usb_entry')|1,park=sym('usb_park'),proof=0x343F8000,proof_words=64,request=0x343F7F00,stack=0x343F0000,bss_start=sym('__bss_start__'),bss_end=sym('__bss_end__'),bytes=len(code),sha256=hashlib.sha256(code).hexdigest(),flags=flags,sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in src+[HERE/'usb.ld',HERE/'usb_hold.h',HERE/'capture_controls.h']})
 m['gpio_hold']=dict(schema=4,port='GPIOD',pin=12,header='Arduino D8 / CN14.1',mode='usb-off',shutdown_proof_schema=5,release='low-from-usb-selection-input-no-pull-at-wfi',uart_recovery='PE6-unchanged')
 (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');print(json.dumps(m,indent=2))
if __name__=='__main__':main()
