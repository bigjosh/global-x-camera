"""Offline PIO/IDMA sector comparison and exact deletion/CRC-prefix models.

No hardware, subprocess or network API. Fits every k=0..16 without forcing a
fit; dynamic programming counts all valid deletion alignments. Repeated symbols
can make deletion locations ambiguous. A fit is a retained-data observation,
not a waveform, valid-read declaration, or root-cause proof.
"""
import argparse
import binascii
from collections import Counter
from datetime import datetime,timezone
import hashlib
import itertools
import json
from pathlib import Path
import re

ROOT=next(parent for parent in Path(__file__).resolve().parents
    if (parent/'NOTES.md').is_file() and (parent/'firmware/capture-raw').is_dir())
DEFAULT=ROOT/'tmp/bringup/sd-read-pio-dma-20261027'
EXPECTED=('reference125','pio25-01','idma25-01','idma25-02','pio25-02','pio25-03','idma25-03')
IDENTITY=('sector_count','cid0','cid1','cid2','cid3')


def require(ok,message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bound(path):
    path=Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path.read_bytes()))


def symbols(data):
    return [value for byte in data for value in (byte>>4,byte&15)]


def pack(data):
    require(len(data)%2==0,'Packing requires even symbols')
    return bytes((data[index]<<4)|data[index+1] for index in range(0,len(data),2))


def crc16(bits):
    value=0
    for bit in bits:
        feedback=((value>>15)&1)^bit
        value=(value<<1)&65535
        if feedback:
            value^=0x1021
    return value


def crc_symbols(data):
    nibbles=symbols(data)
    require(len(nibbles)%8==0,'CRC cross-check needs whole per-lane bytes')
    lanes=[]
    for lane in range(4):
        bits=[(value>>lane)&1 for value in nibbles]
        checksum=crc16(bits)
        packed=bytes(sum(bits[start+bit]<<(7-bit) for bit in range(8))
            for start in range(0,len(bits),8))
        require(checksum==binascii.crc_hqx(packed,0),'Independent per-lane CRC cross-check failed')
        lanes.append(checksum)
    wire=[sum(((lanes[lane]>>bit)&1)<<lane for lane in range(4))
        for bit in range(15,-1,-1)]
    return wire,lanes


def ranges(indices):
    result=[]
    for value in indices:
        if result and value==result[-1][1]+1:
            result[-1][1]=value
        else:
            result.append([value,value])
    return result


def deletion_alignment(expected,observed,k):
    """Exact subsequence DP, deleting k expected symbols and no substitutions."""
    n,m=len(expected),len(observed)
    require(n-m==k and k>=0,'Deletion geometry differs')
    forward=[{} for _ in range(n+1)]
    forward[0][0]=1
    for i in range(n):
        for deleted,count in forward[i].items():
            j=i-deleted
            if deleted<k:
                forward[i+1][deleted+1]=forward[i+1].get(deleted+1,0)+count
            if j<m and expected[i]==observed[j]:
                forward[i+1][deleted]=forward[i+1].get(deleted,0)+count
    count=forward[n].get(k,0)
    if not count:
        return None
    backward=[set() for _ in range(n+1)]
    backward[n].add(k)
    for i in range(n-1,-1,-1):
        for deleted in range(k+1):
            j=i-deleted
            if not 0<=j<=m:
                continue
            if ((deleted<k and deleted+1 in backward[i+1]) or
                (j<m and expected[i]==observed[j] and deleted in backward[i+1])):
                backward[i].add(deleted)
    possible,forced=[],[]
    for i in range(n):
        can_delete=can_match=False
        for deleted in forward[i]:
            j=i-deleted
            can_delete|=deleted<k and deleted+1 in backward[i+1]
            can_match|=j<m and expected[i]==observed[j] and deleted in backward[i+1]
        if can_delete:
            possible.append(i)
            if not can_match:
                forced.append(i)
    example=[]
    deleted=0
    for i in range(n):
        j=i-deleted
        if j<m and expected[i]==observed[j] and deleted in backward[i+1]:
            continue
        require(deleted<k and deleted+1 in backward[i+1],'DP reconstruction failed')
        example.append(i)
        deleted+=1
    skipped=set(example)
    require([value for i,value in enumerate(expected) if i not in skipped]==observed,
            'Reconstructed deletion model differs')
    return dict(deleted_symbol_count=k,alignment_count_decimal=str(count),
        deletion_locations_unique=count==1,example_deleted_indices=example,
        example_deleted_values=[expected[index] for index in example],
        possible_deleted_index_ranges=ranges(possible),forced_deleted_indices=forced,
        retained_data_symbols=m,
        ambiguity='Repeated equal symbols make exact deletion locations ambiguous' if count>1 else
            'Unique within this deletion-only model; not root-cause or wire-location proof')


def model_report(reference,observed):
    require(len(reference)==len(observed)==512,'Expected two full512-byte sectors')
    expected,actual=symbols(reference),symbols(observed)
    wire,lanes=crc_symbols(reference)
    models=[]
    for k in range(17):
        alignment=deletion_alignment(expected,actual[:len(actual)-k] if k else actual,k)
        tail=actual[len(actual)-k:] if k else []
        item=dict(k=k,deletion_subsequence_fits=alignment is not None,
            crc_prefix_matches=tail==wire[:k],exact_model_fits=alignment is not None and tail==wire[:k])
        if alignment is not None:
            item.update(alignment)
            item['observed_tail_symbols']=tail
            item['computed_crc_prefix_symbols']=wire[:k]
        models.append(item)
    exact=[item['k'] for item in models if item['exact_model_fits']]
    first_byte=next((i for i,(a,b) in enumerate(zip(reference,observed)) if a!=b),None)
    first_symbol=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),None)
    return dict(reference_sha256=sha(reference),observed_sha256=sha(observed),
        identical=observed==reference,differing_bytes=sum(a!=b for a,b in zip(reference,observed)),
        differing_symbols=sum(a!=b for a,b in zip(expected,actual)),
        first_difference_byte=first_byte,first_difference_symbol=first_symbol,
        exact_prefix_bytes=512 if first_byte is None else first_byte,
        start_offset_definition='First differing byte/symbol, zero-based within the512-byte payload',
        last8_bytes_hex=observed[-8:].hex(),last8_bytes_sha256=sha(observed[-8:]),
        lane_crc16_hex=[f'{value:04x}' for value in lanes],computed_crc_wire_hex=pack(wire).hex(),
        crc_cross_check='Bitwise0x1021/initial0 equals independent binascii.crc_hqx per lane',
        fitted_k=exact,models=models,
        conclusion='Exact model(s) found; all fitting k retained' if exact else
            'No deletion plus CRC-prefix model fits for k0..16; no alignment forced')


def historical_reference(campaign):
    # Compact excerpt in the prior archive has explicit full-source provenance.
    archives=(campaign/'reference',campaign.parent/'reference',
        ROOT/'firmware/capture-raw/evidence/2026-10-27-clk-slew/pattern-header-comparison/clk1-trial03-v3')
    for archive in archives:
        if not (archive/'historical-header.bin').is_file():
            continue
        data=(archive/'historical-header.bin').read_bytes()
        provenance=read(archive/'provenance.json')
        proof=read(archive/'historical-read-proof.json')
        require(len(data)==512 and sha(data)==provenance['historical_header_sha256'] and
                proof['passed'] is True and proof['proof']['read_lba']==0 and
                proof['read_sha256']==provenance['historical_full_payload']['sha256'],
                'Archived historical reference provenance differs')
        return data,dict(kind='historical_verified_pattern',header=bound(archive/'historical-header.bin'),
            provenance=bound(archive/'provenance.json'),proof=bound(archive/'historical-read-proof.json'),
            card_identity={key:proof['card'][key] for key in IDENTITY})
    candidates=[campaign/name/'reference-header.bin' for name in EXPECTED]
    for path in candidates:
        if path.exists():
            metadata=read(path.parent/'reference.json')
            data=path.read_bytes()
            require(len(data)==512 and sha(data)==metadata['header_sha256'],'Reference header hash differs')
            return data,dict(kind='attempt_frozen_historical_reference',header=bound(path),metadata=metadata)
    raise ValueError('No verified historical reference is available')


def successful_fresh_reference(campaign):
    folder=campaign/'reference125'
    proof_path=folder/'read/verified.json'
    if not proof_path.exists():
        return None,None
    record=read(proof_path)
    p,c=record['proof'],record['card']
    path=folder/'read/sectors.bin'
    data=path.read_bytes()
    require(record.get('passed') is True and p['operation']==3 and p['result']==0 and
            p['read_lba']==0 and p['read_count']==1 and p['read_bytes']==512 and
            c['clock_hz']==12500000 and c['error']==c['cleanup_error']==c['written_sectors']==0 and
            c['read_sectors']==1 and c['media_idle']==1 and c['initialized']==c['controller_owned']==0 and
            len(data)==512 and sha(data)==record['read_sha256'],'Fresh reference proof differs')
    diagnostic=read(folder/'read/read-diagnostics.json')
    require(diagnostic['camera']['held']==1 and diagnostic['camera']['phase']==2 and
            diagnostic['attribution']['immutable_code_equal'] is True and
            diagnostic['attribution']['final_proof_equal'] is True and
            diagnostic['attribution']['cfsr']==diagnostic['attribution']['hfsr']==0 and
            diagnostic['buffer_sha256']==sha(data),'Fresh reference diagnostics differ')
    return data,dict(kind='fresh12.5MHz_PIO_verified',proof=bound(proof_path),
        payload=bound(path),diagnostics=bound(folder/'read/read-diagnostics.json'),
        card_identity={key:c[key] for key in IDENTITY})


def analyze_attempt(folder,historical,fresh,identity):
    if not folder.is_dir():
        return dict(name=folder.name,outcome='not_started')
    plan_path=folder/'plan.json'
    if not plan_path.exists():
        return dict(name=folder.name,outcome='incomplete_no_plan')
    plan=read(plan_path)
    record=dict(name=folder.name,plan=bound(plan_path),pair=plan['pair'],mode=plan['mode'],
        clock_hz=plan['clock_hz'],binary_sha256=plan['binary_sha256'],outcome='incomplete',
        comparison_historical=None,comparison_fresh_reference=None)
    proof_path=folder/'read/proof.json'
    if not proof_path.exists():
        record['outcome']='host_failed_before_terminal' if (folder/'failed.json').exists() else 'incomplete'
        return record
    p=read(proof_path)
    record['proof']=bound(proof_path)
    record['hardware_result']=p['result']
    record['hardware_flags']={key:p.get(key) for key in ('state','stage','terminal','sd_error',
        'cleanup_error','read_lba','read_count','read_bytes','initialized','controller_owned','media_idle',
        'camera_ready','arm','frames','card_read_lo','card_read_hi','card_write_lo','card_write_hi')}
    record['outcome']='hardware_failed' if p['result'] else 'host_validation_incomplete'
    diagnostic_path=folder/'read/read-diagnostics.json'
    if diagnostic_path.exists():
        diagnostic=read(diagnostic_path)
        record['diagnostics']=bound(diagnostic_path)
        d,c=diagnostic['diagnostics'],diagnostic['card']
        record['receive']=d
        record['card']={key:c.get(key) for key in ('read_sectors','written_sectors','error','error_stage',
            'error_command','error_sta','transfer_words','transfer_sta','transfer_cycles','read_cycles',
            'cleanup_error','initialized','controller_owned','media_idle','clock_hz')}
        record['card_identity']={key:c[key] for key in IDENTITY}
        require(record['card_identity']==identity,'Card differs from historical reference')
        record['attribution']=diagnostic['attribution']
        record['camera']=diagnostic['camera']
        record['transfer_ms_nominal400MHz']=c['transfer_cycles']/400000
        record['read_ms_nominal400MHz']=c['read_cycles']/400000
        record['flag_decode']=dict(DCRCFAIL=bool(d['sta']&2),DTIMEOUT=bool(d['sta']&8),
            RXOVERR=bool(d['sta']&32),DATAEND=bool(d['sta']&256))
        record['receive_word_count_caveat']='IDMA words can remain0 on failure even if DMA changed the destination'
    buffer_path=folder/'read/read-buffer.bin'
    if buffer_path.exists():
        data=buffer_path.read_bytes()
        require(len(data)==512,'Retained destination is not complete512bytes')
        record['buffer']=bound(buffer_path)
        if diagnostic_path.exists():
            require(sha(data)==diagnostic['buffer_sha256'],'Diagnostic buffer hash differs')
        record['comparison_historical']=model_report(historical,data)
        if fresh is not None:
            record['comparison_fresh_reference']=model_report(fresh,data)
    verified_path=folder/'read/verified.json'
    if verified_path.exists():
        verified=read(verified_path)
        require(verified.get('passed') is True and verified['binary_sha256']==plan['binary_sha256'] and
                verified['proof']==p and p['result']==0,'Verified operation identity/result differs')
        record['verified']=bound(verified_path)
        record['outcome']='successful' if record['comparison_historical']['identical'] else 'CRC_clean_data_mismatch'
    record['failed_attempt_is_idle_permission']=False
    return record


def analyze(campaign):
    campaign=Path(campaign).resolve()
    historical,historical_meta=historical_reference(campaign)
    fresh,fresh_meta=successful_fresh_reference(campaign)
    identity=historical_meta.get('card_identity') or historical_meta['metadata']['card_identity']
    records=[analyze_attempt(campaign/name,historical,fresh,identity) for name in EXPECTED]
    # Additional explicit repeat folders are reported rather than silently ignored.
    extra=sorted(path.name for path in campaign.iterdir() if path.is_dir() and
        re.fullmatch(r'(?:pio25|idma25)-[0-9]+',path.name) and path.name not in EXPECTED)
    records += [analyze_attempt(campaign/name,historical,fresh,identity) for name in extra]
    groups={mode:dict(Counter(record['outcome'] for record in records
        if record.get('clock_hz')==25000000 and record.get('mode')==mode)) for mode in ('pio','idma')}
    return dict(schema=1,generated_utc=datetime.now(timezone.utc).isoformat(),hardware_access=False,
        campaign=str(campaign),historical_reference=historical_meta,fresh_reference=fresh_meta,
        fresh_matches_historical=None if fresh is None else fresh==historical,
        formal25_outcomes=groups,records=records,
        all_six_formal_terminal=all(record['outcome'] in ('successful','hardware_failed','CRC_clean_data_mismatch')
            for record in records[1:7]),
        interpretation_limits=['Deletion/CRC-prefix fits describe retained bytes, not the physical waveform.',
            'All k0..16 are tested; no fit is forced and all exact fits are retained.',
            'Repeated symbols can make deletion indices ambiguous; example indices are one valid alignment.',
            'A CRC-failed buffer remains untrusted even if it matches a reference or a model.',
            'IDMA failure words0 does not establish that zero destination words were written.',
            'No reflections, sender/receiver edge error, timing margin or formal compliance conclusion is established.'])


def self_test():
    same=bytes(range(256))*2
    report=model_report(same,same)
    require(0 in report['fitted_k'] and report['identical'],'Unchanged data model failed')
    source=symbols(same)
    crc,_=crc_symbols(same)
    removed={100,200,300,400,500,600,700,800}
    altered=pack([value for index,value in enumerate(source) if index not in removed]+crc[:8])
    fitted=model_report(same,altered)
    require(8 in fitted['fitted_k'],'Synthetic deletion+CRC model failed')
    ambiguous=deletion_alignment([1,1,2],[1,2],1)
    require(ambiguous['alignment_count_decimal']=='2' and not ambiguous['deletion_locations_unique'] and
            ambiguous['possible_deleted_index_ranges']==[[0,1]],'Repeated-symbol ambiguity was hidden')
    nofit=model_report(bytes(512),bytes([255])*512)
    require(not nofit['fitted_k'],'Impossible model was forced')
    cases=0
    for n in range(1,7):
        for source in itertools.product(range(2),repeat=n):
            for k in range(min(3,n)+1):
                expected={}
                for removed in itertools.combinations(range(n),k):
                    output=tuple(value for index,value in enumerate(source) if index not in removed)
                    expected.setdefault(output,[]).append(set(removed))
                for output,alignments in expected.items():
                    got=deletion_alignment(list(source),list(output),k)
                    require(int(got['alignment_count_decimal'])==len(alignments),
                        'Exhaustive alignment count differs')
                    possible={index for first,last in got['possible_deleted_index_ranges']
                        for index in range(first,last+1)}
                    require(possible==set.union(*alignments) and
                        set(got['forced_deleted_indices'])==set.intersection(*alignments),
                        'Exhaustive possible/forced deletion locations differ')
                    cases+=1
    return dict(passed=True,tests=5,exhaustive_small_alignment_cases=cases,hardware_access=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,default=DEFAULT)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    report=self_test() if args.self_test else analyze(args.campaign)
    if args.out:
        with args.out.open('x',encoding='utf-8') as file:
            json.dump(report,file,indent=2,allow_nan=False)
            file.write('\n')
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
