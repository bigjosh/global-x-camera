"""Build a RAM-only A3/A4/A5 ADC diagnostic. No instrument imports or access."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sdk=ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers'
    hal=sdk/'STM32N6xx_HAL_Driver';cmsis=sdk/'CMSIS'
    sources=['control.c','entry.S','control.ld']
    for name in sources:shutil.copyfile(HERE/name,out/name)
    conf=(ROOT/'tmp/bringup/x-cube-n6-camera-capture/Inc/stm32n6xx_hal_conf.h').read_text()
    conf=conf.replace('// #define HAL_ADC_MODULE_ENABLED','#define HAL_ADC_MODULE_ENABLED')
    (out/'stm32n6xx_hal_conf.h').write_text(conf)
    sources+=['stm32n6xx_hal_conf.h']
    for name in ('stm32n6xx_hal_adc.c','stm32n6xx_hal_adc_ex.c'):
        shutil.copyfile(hal/'Src'/name,out/name);sources.append(name)
    flags=['-mcpu=cortex-m55','-mthumb','-mcmse','-mfloat-abi=soft','-mgeneral-regs-only',
        '-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
        '-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections',
        '-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-DSTM32N657xx','-DUSE_HAL_DRIVER',
        '-I'+str(out),'-I'+str(hal/'Inc'),'-I'+str(cmsis/'Include'),'-I'+str(cmsis/'Device/ST/STM32N6xx/Include')]
    compile_sources=[str(out/name) for name in sources if name.endswith(('.c','.S'))]
    subprocess.run([str(TC/'arm-none-eabi-gcc.exe'),*flags,'-T'+str(out/'control.ld'),*compile_sources,
        '-Wl,--build-id=none,--gc-sections','-o',str(out/'control.elf')],check=True)
    subprocess.run([str(TC/'arm-none-eabi-objcopy.exe'),'-O','binary',str(out/'control.elf'),str(out/'control.bin')],check=True)
    symbols=subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-n',str(out/'control.elf')],text=True)
    (out/'symbols.txt').write_text(symbols)
    (out/'control.lst').write_text(subprocess.check_output([str(TC/'arm-none-eabi-objdump.exe'),'-d',str(out/'control.elf')],text=True))
    def sym(name):return int(re.search(r'^([0-9a-f]+) [A-Za-z] '+name+r'$',symbols,re.M)[1],16)
    code=(out/'control.bin').read_bytes()
    assert not subprocess.check_output([str(TC/'arm-none-eabi-nm.exe'),'-u',str(out/'control.elf')]).strip()
    assert len(code)<0x10000 and code[sym('control_park')-0x34300000:sym('control_park')-0x34300000+2]==b'\xfe\xe7'
    fields=[x.strip() for x in re.search(r'enum \{(.*?)\};',(out/'control.c').read_text(),re.S)[1].split(',')][:-1]
    assert len(fields)<=64
    m=dict(schema=1,kind='exposure-knob-adc-ram',load=0x34300000,entry=sym('control_entry')|1,
        park=sym('control_park'),proof=0x343C2000,proof_words=64,proof_sequence_end_word=63,request=0x343C1F00,request_words=8,
        request_magic=0x31544F50,stop_magic=0x504F5453,stack=0x343B0000,stack_floor=0x343AF000,
        bss_start=sym('__bss_start__'),bss_end=sym('__bss_end__'),fields=fields,
        bytes=len(code),sha256=hashlib.sha256(code).hexdigest(),flags=flags,core_hz=400000000,
        adc='ADC1_INP16/PF3',resolution_bits=12,adc_source='HCLK/32',
        wiring={'low':'A3/CN4.4/PA2','wiper':'A4/CN4.5/PF3','high':'A5/CN4.6/PH2','hold':'D9/CN14.2/PD7'},
        sd_commands=False,nor_commands=False,camera_commands=False,reset=False,power_switch=False,
        terminal_policy='A5 LOW; PD7 HOLD remains HIGH; debug awake park',
        sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in sources})
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
if __name__=='__main__':main()
