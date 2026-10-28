from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess,sys,time
root=Path(__file__).resolve().parents[3];out=Path(__file__).resolve().parent
suffixes={'.py','.c','.h','.inc','.s','.ld','.cpp'}
paths=[p for p in (root/'firmware').rglob('*') if p.is_file() and p.suffix.lower() in suffixes
       and 'evidence' not in p.relative_to(root).parts and '__pycache__' not in p.parts]
base=root/'firmware/capture-sd/evidence/2026-10-24-normal-profile/build/v66c-normal-standby'
paths += [base/'receiver/capture.c',base/'staged/stage1_sensor.c']
def hashes():return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
before=hashes();started=datetime.now(timezone.utc).isoformat();timer=time.monotonic()
command=[sys.executable,'-m','unittest','discover','-s','firmware/capture-raw','-p','test_*.py']
result=subprocess.run(command,cwd=root,capture_output=True,text=True)
log=result.stdout+result.stderr;(out/'offline-tests.log').write_text(log)
after=hashes();changed=[p for p in before if before[p]!=after[p]]
match=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
report=dict(scope='Offline capture regression suite; no hardware access',invocation=command,cwd=str(root),
 started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-timer,
 returncode=result.returncode,tests=int(match[1]) if match else None,
 test_duration_seconds=float(match[2]) if match else None,log='offline-tests.log',
 log_sha256=hashlib.sha256((out/'offline-tests.log').read_bytes()).hexdigest(),
 source_hashes=before,source_hashes_after=after,changed_sources=changed,
 passed=result.returncode==0 and not changed)
(out/'offline-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if not k.startswith('source_hashes')},indent=2))
if not report['passed']:raise SystemExit(1)
