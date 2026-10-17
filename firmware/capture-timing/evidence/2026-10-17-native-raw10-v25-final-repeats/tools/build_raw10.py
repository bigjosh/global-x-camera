"""Offline native RAW10 relocation from hash-checked frozen capture builds.

Creates a separate receiver/prefix image; never invokes instruments, a debugger,
or a flash loader. Does not edit the shared capture/build sources.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VENDOR = ROOT / 'tmp/bringup/x-cube-n6-camera-capture'
TC = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')
sys.path.insert(0, str(ROOT / 'firmware/boot-timing'))
from add_boot_header import make_image, inspect_image

VECTOR, STACK, FRAME, FRAME_BYTES = 0x34300000, 0x343B0000, 0x34000000, 3055360
FLASH_OFFSET = 0x2000
ADDRESS_FIELDS = {
    'trace_address': '0x343f0000', 'event_address': '0x343f0100',
    'error_address': '0x343f1000', 'prefix_status_address': '0x343f3000',
    'sensor_status_address': '0x343f4000', 'memory_status_address': '0x343f5000',
    'raw10_status_address': '0x343f6000', 'memory_bootstrap_address': '0x341f5000',
    'frame_address': hex(FRAME), 'frame_bytes': FRAME_BYTES,
    'pixel_format': 'raw10_le16', 'bytes_per_pixel': 2, 'sample_bits': 10,
    'sample_alignment': 'right',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(text, old, new, expected=1):
    if text.count(old) != expected:
        raise ValueError(f'Frozen-source pattern mismatch: {old!r}')
    return text.replace(old, new)


def relocate_diagnostics(text):
    return re.sub(r'0x341([Ff][0-9A-Fa-f]{4})', r'0x343\1', text)


def checked_manifest(folder):
    manifest = json.loads((folder / 'manifest.json').read_text())
    for path, expected in manifest['sources'].items():
        source = ROOT / path
        if sha(source.read_bytes()) != expected:
            raise ValueError(f'Frozen source changed: {source}')
    return manifest


def compile_sources(out, sources, flags, linker, name, libc=False):
    gcc = str(TC / 'arm-none-eabi-gcc.exe')
    objects = []
    for i, source in enumerate(sources):
        obj = out / f'{i:02d}_{source.stem}.o'
        subprocess.run([gcc, *flags, '-c', str(source), '-o', str(obj)], check=True)
        objects.append(obj)
    elf = out / f'{name}.elf'
    runtime = ['-nostartfiles', '--specs=nano.specs', '--specs=nosys.specs'] if libc else ['-nostdlib']
    libraries = ['-lc', '-lm', '-lnosys'] if libc else []
    subprocess.run([gcc, *flags, *runtime, '-T', str(linker), *map(str, objects),
                    '-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments',
                    f'-Wl,-Map={out / (name + ".map")}', *libraries, '-o', str(elf)], check=True)
    binary = out / f'{name}.bin'
    subprocess.run([str(TC / 'arm-none-eabi-objcopy.exe'), '-O', 'binary', str(elf), str(binary)], check=True)
    symbols = subprocess.check_output([str(TC / 'arm-none-eabi-nm.exe'), '--numeric-sort', str(elf)], text=True)
    assert not re.search(r'\b(HAL_BSEC_OTP_Program|Fuse_Programming|BSP_XSPI_NOR_(?:Write|Erase)\w*)$', symbols, re.M)
    (out / 'symbols.txt').write_text(symbols)
    (out / f'{name}.lst').write_bytes(subprocess.check_output([str(TC / 'arm-none-eabi-objdump.exe'), '-d', str(elf)]))
    return binary.read_bytes(), subprocess.check_output([str(TC / 'arm-none-eabi-size.exe'), str(elf)], text=True)


def write_manifest(out, manifest, sources):
    manifest['sources'] = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sources}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receiver', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    receiver, prefix, out = args.receiver.resolve(), args.prefix.resolve(), args.output.resolve()
    rm, pm = checked_manifest(receiver), checked_manifest(prefix)
    assert rm['parameters']['receiver_only'] and rm['parameters']['stage2']
    assert rm['parameters']['rom_clocks'] and rm['parameters']['minimal_system_init']
    assert pm['early_sensor'] and pm['skip_sensor_reset'] and pm['word_reads']
    assert pm['stage2_sha256'] == rm['raw_sha256']
    assert sha((receiver / 'capture.bin').read_bytes()) == rm['raw_sha256']
    saved = args.snapshot.read_bytes()
    assert len(saved) == 65536 and sha(saved) == pm['snapshot_sha256']
    out.mkdir(parents=True, exist_ok=False)
    rdir, pdir = out / 'receiver', out / 'staged'
    rdir.mkdir(); pdir.mkdir()

    # Compile exact frozen inputs, changing only relocation/native sample depth.
    sources = []
    for source_name in rm['sources']:
        source = ROOT / source_name
        target = rdir / source.name
        text = source.read_text()
        if source.name == 'capture.c':
            text = relocate_diagnostics(text)
            text = replace(text, 'Native RAW8 dump', 'Native RAW10 padded16 dump')
            text = replace(text, '#define BYTES (WIDTH * HEIGHT)', '#define BYTES (WIDTH * HEIGHT * 2U)')
            text = replace(text, 'DCMIPP_CSI_DT_BPP8', 'DCMIPP_CSI_DT_BPP10')
            text = replace(text, 'DCMIPP_DT_RAW8', 'DCMIPP_DT_RAW10')
            marker = '  event(21);'
            text = replace(text, marker, '''  /* RM0486: RAW10 expands to16-bit right-aligned words. */
  CLEAR_BIT(DCMIPP->P0PPCR, DCMIPP_P0PPCR_PAD);
  check(0x80,HAL_DCMIPP_PIPE_EnableLimitEvent(&hcam,DCMIPP_PIPE0,BYTES/4U));
  volatile uint32_t *guard=(volatile uint32_t *)(0x34000000U+BYTES);
  for(unsigned i=0;i<8;++i) guard[i]=0xA15A1000U+i;
  __DSB();
''' + marker)
            marker = '  TRACE[44]=CSI->SR0; TRACE[45]=CSI->SR1;'
            text = replace(text, marker, marker + '''
  volatile uint32_t *raw10=(volatile uint32_t *)0x343F6000U;
  raw10[0]=0x52313046U; raw10[1]=DCMIPP->P0DCCNTR;
  raw10[2]=DCMIPP->P0PPCR; raw10[3]=DCMIPP->P0DCLMTR;
  raw10[4]=CSI->VC0CFGR1; raw10[5]=DCMIPP->P0FSCR;
  raw10[6]=DCMIPP->CMSR2; raw10[7]=0;
  volatile uint32_t *guard=(volatile uint32_t *)(0x34000000U+BYTES);
  for(unsigned i=0;i<8;++i) if(guard[i]!=(0xA15A1000U+i)) raw10[7]|=1U<<i;
  if(raw10[1]!=BYTES || raw10[7]) fail(0x81,-1);
''')
            marker = '  check(0x66,rd16(&sensor,0x0458,&coarse)); TRACE[58]=coarse;'
            text = replace(text, marker, marker + '''
  uint8_t raw_bits=0,raw_dt=0;
  check(0x82,rd8(&sensor,0x030A,&raw_bits));
  check(0x83,rd8(&sensor,0x030F,&raw_dt));
  raw10[8]=raw_bits; raw10[9]=raw_dt;
  if(raw_bits!=10U || raw_dt!=0x2BU) fail(0x84,-1);
''')
        target.write_text(text, encoding='utf-8', newline='\n')
        sources.append(target)

    link = (receiver / 'capture.ld').read_text()
    link = replace(link, 'ORIGIN = 0x34000000, LENGTH = 1536K', 'ORIGIN = 0x34000000, LENGTH = 0x2E9F00')
    link = replace(link, 'ORIGIN = 0x34190000, LENGTH =  111K', 'ORIGIN = 0x34300000, LENGTH = 0xB0000')
    link = replace(link, 'ORIGIN = 0x341f0000, LENGTH =   64K', 'ORIGIN = 0x343f0000, LENGTH =   64K')
    (rdir / 'capture.ld').write_text(link)
    fw = VENDOR / 'STM32Cube_FW_N6/Drivers'
    includes = [VENDOR/'Inc', fw/'CMSIS/Include', fw/'CMSIS/Device/ST/STM32N6xx/Include',
                fw/'STM32N6xx_HAL_Driver/Inc', fw/'STM32N6xx_HAL_Driver/Inc/Legacy',
                fw/'BSP/STM32N6xx_Nucleo', fw/'BSP/Components/Common', VENDOR/'Lib/Camera_Middleware/sensors/vd6g']
    flags = ['-mcpu=cortex-m55','-mthumb','-mcmse','-mfpu=fpv5-d16','-mfloat-abi=hard','-Os','-g3',
             '-ffunction-sections','-fdata-sections','-DNDEBUG','-DSTM32N657xx','-DSTM32N6570_NUCLEO_REV',
             '-Wall','-Wextra','-flto']
    defines = {'BUS_I2C2_FREQUENCY':'i2c_hz','BENCH_RESET_US':'reset_us','BENCH_POLL_US':'poll_us',
               'BENCH_STROBE':'strobe','BENCH_STOP_STAGE':'stop_stage','BENCH_ROM_CLOCKS':'rom_clocks',
               'BENCH_PREPARE_EARLY':'prepare_early','BENCH_GPIO_LEVEL':'gpio_level',
               'BENCH_COARSE_LINES':'coarse_lines','BENCH_BATCH_CONFIG':'batch_config',
               'BENCH_STAGE2':'stage2','BENCH_FRAME_LINES':'frame_lines',
               'BENCH_RECEIVER_EARLY':'receiver_before_ready','BENCH_CLOCK_DIAGNOSTICS':'clock_diagnostics'}
    flags += [f'-D{define}={int(rm["parameters"][param])}' for define, param in defines.items()]
    flags += [f'-I{path}' for path in includes]
    payload, size = compile_sources(rdir, sources, flags, rdir/'capture.ld', 'capture', libc=True)
    sp, entry = struct.unpack_from('<II', payload)
    assert sp == STACK and entry & 1 and VECTOR <= entry-1 < VECTOR+len(payload)
    assert len(payload) < 65536-FLASH_OFFSET
    manifest = copy.deepcopy(rm)
    manifest.update(ADDRESS_FIELDS)
    manifest.update(vector_address=hex(VECTOR), stack_pointer=hex(sp), entry_point=hex(entry),
                    raw_bytes=len(payload), raw_sha256=sha(payload), size=size, compile_flags=flags,
                    hardware_status='untested', frozen_receiver_manifest_sha256=sha((receiver/'manifest.json').read_bytes()),
                    frozen_linker_sha256=sha((receiver/'capture.ld').read_bytes()))
    manifest['parameters']['raw10_relocated'] = True
    write_manifest(rdir, manifest, sources+[rdir/'capture.ld'])

    psources = []
    for name in ['stage1.c', 'stage1.S', 'stage1_sensor.c', 'stage1.ld']:
        text = (prefix / name).read_text()
        if name in ('stage1.c', 'stage1_sensor.c'):
            text = relocate_diagnostics(text)
        if name == 'stage1.c':
            text = replace(text, '#define STAGE2_LOAD_ADDRESS 0x34190000U', '#define STAGE2_LOAD_ADDRESS 0x34300000U')
            text = replace(text, 'sp > 0x341B0000U', 'sp > 0x343B0000U')
            text = replace(text, 'void stage1_fault(void) { fail(FAULT); }', '''extern void raw10_memory_init(void);
extern void raw10_memory_fault(uint32_t reason) __attribute__((noreturn));
void stage1_fault(void) { raw10_memory_fault(0xF0U); }''')
            text = replace(text, '    for (uint32_t i=0; i<64U; ++i) TRACE[i]=0;',
                           '    raw10_memory_init();\n    for (uint32_t i=0; i<64U; ++i) TRACE[i]=0;')
        elif name == 'stage1_sensor.c':
            text = replace(text, 'write_value(0x030A,8,1)', 'write_value(0x030A,10,1)')
            text = replace(text, 'write_value(0x030F,0x2A,1)', 'write_value(0x030F,0x2B,1)')
        target = pdir/name
        target.write_text(text, encoding='utf-8', newline='\n')
        psources.append(target)
    target = pdir/'raw10_memory.c'
    target.write_bytes((HERE/'raw10_memory.c').read_bytes()); psources.append(target)
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    pflags = [flag for flag in pm['compile_flags'] if not flag.startswith(('-DSTAGE2_BYTES=', '-DSTAGE2_EXPECTED_CRC32='))]
    pflags += [f'-DSTAGE2_BYTES={len(payload)}U',f'-DSTAGE2_EXPECTED_CRC32=0x{crc:08X}U']
    raw, size = compile_sources(pdir, [s for s in psources if s.suffix!='.ld'], pflags, pdir/'stage1.ld', 'stage1')
    boot = make_image(raw)
    assert len(boot) <= FLASH_OFFSET
    (pdir/'stage1_boot.bin').write_bytes(boot); (pdir/'stage2.bin').write_bytes(payload)
    combined = bytearray(saved)
    combined[:len(boot)] = boot
    combined[FLASH_OFFSET:FLASH_OFFSET+len(payload)] = payload
    assert combined[len(boot):FLASH_OFFSET] == saved[len(boot):FLASH_OFFSET]
    assert combined[FLASH_OFFSET+len(payload):] == saved[FLASH_OFFSET+len(payload):]
    (pdir/'capture_sector_0.bin').write_bytes(combined)
    pmanifest = copy.deepcopy(pm)
    pmanifest.update(ADDRESS_FIELDS)
    pmanifest.update(hardware_status='untested',stage1=inspect_image(boot), stage1_raw_bytes=len(raw),
                     stage1_raw_sha256=sha(raw),stage2_load_address=hex(VECTOR), stage2_bytes=len(payload),
                     stage2_crc32=f'0x{crc:08x}', stage2_sha256=sha(payload),
                     stage2_build_manifest=str(rdir/'manifest.json'),
                     stage2_manifest_sha256=sha((rdir/'manifest.json').read_bytes()),
                     program_sha256=sha(combined),size=size,compile_flags=pflags,
                     raw10_relocated=True, frozen_prefix_manifest_sha256=sha((prefix/'manifest.json').read_bytes()))
    write_manifest(pdir,pmanifest,psources)
    print(json.dumps({'receiver':str(rdir), 'staged':str(pdir), 'receiver_bytes':len(payload),
                      'prefix_boot_bytes':len(boot), 'frame_bytes':FRAME_BYTES, 'status':'built; untested'}))


if __name__ == '__main__':
    main()
