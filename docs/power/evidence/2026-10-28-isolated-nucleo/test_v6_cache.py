"""Offline M55 cache-validator regression using the retained failed observation."""
import copy
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('run_v6_cache_test', HERE/'run_v6.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

header = (ROOT/'tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/CMSIS/Include/core_cm55.h').read_text()
for name, expected in [('IC', 17), ('DC', 16)]:
    position = int(re.search(r'#define SCB_CCR_'+name+r'_Pos\s+(\d+)U', header)[1])
    assert position == expected
    assert getattr(runner, 'CCR_'+name) == 1 << position

session = json.loads((HERE/'cacheon01/operation/prepared.json').read_text())
proof = json.loads((HERE/'cacheon01/operation/proof.json').read_text())
runner.validate(proof, session)
results = [dict(case='retained actual I-cache-on proof accepted', passed=True)]
for label, field, value in [
    ('old swapped mask rejected', 'CCR_ACTIVE', proof['CCR'] | (1 << 16)),
    ('both caches rejected', 'CCR_ACTIVE', proof['CCR'] | (3 << 16)),
    ('missing I-cache rejected', 'CCR_ACTIVE', proof['CCR']),
    ('I-cache retained at park rejected', 'CCR_AFTER', proof['CCR'] | (1 << 17)),
    ('D-cache retained at park rejected', 'CCR_AFTER', proof['CCR'] | (1 << 16)),
    ('missing setup proof rejected', 'CACHE_SAFE', 0),
]:
    changed = copy.deepcopy(proof)
    changed[field] = value
    try:
        runner.validate(changed, session)
    except ValueError:
        results.append(dict(case=label, passed=True))
    else:
        raise AssertionError(label)
runner.checked(HERE/'probe-v6')
print(json.dumps(dict(cases=results, frozen_firmware_unchanged=True), indent=2))
