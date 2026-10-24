"""Freeze the v64/v65 sources and portable recipes. Offline only."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'firmware/capture-sd/evidence/2026-10-24-normal-profile'
SHARED = OUT.parent / '2026-10-20-low-power'
PRIOR = OUT.parent / '2026-10-23-one-bit-baseline'
WORK = ROOT / 'tmp/bringup/sd-normal-20261024'
VENDOR = ROOT / 'tmp/bringup/x-cube-n6-camera-capture'
PLAN = json.loads((SHARED / 'archive-plan.json').read_text(encoding='utf-8'))
index = []

def sha(raw): return hashlib.sha256(raw).hexdigest()
def copy(src, relative):
    raw = src.read_bytes()
    dst = OUT / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.read_bytes() != raw: raise ValueError('Refusing changed copy: ' + str(dst))
    else: dst.write_bytes(raw)
    index.append(dict(original_path=src.relative_to(ROOT).as_posix(),
                      archived_path=relative, bytes=len(raw), sha256=sha(raw), kind='exact copy'))
def write(relative, value):
    dst = OUT / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists(): raise ValueError('Refusing overwrite: ' + str(dst))
    dst.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

assert not (OUT / 'archive-build.json').exists()
recipes = {}; identities = {}
for variant in ('v64-normal-awake', 'v65-normal-standby'):
    original = WORK / variant
    identities[variant] = json.loads((original / 'phase-build.json').read_text(encoding='utf-8'))
    copy(original / 'phase-build.json', f'build/{variant}/phase-build.json')
    groups = ['module', 'receiver', 'staged'] + (['late'] if 'standby' in variant else [])
    for group in groups:
        old = original / group
        m = json.loads((old / 'manifest.json').read_text(encoding='utf-8'))
        relative = f'build/{variant}/{group}'
        names = []
        for source, want in m['sources'].items():
            src = (ROOT / source).resolve()
            assert sha(src.read_bytes()) == want
            name = src.relative_to(old.resolve()).as_posix()
            copy(src, relative + '/' + name); names.append(name)
        copy(old / 'manifest.json', relative + '/manifest.json')
        copy(old / 'symbols.txt', relative + '/symbols.txt')
        binary = dict(module='save.bin', receiver='capture.bin', staged='stage1.bin', late='late.bin')[group]
        copy(old / binary, relative + '/' + binary)
        if group == 'staged':
            for name in ('stage1_boot.bin', 'capture_sector_0.bin'):
                copy(old / name, relative + '/' + name)
        flags = []
        for flag in m['compile_flags']:
            if flag.startswith('-I'):
                include = Path(flag[2:]).resolve()
                if include.is_relative_to(VENDOR):
                    flag = '-I${SHARED}/dependencies/st/' + include.relative_to(VENDOR).as_posix()
                elif include.is_relative_to(old.resolve()):
                    suffix = include.relative_to(old.resolve()).as_posix()
                    flag = '-I${ARCHIVE}/' + relative + ('/' + suffix if suffix != '.' else '')
                else:
                    assert group == 'staged' and 'capture-recovery-pe1-v34c' in str(include)
                    flag = '-I${ARCHIVE}/' + relative
            flags.append(flag)
        units = [relative + '/' + n for n in names if Path(n).suffix in ('.c', '.s', '.S')
                 and not (group == 'module' and 'vendor' in Path(n).parts)]
        linker = dict(module='save.ld', receiver='capture.ld', staged='stage1.ld', late='late.ld')[group]
        libc = group in ('module', 'receiver')
        recipes[variant + '/' + group] = dict(sources=units, compile_flags=flags,
            linker=relative + '/' + linker,
            runtime_flags=['-nostartfiles', '--specs=nano.specs', '--specs=nosys.specs'] if libc else ['-nostdlib'],
            link_flags=['-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments'],
            libraries=['-lc', '-lm', '-lnosys'] if libc else [],
            binary=relative + '/' + binary, binary_sha256=sha((old / binary).read_bytes()),
            input_source_order='Original frozen manifest order plus marker source')
    copy(ROOT / f'tmp/sd-normal-20261024/{variant}-peer-review.json',
         f'build/reviews/{variant}.json')

support = ['firmware/capture-sd/build.py', 'firmware/capture-sd/phase_markers/build.py',
    'firmware/capture-sd/build_module.py', 'firmware/capture-sd/capture_profile.h',
    'firmware/capture-sd/receiver_profile.py', 'firmware/capture-sd/test_receiver_profile.py',
    'firmware/capture-timing/build_raw10.py', 'firmware/boot-timing/add_boot_header.py',
    'firmware/capture-sd/fs/LICENSE.txt', 'firmware/png-encoder/vendor/miniz/LICENSE',
    'firmware/png-encoder/vendor/miniz/UPSTREAM.json', 'firmware/png-encoder/vendor/miniz/LOCAL_PATCHES.json',
    'firmware/png-encoder/vendor/miniz/fast-loop-byte-safe.patch']
for rel in support: copy(ROOT / rel, 'support/' + rel)
copy(Path(__file__), 'support/archive_normal.py')
copy(PRIOR / 'rebuild.py', 'rebuild.py')
copy(PRIOR / 'verify_build.py', 'verify_build.py')
shared_index = []
for entry in PLAN['source_index']:
    if entry['archived_path'].startswith('dependencies/'):
        raw = (SHARED / entry['archived_path']).read_bytes()
        assert sha(raw) == entry['archived_sha256']
        shared_index.append(dict(path=entry['archived_path'], bytes=len(raw), sha256=sha(raw)))
write('archive-build.json', dict(schema=1,
    status='Exact reviewed normal-profile candidates; hardware qualification pending in separate addenda',
    privacy=dict(images=False, raw_power_stream=False, large_instrument_waveforms=False),
    source_index=index, recipes=recipes, build_identities=identities,
    shared_dependencies=dict(relative_archive='../2026-10-20-low-power',
        original_plan_sha256=sha((SHARED / 'archive-plan.json').read_bytes()), files=shared_index),
    toolchain=PLAN['toolchain']))
print(json.dumps(dict(files=len(index), bytes=sum(x['bytes'] for x in index),
                     payload_groups=len(recipes), hardware_accessed=False), indent=2))
