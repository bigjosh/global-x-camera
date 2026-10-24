"""Pure host codec/validation for the independent RAM compute proof; no hardware."""
import struct

MAGIC=0x504e4231
READY=0x52454144
DONE=0x444f4e45
FRAME=0x34000000
FRAME_BYTES=3055360
REPORT=0x343e0000
REQUEST=0x343e0800
CHUNKS=0x343e1000
U32='''magic schema words state operation nonce result stage cpu_hz frame_address frame_bytes
width height mode initial_ccr initial_control initial_mpu initial_fpccr final_ccr final_control
final_ipsr final_primask final_faultmask final_fpccr cfgr1 cfgr2 ahb5enr ahb5rstr xspi_sr
dwt_ctrl dwt_delta input_fnv_before input_fnv_after output_fnv output_bytes rows idat_chunks
callback_calls chunk_count encoder_result stack_canary frame_canary_mask cache_owned timed_out'''.split()
U64='''input_check_cycles encode_cycles sink_cycles cpu_cycles cleanup_cycles final_check_cycles
complete_cycles png_total png_conversion png_deflate png_framing png_callback png_other sink_body_cycles'''.split()
TAIL=['png_clock_calls','png_clock_error']+[f'reserved{i}' for i in range(53)]+['terminal']
assert (len(U32),len(U64),len(TAIL))==(44,14,56)

def fnv(data):
    value=2166136261
    for byte in data:value=((value^byte)*16777619)&0xffffffff
    return value

def request(operation,nonce,mode=1,input_fnv=0,output_fnv=0,output_bytes=0):
    if operation not in (1,2) or not 0<nonce<2**32 or mode not in (0,1,2,3):
        raise ValueError('Invalid operation, nonce or scalar encoder mode')
    if operation==2 and not 0<output_bytes<=3200000:
        raise ValueError('RUN requires expected complete encoded byte count')
    return struct.pack('<16I',MAGIC,1,operation,nonce,mode,input_fnv,output_fnv,output_bytes,*([0]*8))

def decode(raw):
    if len(raw)!=512:raise ValueError('Incomplete compute proof')
    return dict(zip(U32+U64+TAIL,struct.unpack('<44I14Q56I',raw)))

def validate(report,request_raw):
    r=struct.unpack('<16I',request_raw)
    expected=dict(magic=MAGIC,schema=1,words=128,state=2,operation=r[2],nonce=r[3],result=0,
        cpu_hz=400000000,frame_address=FRAME,frame_bytes=FRAME_BYTES,width=1120,height=1364,mode=r[4],
        initial_control=0,final_control=0,final_ipsr=0,final_primask=1,final_faultmask=0,
        cfgr1=0x33330000,cfgr2=0x00100000,stack_canary=0x504e4753,
        terminal=READY if r[2]==1 else DONE)
    if any(report.get(k)!=v for k,v in expected.items()):raise ValueError('Unexpected/stale compute terminal proof')
    if ((report['initial_ccr']|report['final_ccr'])&0x30000 or
        (report['initial_fpccr']|report['final_fpccr']|report['initial_mpu'])&1 or
        not report['dwt_ctrl']&1 or not report['dwt_delta']):
        raise ValueError('Cache/context/clock prerequisite failed')
    if r[2]==2:
        expected=dict(stage=5,input_fnv_before=r[5],input_fnv_after=r[5],output_fnv=r[6],output_bytes=r[7],
            rows=1364,frame_canary_mask=255,cache_owned=1,timed_out=0,encoder_result=0,png_clock_error=0)
        if any(report.get(k)!=v for k,v in expected.items()):raise ValueError('Fixture/encoder integrity proof failed')
        if (report['encode_cycles']!=report['cpu_cycles']+report['sink_cycles'] or
            report['sink_cycles']!=report['png_callback'] or
            not 0<report['sink_body_cycles']<=report['sink_cycles'] or
            report['png_total']!=sum(report['png_'+k] for k in ('conversion','deflate','framing','callback','other')) or
            not 0<report['chunk_count']<=100):raise ValueError('Inconsistent timing or chunk accounting')
    return report

def chunks(raw,count):
    if not 0<count<=100 or len(raw)!=count*32:raise ValueError('Invalid chunk extent')
    rows=[dict(zip(('bytes','fnv','elapsed_cycles','sink_body_cycles','cpu_cycles'),
                   struct.unpack_from('<IIQQQ',raw,i*32))) for i in range(count)]
    previous=0; prior_times=(0,0,0)
    for index,row in enumerate(rows):
        times=tuple(row[k] for k in ('elapsed_cycles','sink_body_cycles','cpu_cycles'))
        if (not previous<row['bytes']<=3200000 or row['bytes']-previous>32768 or
            (index<count-1 and row['bytes']-previous!=32768) or
            any(now<before for now,before in zip(times,prior_times)) or
            row['elapsed_cycles']!=row['sink_body_cycles']+row['cpu_cycles']):
            raise ValueError('Invalid cumulative interval')
        previous=row['bytes'];prior_times=times
    return rows
