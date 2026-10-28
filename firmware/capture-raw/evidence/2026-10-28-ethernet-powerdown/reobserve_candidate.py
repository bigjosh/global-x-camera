"""Fresh completion observation after host-only CONTROL validator correction.
No reset, request write, card command, or replacement executable.
"""
from pathlib import Path
import importlib.util,json,struct
H=Path(__file__).resolve().parent;R=H.parents[2]
s=importlib.util.spec_from_file_location('rawbench',R/'firmware/capture-raw/bench.py')
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
build=H/'ram-candidate';old=H/'candidate-awake/capture';out=H/'candidate-reobserved'
m,code=r.checked_build(build,'ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000')
names=r.fields(build);plan=json.loads((old/'plan.json').read_text());words=plan['request_words']
saved=json.loads((old/'proof.json').read_text());r.diagnostic_layout(m,1)
out.mkdir(exist_ok=False);b=r.sd.Bench(out/'operation')
p=r.decode(b.upload(r.PROOF,384,'completed-proof.bin'),names)
assert p==saved,'Original completed operation changed'
assert b.upload(r.REQUEST,64,'completed-request.bin')==struct.pack('<16I',*words)
r.validate(p,m,words)
card=r.card_snapshot(b,m,p,'completed')
magic=r.magic_snapshot(b,m,p,'completed',card)
context=r.sd.context_proof(b,{m['park']},'completed')
assert b.upload(r.LOAD,m['immutable_bytes'],'completed-code.bin')==code[:m['immutable_bytes']]
assert struct.unpack('<I',b.upload(m['system_core_clock'],4,'system-clock.bin'))[0]==400000000
eth=r.board_eth_snapshot(b,m,p,'completed');assert eth['qualified_powerdown']
result=dict(passed=True,binary_sha256=r.sha(code),request_words=words,proof=p,context=context,
 card=card,magic_format=magic,board_eth=eth,whole_image=r.frame_guards(b,m,p),
 reobservation=dict(original_plan=str(old/'plan.json'),original_proof_sha256=r.sha((old/'proof.json').read_bytes()),
 reason='Host CONTROL checker corrected to admit privileged MSP FPCA/SFPA context; same completed capture, no rerun'))
assert not p['chunk_overflow'] and 1<=p['chunk_count']<=128
(out/'chunks.bin').write_bytes(b.upload(0x343FE000,p['chunk_count']*32,'chunks.bin'))
(out/'producer.bin').write_bytes(b.upload(m['producer'],416,'producer.bin'))
frame=b''.join(b.upload(m['frame']+off,min(r.READ_MAX,r.FRAME_BYTES-off),f'frame-{off:08x}.bin') for off in range(0,r.FRAME_BYTES,r.READ_MAX))
(out/'frame.bin').write_bytes(frame);result['frame_sha256']=r.sha(frame)
assert r.decode(b.upload(r.PROOF,384,'final-proof.bin'),names)==p
r.dump(out/'verified.json',result)
print(json.dumps(dict(passed=True,slot=p['slot'],frame_sha256=result['frame_sha256'],ethernet=eth)))
