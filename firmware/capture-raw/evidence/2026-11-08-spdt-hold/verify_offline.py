"""Offline-only rebuild and frozen-package audit; never opens an instrument."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'firmware/capture-raw'))
import inspect_flash


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


archive = ROOT/'firmware/capture-raw/evidence/2026-11-07-gpio-hold'
paths = ('capture.bin', 'staged/stage1.bin', 'staged/capture_sector_0.bin')
results = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(),
               scope='Offline metadata and build verification only; no hardware access, NOR write, or recovery allowlist change',
               current_contract_schema=2, hardware_qualified=False,
               package_audits={}, binary_comparisons={}, frozen_archive={})
for name in ('hold-standby', 'hold-awake'):
    for prefix, folder in (('current', HERE/name), ('historical', archive/name)):
        manifest = json.loads((folder/'manifest.json').read_text())
        staged = json.loads((folder/'staged/manifest.json').read_text())
        results['package_audits'][prefix+'/'+name] = dict(
            contract=manifest['gpio_hold_contract'],
            audit=inspect_flash.gpio_hold_artifacts(folder, manifest, staged))
    result = {}
    for relative in paths:
        new, old = HERE/name/relative, archive/name/relative
        assert new.read_bytes() == old.read_bytes(), (name, relative)
        result[relative] = dict(sha256=sha(new), bytes=new.stat().st_size,
                               byte_identical_to_november7=True)
    results['binary_comparisons'][name] = result

default = HERE/'default-standby'
old_default = ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/flash-standby-v1'
default_manifest = json.loads((default/'manifest.json').read_text())
assert 'gpio_hold' not in default_manifest and 'gpio_hold_contract' not in default_manifest
result = {}
for relative in paths:
    new, old = default/relative, old_default/relative
    assert new.read_bytes() == old.read_bytes(), ('default-standby', relative)
    result[relative] = dict(sha256=sha(new), bytes=new.stat().st_size,
                           byte_identical_to_october28=True)
results['binary_comparisons']['default-standby'] = result

checked = 0
for line in (archive/'SHA256SUMS').read_text().splitlines():
    digest, relative = line.split('  ', 1)
    assert sha(archive/relative) == digest, relative
    checked += 1
results['frozen_archive'] = dict(path=str(archive.relative_to(ROOT)),
                                sha256_manifest=sha(archive/'SHA256SUMS'),
                                files_verified=checked, all_unchanged=True)
log = (HERE/'regression.log').read_text(encoding='utf-8-sig')
assert 'Ran 320 tests' in log and log.rstrip().endswith('OK')
results['tests'] = dict(tests=320, passed=320, skipped=0,
                       real_linked_candidate='hold-standby',
                       log_sha256=sha(HERE/'regression.log'))
results['timing_estimate'] = dict(
    method='Historical first-GPIO cold timing plus observed ROM image-size slope; no new PD7 timing measurement',
    first_gpio_source='firmware/boot-timing/optimization-results-2026-10-17.md',
    first_gpio_reference='Target 5 V first crosses 0.5 V',
    baseline_boot_bytes=1472, hold_boot_bytes=7840, slope_ms_per_KiB=0.262,
    baseline_min_ms=22.563, baseline_max_ms=23.228,
    estimated_min_ms=22.563+(7840-1472)/1024*0.262,
    estimated_max_ms=23.228+(7840-1472)/1024*0.262,
    planning_budget_ms=30,
    later_event_crosscheck_source='docs/power/evidence/2026-11-06-series-resistor-tested/README.md',
    later_exposure_from_current_onset_ms=[24.584,25.122,25.268],
    limits=['Different supply routes, ramp thresholds and board population',
            'No installed SPDT latch; no current PD7 assertion measurement',
            'Planning budget is not worst-case or rail-sequencing qualification'])
(HERE/'results.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(result='PASS', builds=list(results['binary_comparisons']),
                      package_audits=list(results['package_audits']),
                      frozen_files_verified=checked, tests=320), indent=2))
