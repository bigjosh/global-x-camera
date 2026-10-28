"""Validate finite TIM5 input-capture records against the PE0 event trace.

Timing is relative to the timer's synchronized PA0 input, not a direct optical
measurement. This read-only decoder never controls hardware or rewrites evidence.
"""
import argparse
import json
from pathlib import Path

MASK=0xFFFFFFFF
def delta(a,b): return (a-b)&MASK
def require(condition,message):
    if not condition: raise ValueError(message)


def analyze(result,timing):
    w=result['timer_status_words']
    require(len(w)==224,'Expected exactly224 timer words')
    require(w[0]==0x54354943 and w[1]==0,'TIM5 probe did not initialize')
    require((w[2],w[3])==(300000000,400000000),'Unexpected timer/core frequency')
    require(w[4]==0x33330000 and w[5]==0x00100000,'Unexpected ROM clock profile')
    require(not(w[8]&8) and not any(w[9:13]),'TIM5 ownership/reset-state guard failed')
    require(w[13]&3==2 and w[14]&15==2,'PA0 is not AF2')
    require(w[15]&255==0 and all(w[i]&1 for i in (16,17,18)),'EXTI0 route/triggers/mask invalid')
    require(w[19:24]==[1,11,0,0,0xFFFFFFFF],'Timer capture configuration invalid')
    count=w[24]
    require(2<=count<=16 and not w[25],'Missing records or timer log overflow')
    require(timing.get('matched') and timing.get('mode')=='cold','Need matched cold PE0 trace')
    require(result.get('completed') and result.get('frames')==1,'Need completed first-frame snapshot')
    expected=[(i,e) for i,e in enumerate(result['events']) if e['id'] in (50,51)]
    require(len(expected)==count,'Capture/event count mismatch')
    timer_hz,core_hz=w[2],w[3]
    # The true CNT-read instant is bracketed by DWT reads at each end.
    elapsed_timer=delta(w[30],w[27])
    elapsed_core_min=delta(w[29],w[28])
    elapsed_core_max=delta(w[31],w[26])
    require(0<elapsed_core_min<=elapsed_core_max<0x80000000,'Invalid DWT calibration interval')
    require(0<elapsed_timer<0x80000000,'Invalid timer calibration interval')
    require(elapsed_core_min*timer_hz-2*core_hz <= elapsed_timer*core_hz <=
            elapsed_core_max*timer_hz+2*core_hz,'Timer/DWT clock ratio inconsistent')
    # Nominal400/300MHz share the HSI-derived PLL error. Rates also vary over
    # this run: the long post-frame interval must not set an assumed constant
    # frequency for first exposure. Use independent non-strobe endpoints.
    endpoint_allowance_s=20.32e-6
    observations=[]
    for a,b in ((200,25),(25,3),(25,30),(3,31),(26,29),(29,30),(31,40),(3,40)):
        ia=next((i for i,e in enumerate(result['events']) if e['id']==a),None)
        ib=next((i for i,e in enumerate(result['events']) if e['id']==b),None)
        if ia is None or ib is None:continue
        require(ia<ib,'Independent calibration events are out of order')
        settings_match=all(e['core_hz']==core_hz for e in result['events'][ia:ib+1])
        seconds=timing['events'][ib]['time_s']-timing['events'][ia]['time_s']
        cycles=delta(result['events'][ib]['cycles'],result['events'][ia]['cycles'])
        require(0.001<seconds<5 and 0<cycles<0x80000000,'Invalid independent calibration interval')
        rate=cycles/seconds
        observations.append(dict(first_event=a,last_event=b,external_seconds=seconds,core_cycles=cycles,
            core_hz=rate,timer_hz=rate*timer_hz/core_hz,
            recorded_core_settings_match=settings_match,
            included_in_empirical_envelope=seconds>=0.01 and settings_match,
            timer_hz_min=cycles/(seconds+endpoint_allowance_s)*timer_hz/core_hz,
            timer_hz_max=cycles/(seconds-endpoint_allowance_s)*timer_hz/core_hz))
    local=next((o for o in observations if (o['first_event'],o['last_event'])==(26,29)),None)
    require(local is not None and local['included_in_empirical_envelope'],
            'Need independent near-exposure event26-to29 interval with stable clock metadata')
    measured_core_hz,measured_timer_hz=local['core_hz'],local['timer_hz']
    envelope=[o for o in observations if o['included_in_empirical_envelope']]
    timer_low=min(o['timer_hz_min'] for o in envelope)
    timer_high=max(o['timer_hz_max'] for o in envelope)
    records=[]
    for n,(event_index,event) in enumerate(expected):
        r=w[32+n*12:44+n*12]
        require(r[0]==event['id'] and r[10]==event_index+1,f'Record{n}: event association mismatch')
        require(r[0]==(50 if n%2==0 else 51),f'Record{n}: rising/falling order mismatch')
        require(r[11]==15,f'Record{n}: capture validity bits not all set')
        require(r[3]&2 and not((r[3]|r[5])&0x200) and not(r[5]&2),
                f'Record{n}: missing/overwritten capture')
        require((r[9]&1)==(r[0]==50),f'Record{n}: PA0 level contradicts edge')
        lag_min,lag_max=delta(r[1],r[4]),delta(r[2],r[4])
        require((r[6],r[7])==(lag_min,lag_max),f'Record{n}: subtraction mismatch')
        require(0<lag_min<=lag_max<timer_hz//1000,
                f'Record{n}: nonpositive, wrapped or >=1ms marker lag')
        require(delta(r[8],event['cycles'])<core_hz//1000,
                f'Record{n}: record is not contemporaneous with event')
        external=timing['events'][event_index]
        require(external['id']==event['id'],f'Record{n}: external event mismatch')
        marker_us=external['after_nrst_us']
        lo,hi=lag_min*1e6/timer_high,lag_max*1e6/timer_low
        records.append(dict(ordinal=n+1,id=r[0],event_index=event_index,captured_counter=r[4],
            marker_lag_min_us=lo,marker_lag_max_us=hi,
            nominal_marker_lag_min_us=lag_min*1e6/timer_hz,
            nominal_marker_lag_max_us=lag_max*1e6/timer_hz,
            synchronized_edge_after_nrst_min_us=marker_us-hi,
            synchronized_edge_after_nrst_max_us=marker_us-lo,
            marker_after_nrst_us=marker_us,validity=r[11],sr_before=r[3],sr_after=r[5]))
    pulses=[]
    for i in range(0,count-1,2):
        rise,fall=records[i:i+2]
        ticks=delta(fall['captured_counter'],rise['captured_counter'])
        width=ticks*1e6/measured_timer_hz
        width_low,width_high=ticks*1e6/timer_high,ticks*1e6/timer_low
        external_width=fall['marker_after_nrst_us']-rise['marker_after_nrst_us']
        lower=external_width-fall['marker_lag_max_us']+rise['marker_lag_min_us']
        upper=external_width-fall['marker_lag_min_us']+rise['marker_lag_max_us']
        require(width_high>=lower-0.32 and width_low<=upper+0.32,
                f'Pulse{i//2+1}: hardware/external widths disagree')
        pulses.append(dict(ordinal=i//2+1,hardware_width_us=width,
                           hardware_width_min_us=width_low,hardware_width_max_us=width_high,
                           nominal_hardware_width_us=ticks*1e6/timer_hz,
                           external_marker_width_us=external_width))
    frame_index=next(i for i,e in enumerate(result['events']) if e['id']==30)
    require(expected[0][0]<expected[1][0]<frame_index,'First pulse does not precede first frame')
    return dict(valid=True,timer='TIM5',nominal_timer_hz=timer_hz,nominal_core_hz=core_hz,
        measured_timer_hz=measured_timer_hz,measured_core_hz=measured_core_hz,
        independent_frequency_calibration=dict(first_event=26,last_event=29,
            external_seconds=local['external_seconds'],core_cycles=local['core_cycles'],
            total_endpoint_allowance_us=endpoint_allowance_s*1e6,
            allowance_note='10us logging allowance and one0.16us Saleae sample per endpoint; conservative assumption, not proved worst-case.',
            envelope_note='Observed non-strobe interval rates plus endpoint allowance; empirical consistency envelope, not a universal or pointwise frequency bound.',
            observations=observations,
            timer_hz_min=timer_low,timer_hz_max=timer_high),
        calibration=dict(timer_ticks=elapsed_timer,core_cycles_min=elapsed_core_min,
                         core_cycles_max=elapsed_core_max),records=records,pulses=pulses,
        maximum_observed_marker_lag_us=max(r['marker_lag_max_us'] for r in records),
        limitation='Observed bracket relative to synchronized timer input; excludes sensor/translator/input synchronization delay and is not a universal IRQ-latency bound.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    result=json.loads((a.capture/'ram/capture-result.json').read_text())
    timing=json.loads((a.capture/'timing.json').read_text())
    decoded=analyze(result,timing)
    data=json.dumps(decoded,indent=2)+'\n'
    if a.output:
        with a.output.open('x',encoding='utf-8') as f:f.write(data)
    print(data,end='')


if __name__=='__main__':main()
