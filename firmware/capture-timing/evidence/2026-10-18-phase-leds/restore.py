"""Restore frozen v44 files into a new directory, optionally recompile offline.

This has no bench access. It never writes to the original workspace or programs
flash. The optional rebuild requires the matching external GNU Arm toolchain.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
BUILD_REL = Path('tmp/bringup/capture-status-leds-v44-default-20261018')
ORIGINAL_ROOT = 'D:\\Github\\global-x-camera'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified(path, digest, size=None):
    data = path.read_bytes()
    if sha(data) != digest or size is not None and len(data) != size:
        raise ValueError(f'Archived bytes changed: {path}')
    return data


def safe_child(root, name):
    path = (root/name.replace('\\', '/')).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Unsafe restore path: {name}')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True, help='Must not already exist')
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--toolchain-bin', type=Path)
    args = parser.parse_args()
    root = args.destination.resolve()
    if root.exists():
        raise ValueError('Destination exists; refusing any overwrite')
    index = json.loads((HERE/'archive-index.json').read_text())
    for entry in index['files']:
        archive_file = (HERE/entry['archive']).resolve()
        if not archive_file.is_relative_to(HERE.parent.resolve()):
            raise ValueError('Archive index escapes evidence root')
        verified(archive_file, entry['sha256'], entry['bytes'])
    rows = json.loads((HERE/'source-provenance.json').read_text())
    root.mkdir(parents=True)
    for row in rows:
        content = verified(HERE/row['archive'], row['sha256'], row['bytes'])
        target = safe_child(root, row['source'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    headers = json.loads((HERE/'headers-index.json').read_text())['files']
    with zipfile.ZipFile(HERE/'headers.zip') as archive:
        for item in headers:
            content = archive.read(item['source'])
            if sha(content) != item['sha256'] or len(content) != item['bytes']:
                raise ValueError('Header member differs from recorded bytes')
            target = safe_child(root, item['source'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    for stage in ('receiver', 'staged'):
        target = root/BUILD_REL/stage
        target.mkdir(parents=True, exist_ok=True)
        for source in (HERE/'build'/stage).iterdir():
            shutil.copyfile(source, target/source.name)
    for entry in json.loads((HERE/'license-index.json').read_text())['files']:
        target = safe_child(root, entry['source'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(verified(HERE/entry['archive'], entry['sha256'], entry['bytes']))

    result = dict(restored=True, destination=str(root), source_rows=len(rows), headers=len(headers),
                  hardware_operations=0, rebuilt=False)
    if args.rebuild:
        toolchain = json.loads((HERE/'toolchain.json').read_text())
        tc = args.toolchain_bin or Path(toolchain['bin_directory'])
        for name, digest in toolchain['executables'].items():
            verified(tc/name, digest)
        rebuilt = {}
        for stage, stem, libc in [('receiver', 'capture', True), ('staged', 'stage1', False)]:
            folder = root/BUILD_REL/stage
            manifest = json.loads((folder/'manifest.json').read_text())
            flags = [f.replace(ORIGINAL_ROOT, str(root)) for f in manifest['compile_flags']]
            objects = []
            for i, name in enumerate(manifest['sources']):
                source = safe_child(root, name)
                if source.suffix not in ('.c', '.s', '.S'):
                    continue
                obj = folder/f'rebuild-{i:02d}-{source.stem}.o'
                subprocess.run([str(tc/'arm-none-eabi-gcc.exe'), *flags, '-c', str(source), '-o', str(obj)], check=True)
                objects.append(obj)
            elf = folder/(stem+'-rebuilt.elf')
            runtime = ['-nostartfiles', '--specs=nano.specs', '--specs=nosys.specs'] if libc else ['-nostdlib']
            libraries = ['-lc', '-lm', '-lnosys'] if libc else []
            subprocess.run([str(tc/'arm-none-eabi-gcc.exe'), *flags, *runtime,
                '-T', str(folder/(stem+'.ld')), *map(str, objects),
                '-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments', *libraries, '-o', str(elf)], check=True)
            binary = folder/(stem+'-rebuilt.bin')
            subprocess.run([str(tc/'arm-none-eabi-objcopy.exe'), '-O', 'binary', str(elf), str(binary)], check=True)
            expected = manifest['raw_sha256' if libc else 'stage1_raw_sha256']
            rebuilt[stage] = verified(binary, expected)
        spec = importlib.util.spec_from_file_location('restored_boot_header', root/'firmware/boot-timing/add_boot_header.py')
        header = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(header)
        boot = header.make_image(rebuilt['staged'])
        original_boot = (root/BUILD_REL/'staged/stage1_boot.bin').read_bytes()
        if boot != original_boot:
            raise ValueError('Rebuilt boot header differs')
        sector = bytearray((root/BUILD_REL/'staged/capture_sector_0.bin').read_bytes())
        sector[:len(boot)] = boot
        sector[0x2000:0x2000+len(rebuilt['receiver'])] = rebuilt['receiver']
        manifest = json.loads((root/BUILD_REL/'staged/manifest.json').read_text())
        if sha(sector) != manifest['program_sha256']:
            raise ValueError('Rebuilt sector differs')
        result.update(rebuilt=True, byte_identical=True, sector_sha256=sha(sector),
                      receiver_sha256=sha(rebuilt['receiver']), prefix_sha256=sha(rebuilt['staged']))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
