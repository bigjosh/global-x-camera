"""Load generated footprints in KiCad and verify schematic physical-pin coverage.

Run with KiCad's bundled Python (pcbnew required). This checks parsing and pad
identity only; it does not approve land geometry or manufacturing rules.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/reconstruction'
LIBRARY = ROOT / 'hardware/kicad/GX.pretty'
SOURCE = OUT / 'schematic-connectivity.json'


def natural(value):
    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', str(value))]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    connectivity = json.loads(SOURCE.read_text(encoding='utf-8'))
    expected = {ref: component for ref, component in connectivity['components'].items()
                if ref != 'CAM1' and not component.get('external_to_host_pcb', False)}
    files = sorted(LIBRARY.glob('*.kicad_mod'), key=lambda p: natural(p.name))
    results, loaded_refs = [], set()
    ignored_counts = Counter()

    for path in files:
        ref = path.stem.removesuffix('_Recovered')
        result = {'reference': ref, 'path': path.relative_to(ROOT).as_posix(),
                  'sha256': digest(path), 'load_status': 'error'}
        try:
            footprint = pcbnew.FootprintLoad(str(LIBRARY), path.stem)
            if footprint is None:
                raise ValueError('KiCad FootprintLoad returned None')
        except Exception as exc:
            result['error'] = str(exc)
            results.append(result)
            continue
        result['load_status'] = 'pass'
        loaded_refs.add(ref)
        copper, ignored = [], []
        for index, pad in enumerate(footprint.Pads()):
            layers = list(pad.GetLayerSet().Seq())
            copper_layers = [pcbnew.LayerName(layer) for layer in layers
                             if pcbnew.IsCopperLayer(layer)]
            info = {'record_index': index, 'number': pad.GetNumber(),
                    'layers': [pcbnew.LayerName(layer) for layer in layers],
                    'position_mm': [round(pcbnew.ToMM(v), 6) for v in pad.GetPosition()]}
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                info['ignored_reason'] = 'non-plated mechanical hole'
            elif not copper_layers:
                info['ignored_reason'] = 'no copper layers (mask/paste or other aperture)'
            else:
                copper.append(info)
                continue
            ignored.append(info)
            ignored_counts[info['ignored_reason']] += 1

        number_counts = Counter(p['number'] for p in copper)
        required = set(expected.get(ref, {}).get('pins', {}))
        actual = set(number_counts)
        result.update({
            'expected_component': ref in expected,
            'expected_pin_count': len(required),
            'copper_pad_record_count': len(copper),
            'unique_copper_pad_number_count': len(actual),
            'expected_pins': sorted(required, key=natural),
            'actual_copper_pad_numbers': sorted(actual, key=natural),
            'missing_physical_pins': sorted(required - actual, key=natural),
            'unexpected_copper_pad_numbers': sorted(actual - required, key=natural),
            'unexpected_copper_pad_records': [p for p in copper if p['number'] not in required],
            'duplicate_copper_pad_numbers': {n: count for n, count in number_counts.items() if count > 1},
            'ignored_pad_records': ignored,
        })
        result['pin_coverage_status'] = ('pass' if ref in expected and required == actual else 'fail')
        # Copper graphics cannot acquire schematic pin numbers. Report their
        # presence separately, without misclassifying custom-pad primitives.
        result['non_pad_copper_graphic_count'] = sum(
            pcbnew.IsCopperLayer(item.GetLayer()) for item in footprint.GraphicalItems())
        results.append(result)

    errors = [r for r in results if r['load_status'] != 'pass']
    mismatches = [r for r in results if r.get('pin_coverage_status') == 'fail']
    missing = sorted(set(expected) - loaded_refs, key=natural)
    unexpected = sorted(loaded_refs - set(expected), key=natural)
    summary = {
        'kicad_version': pcbnew.Version(),
        'expected_pcb_components': len(expected),
        'footprint_files': len(files),
        'loaded_footprints': len(results) - len(errors),
        'load_errors': len(errors),
        'components_with_pin_coverage_mismatch': len(mismatches),
        'expected_physical_pins': sum(len(v['pins']) for v in expected.values()),
        'unique_copper_pad_numbers_across_footprints': sum(r.get('unique_copper_pad_number_count', 0) for r in results),
        'copper_pad_records': sum(r.get('copper_pad_record_count', 0) for r in results),
        'missing_physical_pins': sum(len(r.get('missing_physical_pins', [])) for r in results),
        'unexpected_copper_pad_records': sum(len(r.get('unexpected_copper_pad_records', [])) for r in results),
        'ignored_pad_records': dict(ignored_counts),
        'missing_or_unloaded_component_footprints': missing,
        'unexpected_component_footprints': unexpected,
        'non_pad_copper_graphics': sum(r.get('non_pad_copper_graphic_count', 0) for r in results),
    }
    passed = not errors and not mismatches and not missing and not unexpected
    data = {'status': 'pass' if passed else 'fail', 'scope': 'KiCad parse and physical-pin coverage only',
            'schematic_connectivity_source': {'path': SOURCE.relative_to(ROOT).as_posix(), 'sha256': digest(SOURCE)},
            'summary': summary, 'footprints': results}
    (OUT / 'footprint-load-validation.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

    lines = [f"# Footprint load and pin coverage: {'PASS' if passed else 'FAIL'}", '',
             f"KiCad {summary['kicad_version']} `pcbnew.FootprintLoad` loaded {summary['loaded_footprints']} of {len(files)} generated footprints.", '',
             f"Compared copper pad numbers against `schematic-connectivity.json`: {summary['expected_physical_pins']} expected physical pins across {len(expected)} host-PCB components. CAM1 is excluded; J3 contacts 31–34 are included.", '',
             f"Missing pins: {summary['missing_physical_pins']}. Unexpected copper pad records: {summary['unexpected_copper_pad_records']}. Component mismatches: {len(mismatches)}.", '',
             'Ignored records are classified by actual KiCad attributes and layers, not by their names. NPTH mechanical holes are excluded, as are pads with no copper layers. A `~` or blank-number pad on copper is reported as an extra.', '']
    for reason, count in ignored_counts.items():
        lines.append(f'- {count} ignored: {reason}.')
    lines.extend(['', '## Exceptions', ''])
    if not errors and not mismatches and not missing and not unexpected:
        lines.append('No parsing or physical-pin coverage exceptions.')
    for r in errors:
        lines.append(f"- {r['reference']}: load error: {r['error']}")
    for r in mismatches:
        lines.append(f"- {r['reference']}: missing {r['missing_physical_pins']}; unexpected copper numbers {r['unexpected_copper_pad_numbers']}.")
    if missing:
        lines.append(f'- Missing or unloaded component footprints: {missing}.')
    if unexpected:
        lines.append(f'- Unexpected component footprints: {unexpected}.')
    duplicates = [r for r in results if r.get('duplicate_copper_pad_numbers')]
    lines.extend(['', '## Multiple pad records for one physical pin', ''])
    if not duplicates:
        lines.append('None.')
    for r in duplicates:
        lines.append(f"- {r['reference']}: {r['duplicate_copper_pad_numbers']}. These retain a single physical-pin identity and are not counted as extra pins.")
    lines.extend(['', f"Non-pad copper graphics found: {summary['non_pad_copper_graphics']}. Custom-pad primitives belong to their pad and are not counted as separate graphics.", '',
                  'This validation does not sign off land dimensions, polarity/orientation, courtyard shape, solder-mask or paste rules, board clearances, or manufacturing suitability. File hashes and per-footprint results are recorded in `footprint-load-validation.json`.', '',
                  'Re-run with KiCad’s bundled Python: `python tools/validate_footprints.py`.', ''])
    (OUT / 'footprint-load-validation.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'status': data['status'], **summary}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
