"""One bounded request to this task's already-owned JS110 session."""
import argparse, json, os, time, uuid
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--state',choices=('query','recovery','stop'),required=True)
p.add_argument('--asserted',choices=('true','false'))
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if (a.state=='recovery') != (a.asserted is not None):
    p.error('Only recovery requires --asserted')
folder=Path('tmp/bringup/phy-fast-session-01')
request={'id':str(uuid.uuid4()),'state':a.state}
if a.state=='recovery':request['asserted']=a.asserted=='true'
temporary=folder/'one-request.tmp'
temporary.write_text(json.dumps(request),encoding='utf-8')
os.replace(temporary,folder/'control.json')
deadline=time.monotonic()+8
while time.monotonic()<deadline:
    try:
        result=json.loads((folder/'response.json').read_text(encoding='utf-8-sig'))
        if result.get('id')==request['id']:
            a.out.parent.mkdir(parents=True,exist_ok=True)
            a.out.write_text(json.dumps(result,indent=2)+'\n')
            if not result.get('ok'):raise RuntimeError(result)
            if a.state=='recovery':
                r=result['recovery_output']
                assert r['interface']=='active_low_diode' and r['extio_voltage_mv']==3300
                assert r['gpo0']==int(not request['asserted']) and r['gpo1']==0
            print(json.dumps(result));break
    except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
    time.sleep(.05)
else:raise TimeoutError('No matching response; do not send competing commands')
