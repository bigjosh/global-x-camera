import json,time,pathlib
base=pathlib.Path(__file__).resolve().parent
def log(obj):
    obj['host_monotonic_ns']=time.monotonic_ns()
    with (base/'cycles.jsonl').open('a') as f:f.write(json.dumps(obj)+'\n')
    print(json.dumps(obj),flush=True)
def command(state):
    ident=f'{state}-{time.monotonic_ns()}'
    (base/'control.json').write_text(json.dumps(dict(id=ident,state=state)))
    for _ in range(80):
        time.sleep(.1)
        try:r=json.loads((base/'response.json').read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):continue
        if r.get('id')==ident:
            if not r.get('ok'):raise RuntimeError(r)
            return r
    raise RuntimeError('mailbox timeout')
def latest():
    for line in reversed((base/'session.jsonl').read_text().splitlines()):
        try:r=json.loads(line)
        except ValueError:continue
        if r.get('event')=='statistics':return r['statistics']
    raise RuntimeError('No statistics')
def fresh(s):
    return (time.monotonic_ns()-s['received']['monotonic_ns'])<2000000000
s=latest()
assert fresh(s) and s['voltage']['avg']>4.5 and .006<s['current']['avg']<.012,s
log(dict(event='starting_idle',statistics=s))
for cycle in range(1,6):
    log(dict(event='off',cycle=cycle,response=command('off')))
    time.sleep(15)
    s=latest()
    assert fresh(s) and abs(s['current']['avg'])<.0001,s
    log(dict(event='on',cycle=cycle,response=command('auto')))
    began=time.monotonic();active=False;idle_seq=[];last_seq=-1
    while time.monotonic()-began<15:
        time.sleep(.2);s=latest()
        if not fresh(s):raise RuntimeError('Statistics stale; leave power on')
        if s['sequence']==last_seq:continue
        last_seq=s['sequence'];a=s['current']['avg']
        if a>.03:active=True
        if active and time.monotonic()-began>3 and .006<a<.012:
            idle_seq.append(s)
        else:idle_seq=[]
        if len(idle_seq)>=6:break
    if len(idle_seq)<6:raise RuntimeError('No expected terminal plateau; leave power on')
    log(dict(event='plateau',cycle=cycle,statistics=idle_seq))
log(dict(event='completed',cycles=5,target='left powered at plateau'))
