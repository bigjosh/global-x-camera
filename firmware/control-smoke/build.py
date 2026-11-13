"""Build a RAM-only A0/A1/A2 ADC diagnostic with D8 HOLD. No instruments."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from build_raw10 import TC

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--vrefbuf-clock',action='store_true',help='Match vendor VREFBUF peripheral clock; retain external reference mode')
    p.add_argument('--adc-hsi8',action='store_true',help='Use already-ready HSI divided by8 for ADC only; leave all system clocks unchanged')
    p.add_argument('--internal-vref',action='store_true',help='Also measure ADC1 internal0.8V reference with separate coherent telemetry')
    a=p.parse_args()
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
    if a.vrefbuf_clock:flags.append('-DCONTROL_VREFBUF_CLOCK=1')
    if a.adc_hsi8:flags.append('-DCONTROL_ADC_HSI8=1')
    if a.internal_vref:flags.append('-DCONTROL_INTERNAL_VREF=1')
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
    assert len(fields)==63
    m=dict(schema=5,kind='exposure-knob-adc-ram',load=0x34300000,entry=sym('control_entry')|1,
        park=sym('control_park'),proof=0x343C2000,proof_words=64,proof_sequence_end_word=63,request=0x343C1F00,request_words=8,
        request_magic=0x31544F50,stop_magic=0x504F5453,stack=0x343B0000,stack_floor=0x343AF000,
        bss_start=sym('__bss_start__'),bss_end=sym('__bss_end__'),fields=fields,
        bytes=len(code),sha256=hashlib.sha256(code).hexdigest(),flags=flags,core_hz=400000000,
        adc='ADC1_INP10/PA9',resolution_bits=12,adc_source='HSI/8' if a.adc_hsi8 else 'HCLK/32',
        adc_clock_probe={'address':0x343C2100,'words':['HSICFGR','RCC_SR','nominal_adc_hz','CCIPR1']} if a.adc_hsi8 else None,
        internal_vref_probe={'address':0x343C2200,'magic':0x46455256,'words':['magic','sequence','raw','min','max','count','ADC12_CCR','ADC1_CFGR2','ADC1_GCOMP','ADC1_OR','VREF_SQR1','CALFACT','milliseconds','nonce','reserved','sequence_end'],'expected_typical_volts':0.8,'settle_ms':10} if a.internal_vref else None,
        adc_security_probe={'address':0x343C2300,'magic':0x43455341,'words':['magic','RIF_SEC2_before','RIF_SEC2_after','RIF_PRIV2_before','RIF_PRIV2_after','GPIOA_SEC','GPIOF_SEC','GPIOC_SEC','AHB3ENR_before','AHB3ENR_after','validated','nonce'],'mutation':'RIFSC RISC_SECCFGRx[2] bit0 only'},
        vrefbuf_clock=a.vrefbuf_clock,vrefbuf_mode='external ENVR=0,HIZ=1' if a.vrefbuf_clock else 'untouched',
        reserved53='VREFBUF CSR before low16 / after high16' if a.vrefbuf_clock else 'reserved',
        endpoint_channels={'A0':'ADC1_INP5/PA8','A2':'ADC1_INP11/PA10'},
        wiring={'low':'A0/CN4.1/PF5','wiper':'A1/CN4.2/PA9','high':'A2/CN4.3/PF6','hold':'D8/CN14.1/PD12'},
        digital_wiper='PC10 input/no-pull',retired_hold='PA2 and PA12 untouched',
        sd_commands=False,nor_commands=False,camera_commands=False,reset=False,power_switch=False,
        terminal_policy='A2 LOW; PD12/D8 HOLD remains HIGH; debug awake park',
        sources={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in sources})
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
if __name__=='__main__':main()
