"""Offline tests only; retain their command, source identities and output."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
paths=sorted((ROOT/'firmware/capture-raw').glob('test_*.py'))+[ROOT/'firmware/capture-raw/bench.py']
hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
command=[sys.executable,'-m','unittest','discover','-s','firmware/capture-raw','-p','test_*.py']
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
r=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
ended=datetime.datetime.now(datetime.timezone.utc).isoformat()
out=HERE/'host-offline-tests.log'
if out.exists():raise FileExistsError(out)
out.write_bytes(r.stdout)
report=dict(scope='Offline capture test suite; no instrument or disk-device access',invocation=command,
    cwd=str(ROOT),started_at=started,ended_at=ended,returncode=r.returncode,
    log=out.name,log_sha256=hashlib.sha256(r.stdout).hexdigest(),source_hashes=hashes,
    sources_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in hashes.items()))
report['passed']=r.returncode==0 and report['sources_unchanged']
(HERE/'host-offline-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(r.stdout.decode('utf-8',errors='replace'))
print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'},indent=2))
raise SystemExit(0 if report['passed'] else 1)
