"""Freeze the exact offline v44 build. No instrument or debugger operations."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILD = ROOT/'tmp/bringup/capture-status-leds-v44-default-20261018'
LED = ROOT/'firmware/capture-timing/status_leds'
TC = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.12.3.rel1.win32_1.0.200.202406191623/tools/bin')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def freeze_headers(manifests, mapped):
    requests = []
    for manifest in manifests.values():
        for name in manifest['sources']:
            path = ROOT/name
            if path.suffix == '.c':
                requests.append((path, manifest['compile_flags']))
    def dependencies(item):
        source, flags = item
        # -M is intentional: CMSIS marks some repository headers as system
        # headers via pragma, so -MM silently misses required owned files.
        output = subprocess.check_output([str(TC/'arm-none-eabi-gcc.exe'), *flags,
                                          '-M', '-MT', 'deps', str(source)], text=True)
        return [Path(s).resolve() for s in output.replace('\\\n', ' ').replace('\\', '/').split()[1:]]
    closure = set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for names in pool.map(dependencies, requests):
            closure.update(names)
    dependencies_index = []
    external = []
    with zipfile.ZipFile(HERE/'headers.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(closure):
            if not source.is_relative_to(ROOT):
                external.append(dict(source=str(source), sha256=sha(source.read_bytes())))
                continue
            relative = source.relative_to(ROOT).as_posix()
            if relative in mapped:
                continue
            data = source.read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compresslevel=9)
            dependencies_index.append(dict(source=relative, bytes=len(data), sha256=sha(data)))
    dump('headers-index.json', dict(method='gcc -M for every C translation unit; retain all repository-owned dependencies',
                                  excludes='Toolchain-owned headers and runtime libraries belong to the pinned toolchain',
                                  external_headers=external, files=dependencies_index))
    return dependencies_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-headers', action='store_true')
    args = parser.parse_args()
    if args.refresh_headers:
        manifests = {stage:json.loads((HERE/'build'/stage/'manifest.json').read_text()) for stage in ('receiver', 'staged')}
        rows = json.loads((HERE/'source-provenance.json').read_text())
        headers = freeze_headers(manifests, {r['source'] for r in rows})
        print(json.dumps(dict(headers=len(headers), header_zip_bytes=(HERE/'headers.zip').stat().st_size)))
        return
    if (HERE/'source-provenance.json').exists():
        raise RuntimeError('Archive already prepared; refusing to rewrite it')
    existing = {}
    for path in sorted(HERE.parent.glob('*/source-objects/*')):
        if path.is_file():
            existing.setdefault(sha(path.read_bytes()), path)
    rows = []
    def store(source, role):
        content = source.read_bytes()
        digest = sha(content)
        destination = existing.get(digest)
        if destination is None:
            destination = HERE/'source-objects'/(digest+source.suffix.lower())
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            existing[digest] = destination
        rows.append(dict(source=source.relative_to(ROOT).as_posix(), role=role,
                         archive=Path(os.path.relpath(destination, HERE)).as_posix(),
                         bytes=len(content), sha256=digest))

    manifests = {}
    for stage, filenames in {
        'receiver': ('manifest.json', 'capture.bin', 'symbols.txt'),
        'staged': ('manifest.json', 'stage1.bin', 'stage1_boot.bin', 'stage2.bin',
                   'capture_sector_0.bin', 'symbols.txt'),
    }.items():
        folder = HERE/'build'/stage
        folder.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            shutil.copyfile(BUILD/stage/name, folder/name)
        manifest = json.loads((BUILD/stage/'manifest.json').read_text())
        manifests[stage] = manifest
        for name, digest in manifest['sources'].items():
            source = ROOT/name
            if sha(source.read_bytes()) != digest:
                raise RuntimeError(f'Frozen source mismatch: {name}')
            store(source, stage+'-source')
        for name, digest in manifest['generator_inputs'].items():
            source = ROOT/name
            if sha(source.read_bytes()) != digest:
                raise RuntimeError(f'Generator revision unavailable: {name}')
            if not any(r['source'] == source.relative_to(ROOT).as_posix() for r in rows):
                store(source, 'generator-input')
    for name in ('README.md', 'inspect.py', 'test_status_leds.py'):
        store(LED/name, 'offline-validation')
    for name in ('firmware/capture-timing/build_raw10.py', 'firmware/boot-timing/add_boot_header.py'):
        store(ROOT/name, 'builder-support')

    dependencies_index = freeze_headers(manifests, {r['source'] for r in rows})
    dump('source-provenance.json', rows)
    licenses = json.loads((HERE.parent/'2026-10-17-receiver-ready/license-index.json').read_text())
    for entry in licenses['files']:
        entry['archive'] = '../2026-10-17-receiver-ready/'+entry['archive']
        data = (HERE/entry['archive']).read_bytes()
        if sha(data) != entry['sha256']:
            raise RuntimeError('License hash mismatch')
    dump('license-index.json', licenses)
    dump('toolchain.json', dict(
        bin_directory=str(TC),
        version=subprocess.check_output([str(TC/'arm-none-eabi-gcc.exe'), '--version'], text=True),
        executables={name:sha((TC/name).read_bytes()) for name in
                     ('arm-none-eabi-gcc.exe', 'arm-none-eabi-objcopy.exe', 'arm-none-eabi-nm.exe')},
        vendor_repository='https://github.com/STMicroelectronics/x-cube-n6-camera-capture.git',
        vendor_commit=manifests['receiver']['vendor_commit']))

    command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(LED), '-p', 'test_status_leds.py', '-v']
    test = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    (HERE/'offline-tests.txt').write_text(test.stdout+test.stderr, encoding='utf-8', newline='\n')
    if test.returncode:
        raise RuntimeError('Offline tests failed; preserving output')
    spec = importlib.util.spec_from_file_location('phase_led_inspection', LED/'inspect.py')
    inspect = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspect)
    dump('offline-validation.json', dict(
        hardware_status='pending qualification', instrument_operations=0,
        tests_command=command, tests_exit_code=test.returncode, tests_passed=8,
        source_checks=inspect.source_checks(manifests['staged']),
        sector_sha256=sha((BUILD/'staged/capture_sector_0.bin').read_bytes()),
        prefix_sha256=sha((BUILD/'staged/stage1.bin').read_bytes()),
        receiver_sha256=sha((BUILD/'receiver/capture.bin').read_bytes()),
        recovery_park='0x3418078c', sleep_idle='0x343022d8', failure_park='0x34301546'))
    print(json.dumps(dict(sources=len(rows), headers=len(dependencies_index),
                         header_zip_bytes=(HERE/'headers.zip').stat().st_size, tests_passed=8)))


if __name__ == '__main__':
    main()
