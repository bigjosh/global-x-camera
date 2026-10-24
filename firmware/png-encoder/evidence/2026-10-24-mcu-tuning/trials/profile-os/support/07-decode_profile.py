"""Read only: decode isolated MPF1 extension, never operate hardware.

Input is a 512-byte compute report or terminal.json produced by the existing
compute runner. Successful basic fixture/park proof remains a separate gate.
"""
import argparse,json,struct
from pathlib import Path
NAMES=['compress_inclusive','accumulate_inclusive','flush_inclusive',
       'dynamic_header_inclusive','tree_construction','static_header_inclusive',
       'lz_code_emission','adler','output_callback','raw_fallback',
       'flush_output_buffer','init','accumulate_flush_child','histogram_clear']
def decode(words,require_mcu=True):
    if len(words)!=53 or words[:3]!=[0x4d504631,1,14] or words[47]!=53 or any(words[48:]):
        raise ValueError('Not an exact MPF1 extension')
    if words[46] not in (0,1) or (require_mcu and words[46]!=1):
        raise ValueError('Expected MCU DWT clock')
    c=[words[4+2*i]+(words[5+2*i]<<32) for i in range(14)]
    calls=words[32:46]
    if calls[12]!=calls[1] or words[3]!=2*(sum(calls)-calls[12]):
        raise ValueError('Probe/call accounting mismatch')
    disjoint={
        'accumulation_including_histogram_updates':c[1]-c[12],
        'huffman_tree_construction':c[4],
        'huffman_header_other':c[3]+c[5]-c[4],
        'lz_code_emission':c[6],
        'adler':c[7],
        'raw_fallback_emission':c[9],
        'histogram_clear':c[13],
        'block_flush_other':c[2]-c[3]-c[5]-c[6]-c[8]-c[9]-c[13],
        'flush_output_buffer':c[10],
        'compress_other':c[0]-(c[1]-c[12])-c[2]-c[7]-c[10],
        'init':c[11],
        'compressed_output_callback':c[8],
    }
    if min(disjoint.values())<0 or sum(disjoint.values())!=c[0]+c[11]:
        raise ValueError('Nested interval accounting failed')
    return dict(schema=1,clock='nominal 400 MHz DWT' if words[46] else 'host C clock ticks',
        clock_reads=words[3],inclusive={n:dict(cycles=c[i],calls=calls[i]) for i,n in enumerate(NAMES)},
        disjoint_cycles=disjoint,deflate_excluding_output_cycles=c[0]+c[11]-c[8],
        scope='Instrumented profiling only; contains probe/layout cost, not uninstrumented speed',
        cpu_ms={n:v/400000 for n,v in disjoint.items()} if words[46] else None)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path)
    p.add_argument('--out',type=Path);a=p.parse_args()
    if a.report.suffix=='.json':
        report=json.loads(a.report.read_text());words=[report['reserved'+str(i)] for i in range(53)]
    else:
        raw=a.report.read_bytes()
        if len(raw)!=512:raise ValueError('Expected complete 512-byte report')
        words=list(struct.unpack_from('<53I',raw,74*4))
    result=decode(words);text=json.dumps(result,indent=2)+'\n'
    if a.out:a.out.write_text(text)
    print(text)
if __name__=='__main__':main()
