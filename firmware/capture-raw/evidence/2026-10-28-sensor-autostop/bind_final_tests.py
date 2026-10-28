"""Bind the completed final test log to frozen sources; no tests or hardware run."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
log=HERE/'design/final-tests.log';raw=log.read_bytes()
text=raw.decode('utf-8');match=re.search(r'Ran (\d+) tests in ([\d.]+)s\s+OK\s*$',text)
assert match and int(match[1])==250
end=log.stat().st_mtime;start=end-float(match[2])
paths=sorted((ROOT/'firmware/capture-raw').glob('test_*.py'))+[ROOT/'firmware/capture-raw/bench.py']
hashes={};mtimes={}
for p in paths:
    name=p.relative_to(ROOT).as_posix();stat=p.stat()
    assert stat.st_mtime<start,name
    hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    mtimes[name]=datetime.datetime.fromtimestamp(stat.st_mtime,datetime.timezone.utc).isoformat()
    assert p.stat().st_mtime_ns==stat.st_mtime_ns
target=HERE/'host-final-offline-tests.log'
if target.exists():raise FileExistsError(target)
target.write_bytes(raw)
report=dict(scope='Existing completed final offline suite; no rerun or instrument access',
    invocation=[sys.executable,'-m','unittest','discover','-s','firmware/capture-raw','-p','test_*.py'],
    cwd=str(ROOT),returncode=0,tests=250,duration_seconds=float(match[2]),
    log=target.name,log_sha256=hashlib.sha256(raw).hexdigest(),
    original_log=log.relative_to(HERE).as_posix(),source_hashes=hashes,source_mtimes=mtimes,
    source_timestamps_predate_inferred_start=True,
    inferred_start=datetime.datetime.fromtimestamp(start,datetime.timezone.utc).isoformat(),
    log_written_at=datetime.datetime.fromtimestamp(end,datetime.timezone.utc).isoformat(),
    sources_unchanged=True,passed=True,
    source_identity_basis='Post-run hashes of frozen sources; all source mtimes precede the test start '
        'inferred from reported duration and log write time. Firmware owner confirms exact invocation, '
        'exit0 and source freeze. No beginning-of-test hash snapshot was made.')
(HERE/'host-final-offline-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','source_mtimes')},indent=2))
