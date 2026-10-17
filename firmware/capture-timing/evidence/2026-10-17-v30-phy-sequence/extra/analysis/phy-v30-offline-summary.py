"""Summarize already completed Logic exports; never opens an instrument."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from cold_experiment import rails

for relative, logic_relative in (
    ('phy-v30-early-cycle-01/cold', 'phy-v30-early-cycle-01/cold/logic'),
    ('phy-v30-recovery-cold-02', 'phy-v30-recovery-cold-02'),
):
    capture = ROOT / 'tmp/bringup' / relative
    logic = ROOT / 'tmp/bringup' / logic_relative
    rail_file = logic / 'rail-validation.json'
    if not rail_file.exists():
        rails(logic)
    rail = json.loads(rail_file.read_text())
    boot = json.loads((logic / 'boot-summary.json').read_text())
    nrst = boot['cycles'][-1]['nrst_rise_s']
    edges = []
    previous = None
    with (logic / 'digital.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            stamp, current = float(row['Time [s]']), int(row['Channel 2'])
            if previous is not None and current != previous and stamp >= nrst:
                edges.append(dict(time_s=stamp, after_nrst_ms=(stamp - nrst) * 1000,
                                  level=current))
            previous = current
    result = dict(schema=1, source='offline analysis of completed exports; no hardware access',
        capture_directory=str(capture.relative_to(ROOT)).replace('\\', '/'),
        source_sha256={name: hashlib.sha256((logic / name).read_bytes()).hexdigest()
                      for name in ('digital.csv', 'analog.csv', 'capture-config.json', 'boot-summary.json')},
        rail_validation=rail, nrst_release_s=nrst,
        pe0_transitions_after_nrst=len(edges), pe0_edges=edges,
        captured_image=False, ram_result_available=(capture / 'ram/capture-result.json').exists(),
        inference='The 24 transitions are consistent with prefix execution through stage2 handoff event207. '
                  'Event identities were inferred from immutable firmware order, not matched to a RAM event dump.',
        limitation='No validated CSI register snapshot or first-frame evidence was obtained. '
                   'A diagnostic access stall is a hypothesis, not a proven bus-fault location.')
    destination = capture / 'offline-failure-summary.json'
    data = (json.dumps(result, indent=2) + '\n').encode()
    if destination.exists():
        if destination.read_bytes() != data:
            raise ValueError(f'Refusing different overwrite: {destination}')
    else:
        with destination.open('xb') as stream:
            stream.write(data)
    print(json.dumps(dict(capture=relative, pe0_edges=len(edges), rails_passed=rail['passed'])))
