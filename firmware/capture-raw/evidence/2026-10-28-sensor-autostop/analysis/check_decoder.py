"""Small pure synthetic tests of the diagnostic phase decoder."""
import json
import numpy as np
from analyze_cold import decode,HERE

def signal(ids):
    v=np.zeros(12000,dtype=np.uint8)
    for i,event in enumerate(ids):
        start=100+i*600;v[start:start+4*event+1]=1
    return {'gpi0':(0,v)}

cases=[
 ('normal overlap',[1,2,4,3,5,6,7,8,9,10],False,True),
 ('normal serialized',[1,2,3,4,5,6,7,8,9,10],False,True),
 ('auto early standby',[1,2,4,3,11,5,6,7,8,9,10],True,True),
 ('auto late observation',[1,2,4,3,5,6,7,11,8,9,10],True,True),
 ('auto beforeframe',[1,2,4,11,3,5,6,7,8,9,10],True,False),
 ('auto missing11',[1,2,4,3,5,6,7,8,9,10],True,False),
 ('auto duplicate11',[1,2,4,3,11,11,5,6,7,8,9,10],True,False),
 ('auto aftercommit',[1,2,4,3,5,6,7,8,11,9,10],True,False),
]
out=[]
for title,ids,auto,want in cases:
    try:decode(signal(ids),auto);got=True
    except AssertionError:got=False
    assert got==want,(title,got,want)
    out.append(dict(case=title,passed=True,accepted=got,expected=want))
for title,ids,auto,want in [
 ('awake normal',[1,2,4,3,5,6,7,8,9],False,True),
 ('awake auto',[1,2,4,3,11,5,6,7,8,9],True,True),
 ('awake auto missing11',[1,2,4,3,5,6,7,8,9],True,False),
 ('awake auto beforeframe',[1,2,4,11,3,5,6,7,8,9],True,False),
]:
    try:decode(signal(ids),auto,awake=True);got=True
    except AssertionError:got=False
    assert got==want,(title,got,want)
    out.append(dict(case=title,passed=True,accepted=got,expected=want))
(HERE/'decoder-checks.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
