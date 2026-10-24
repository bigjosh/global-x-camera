"""Create the compact October23 probe/phase-build archive; no hardware."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'firmware/capture-sd/evidence/2026-10-23-one-bit-baseline'
SHARED=ROOT/'firmware/capture-sd/evidence/2026-10-20-low-power'
BENCH=ROOT/'tmp/bringup/sd-baseline-20261023'
PHASE=ROOT/'tmp/bringup/sd-phase-20261023'
VENDOR=ROOT/'tmp/bringup/x-cube-n6-camera-capture'
PLAN=json.loads((SHARED/'archive-plan.json').read_text(encoding='utf-8'))
index=[]; omitted=[]
def digest(raw): return hashlib.sha256(raw).hexdigest()
def copy(src,relative,kind='exact copy'):
    dst=OUT/relative;dst.parent.mkdir(parents=True,exist_ok=True)
    raw=src.read_bytes()
    if dst.exists():raise ValueError(f'Refusing overwrite: {dst}')
    dst.write_bytes(raw)
    index.append(dict(original_path=src.relative_to(ROOT).as_posix(),archived_path=relative,
                      bytes=len(raw),sha256=digest(raw),kind=kind))
def write(relative,value):
    dst=OUT/relative;dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():raise ValueError(f'Refusing overwrite: {dst}')
    dst.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def omit(src):
    raw=src.read_bytes();omitted.append(dict(path=src.relative_to(ROOT).as_posix(),
        bytes=len(raw),sha256=digest(raw),reason='Raw waveform/large interval listing retained locally; compact summary archived'))
assert not (OUT/'build').exists() and not (OUT/'probes').exists()
for name in ('probe-static-01','pd12-toggle-01','pd12-toggle-02','smoke-recovery-01','smoke-park-01','smoke-park-02'):
    for src in sorted((BENCH/name).iterdir()):
        if not src.is_file():continue
        if src.suffix in ('.sal',) or src.stat().st_size>131072:
            omit(src)
        else: copy(src,'probes/'+name+'/'+src.name)
copy(BENCH/'smoke_pd12.py','probes/support/smoke_pd12.py')
copy(BENCH/'smoke-power/response.json','probes/smoke-power/stopped-response.json')
summary=json.loads((BENCH/'smoke-recovery-01/signal-summary.json').read_text())
compact=dict(analog=summary['analog'],source_limitations=summary['limitations'],channels={})
for name,intervals in summary['digital_intervals'].items():
    item=dict(interval_count=len(intervals),transition_count=max(0,len(intervals)-1))
    if len(intervals)<=32:item['intervals']=intervals
    for level in (0,1):
        widths=[x['end_s']-x['start_s'] for x in intervals[1:-1] if x['level']==level]
        item['interior_'+('high' if level else 'low')]=dict(count=len(widths),
            min_s=min(widths) if widths else None,max_s=max(widths) if widths else None)
    compact['channels'][name]=item
compact['scope']='Derived compact summary; boundary intervals excluded from width extrema. Firmware recovery proof is separate.'
write('probes/smoke-recovery-01/compact-summary.json',compact)
write('probes/omitted-waveforms.json',omitted)
write('probes/status.json',dict(status='work in progress',installed_firmware='unchanged v59',
    sector_sha256='7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63',
    phase_probe='CH1=PD12/CN15.21',power_probe='CH4=target 5V',
    first_pd12_test_passed=False,second_pd12_test_passed=True,
    gpio_restored=True,fresh_v59_recovery_park_passed=True,
    no_nor_or_sd_write_in_probe_tests=True,
    qualification_limit='Slow reversible GPIO wiring test only; encoded sub-microsecond pulses and camera/storage instrumentation not yet qualified.'))

recipes={}; identities={}
for variant in ('v60c-awake','v61b-standby'):
    original=PHASE/variant
    bm=json.loads((original/'phase-build.json').read_text())
    identities[variant]=bm
    copy(original/'phase-build.json',f'build/{variant}/phase-build.json')
    groups=['module','receiver','staged']+(['late'] if variant=='v61b-standby' else [])
    for group in groups:
        old=original/group
        m=json.loads((old/'manifest.json').read_text())
        relative=f'build/{variant}/{group}'
        names=[]
        for source,want in m['sources'].items():
            src=(ROOT/source).resolve();assert digest(src.read_bytes())==want
            name=src.relative_to(old.resolve()).as_posix()
            copy(src,relative+'/'+name);names.append(name)
        copy(old/'manifest.json',relative+'/manifest.json')
        copy(old/'symbols.txt',relative+'/symbols.txt')
        binary={'module':'save.bin','receiver':'capture.bin','staged':'stage1.bin','late':'late.bin'}[group]
        copy(old/binary,relative+'/'+binary)
        if group=='staged':
            for name in ('stage1_boot.bin','capture_sector_0.bin'):
                copy(old/name,relative+'/'+name)
        flags=[]
        for flag in m['compile_flags']:
            if flag.startswith('-I'):
                include=Path(flag[2:]).resolve()
                if include.is_relative_to(VENDOR):
                    flag='-I${SHARED}/dependencies/st/'+include.relative_to(VENDOR).as_posix()
                elif include.is_relative_to(old.resolve()):
                    suffix=include.relative_to(old.resolve()).as_posix()
                    flag='-I${ARCHIVE}/'+relative+('/'+suffix if suffix!='.' else '')
                else:
                    # Old prefix include search path is shadowed by the first,
                    # exact copied source directory. Preserve that resolution.
                    assert group=='staged' and 'capture-recovery-pe1-v34c' in str(include)
                    flag='-I${ARCHIVE}/'+relative
            flags.append(flag)
        units=[relative+'/'+n for n in names if Path(n).suffix in ('.c','.s','.S') and not(group=='module' and 'vendor' in Path(n).parts)]
        linker={'module':'save.ld','receiver':'capture.ld','staged':'stage1.ld','late':'late.ld'}[group]
        libc=group in ('module','receiver')
        recipes[variant+'/'+group]=dict(sources=units,compile_flags=flags,linker=relative+'/'+linker,
            runtime_flags=['-nostartfiles','--specs=nano.specs','--specs=nosys.specs'] if libc else ['-nostdlib'],
            link_flags=['-Wl,--gc-sections,--build-id=none,--no-warn-rwx-segments'],
            libraries=['-lc','-lm','-lnosys'] if libc else [],
            binary=relative+'/'+binary,binary_sha256=digest((old/binary).read_bytes()),
            input_source_order='Original frozen manifest order plus the marker source')

for src in (ROOT/'firmware/capture-sd/phase_markers').iterdir():
    if src.is_file() and src.suffix in ('.py','.c','.h','.md'):
        copy(src,'support/phase_markers/'+src.name)
for rel in ('firmware/capture-sd/build.py','firmware/capture-timing/build_raw10.py',
            'firmware/boot-timing/add_boot_header.py',
            'firmware/capture-timing/recovery_gpio/check_park.py',
            'firmware/capture-sd/fs/LICENSE.txt',
            'firmware/png-encoder/vendor/miniz/LICENSE','firmware/png-encoder/vendor/miniz/UPSTREAM.md',
            'firmware/png-encoder/vendor/miniz/LOCAL_PATCHES.md'):
    src=ROOT/rel
    if src.exists():copy(src,'support/'+rel)
copy(Path(__file__).resolve(),'support/archive_phase.py')
shared_index=[]
for entry in PLAN['source_index']:
    if entry['archived_path'].startswith('dependencies/'):
        p=SHARED/entry['archived_path'];raw=p.read_bytes()
        assert digest(raw)==entry['archived_sha256']
        shared_index.append(dict(path=entry['archived_path'],bytes=len(raw),sha256=digest(raw)))
write('archive-build.json',dict(schema=1,status='work in progress; reviewed software candidates, pending hardware qualification',
    privacy=dict(images=False,raw_power_stream=False,large_instrument_waveforms=False),
    source_index=index,recipes=recipes,build_identities=identities,
    shared_dependencies=dict(relative_archive='../2026-10-20-low-power',
        original_plan_sha256=digest((SHARED/'archive-plan.json').read_bytes()),files=shared_index),
    toolchain=PLAN['toolchain'],probes='probes/status.json'))
print(json.dumps(dict(out=str(OUT),copied_files=len(index),source_bytes=sum(x['bytes'] for x in index),
    omitted_waveforms=len(omitted),shared_dependency_files=len(shared_index),hardware_accessed=False),indent=2))
