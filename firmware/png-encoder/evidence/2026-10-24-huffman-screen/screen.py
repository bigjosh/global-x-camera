"""Local offline screen only: source copies, no hardware, no published pixels."""
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import sys
import time
import numpy as np

import argparse
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--raw',type=Path,help='Optional private 1120x1364 RAW10 LE16 frame; never copied')
p.add_argument('--out',type=Path,required=True,help='New output folder for disposable source copies and JSON')
a=p.parse_args()
HERE=a.out.resolve();HERE.mkdir(parents=True,exist_ok=False)
ENC=Path(__file__).resolve().parent/'baseline'
index=json.loads((ENC.parent/'baseline-index.json').read_text())
for record in index['files']:
    data=(ENC.parent/record['path']).read_bytes()
    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256']
sys.path.insert(0,str(ENC))
import test_png16 as test
base='TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG | 1'
variants={
 'baseline':base,
 'fixed':base+' | TDEFL_FORCE_ALL_STATIC_BLOCKS',
 'huffman_only':'TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG',
 'rle':base+' | TDEFL_RLE_MATCHES',
 'filtered':base+' | TDEFL_FILTER_MATCHES',
 'two_probes':'TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG | 2',
 'larger_workspace':base,
 'direct_huffman':'TDEFL_WRITE_ZLIB_HEADER | TDEFL_GREEDY_PARSING_FLAG',
}
W,H=1120,1364
cases={
 'noise':np.random.default_rng(5943).integers(0,1024,W*H,dtype=np.uint16).astype('<u2').tobytes(),
 'constant64':np.full(W*H,64,dtype='<u2').tobytes(),
}
if a.raw:
    raw=a.raw.read_bytes()
    assert len(raw)==W*H*2 and np.all(np.frombuffer(raw,dtype='<u2')<=1023)
    cases['supplied_private_frame']=raw
records=[]
for variant,flags in variants.items():
    folder=HERE/variant
    shutil.copytree(ENC,folder,ignore=shutil.ignore_patterns('__pycache__'))
    p=folder/'png16.c';txt=p.read_text();assert txt.count(base)==1
    p.write_text(txt.replace(base,flags))
    if variant=='larger_workspace':
        p=folder/'miniz_config.h';p.write_text(p.read_text().replace('TDEFL_LESS_MEMORY 1','TDEFL_LESS_MEMORY 0'))
        p=folder/'png16.h';p.write_text(p.read_text().replace('(192U * 1024U)','(384U * 1024U)'))
    if variant=='direct_huffman':
        p=folder/'vendor/miniz/miniz_tdef.c';text=p.read_text()
        needle='        tdefl_flush flush = d->m_flush;'
        assert text.count(needle)==1
        body=(ENC.parent/'direct-prototype.txt').read_text()
        p.write_text(text.replace(needle,needle+'\n'+body))
    test.HERE=folder
    lib=test.compile_library(folder)
    try:
        needed=lib.png16_workspace_size()
        workspace=(C.c_uint64*((needed+7)//8))()
        for name,raw in cases.items():
            source=C.create_string_buffer(raw)
            for mode in (1,2):
                pieces=[]
                @test.WRITE
                def sink(user,data,n):
                    pieces.append(C.string_at(data,n));return 1
                stats=test.Stats();times=[]
                for repeat in range(6):
                    pieces.clear();start=time.perf_counter_ns()
                    status=lib.png16_encode(source,len(raw),W,H,W*2,mode,workspace,needed,sink,None,C.byref(stats))
                    elapsed=(time.perf_counter_ns()-start)/1e6
                    assert status==0
                    if repeat:times.append(elapsed)
                encoded=b''.join(pieces)
                width,height,pixels,*_=test.parse_png(encoded)
                assert (width,height)==(W,H)
                assert np.array_equal(np.asarray(pixels),np.frombuffer(raw,dtype='<u2').astype(np.uint32)<<6)
                assert C.string_at(source,len(raw))==raw
                record=dict(variant=variant,mode='none' if mode==1 else 'sub',case=name,
                    input_sha256=hashlib.sha256(raw).hexdigest(),png_bytes=len(encoded),
                    host_median_ms=statistics.median(times),host_min_ms=min(times),host_max_ms=max(times),
                    exact_pixels=True,workspace_bytes=needed,flags=flags)
                records.append(record);print(json.dumps(record),flush=True)
    finally:test.close_library(lib)
report=dict(hardware_access=False,scope='Host Clang -O2 encode wall, Python collecting callbacks; NOT MCU predictions. Five timed repeats after warmup; every decoded sample validated.',records=records)
(HERE/'report.json').write_text(json.dumps(report,indent=2)+'\n')
