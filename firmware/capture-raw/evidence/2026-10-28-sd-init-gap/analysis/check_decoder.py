"""Offline marker-schema regression checks; synthetic arrays only."""
import json
import numpy as np
from analyze_gap import decode,HERE

def signal(ids):
    a=np.zeros(10000,dtype=np.uint8)
    for i,event in enumerate(ids):
        start=100+i*600;a[start:start+4*event+1]=1
    return {'gpi0':(0,a)}

cases=[('normal overlap',[1,2,4,3,5,6,7,8,9,10],False,True),
       ('normal serialized',[1,2,3,4,5,6,7,8,9,10],False,True),
       ('gap complete',[1,2,3,11,12,4,5,6,7,8,9,10],True,True),
       ('gap missing begin',[1,2,3,12,4,5,6,7,8,9,10],True,False),
       ('gap SD before end',[1,2,3,11,4,12,5,6,7,8,9,10],True,False),
       ('gap duplicate ID',[1,2,3,11,11,12,4,5,6,7,8,9,10],True,False)]
results=[]
for title,ids,gap,want in cases:
    try:decode(signal(ids),gap);got=True
    except AssertionError:got=False
    assert got==want,(title,got,want)
    results.append(dict(case=title,accepted=got,expected=want,passed=True))
(HERE/'decoder-checks.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
