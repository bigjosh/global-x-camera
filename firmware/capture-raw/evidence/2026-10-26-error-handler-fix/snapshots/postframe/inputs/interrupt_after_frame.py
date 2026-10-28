"""Verify full frame then request UART recovery during code4; root bench only."""
import sys,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
base=Path(__file__).resolve().parent
build=base/'flash-postframe-v3'
signal=base/'postframe-interrupt-current.power-on.json'
def run(label,*args):
    with (base/(label+'.log')).open('x') as f:
        subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True)
run('interrupt-live-proof',base/'read_postframe.py',build,signal,base/'interrupt-live-proof')
assert json.loads((base/'interrupt-live-proof/verified.json').read_text())['passed']
launch=json.loads(signal.read_text())
elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(launch['utc'])).total_seconds()
assert 1<elapsed<10,elapsed
(base/'interrupt-request.json').write_text(json.dumps(dict(requested_utc=datetime.now(timezone.utc).isoformat(),
    seconds_after_power_on=elapsed,nominal_blink_duration_s=16.4,post_frame_verified=True,
    sd_transaction=False),indent=2))
run('interrupt-recovery','tmp/bringup/sd125-negedge-20261026/uart_recover.py',base/'interrupt-recovery')
run('interrupt-park','firmware/capture-timing/recovery_gpio/check_park.py','--build',build/'staged','--out',base/'interrupt-park')
print('Post-frame UART recovery during code4 passed exact park',flush=True)
