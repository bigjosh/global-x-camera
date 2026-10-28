"""Offline PHY power-down A/B/A decode and current analysis. No hardware APIs."""
from pathlib import Path
import json, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from analyze_isolated import HERE, CAMPAIGN
from analyze_warm_ablations import load
from analyze_existing_baseline import FS, metrics, sha

FIELDS=('magic version state error cleanup begin end dwt_hz rcc0 rcc1 rstr0 cfgr1 cfgr2 ic1 pll1a pll1b pll1c dwt_ctrl demcr mdio_high0 mdio_low mdio_high1 mdc_low mdc_high mdc_low2 clock_low_fail clock_high_fail bit_count scan_count match_count first_match restore_match').split()
TAIL='control ipsr msp msplim old_msp old_msplim reserved2 reserved3'.split()
EXTRA='id1 id2 bmcr0 bmcr1 requested after0 after1 restored0 restored1 polls writes restore_writes restored failure_stage restore_error'.split()
WINDOWS='a_start a_end b_start b_end c_start c_end settle_cycles hold_cycles a_loops b_loops c_loops restore_id1 restore_id2 marker_error d_safe'.split()

def analyze(run):
    folder=CAMPAIGN/run;debug=folder/'debug';raw=(debug/'proof-after.bin').read_bytes()
    w=struct.unpack('<512I',raw);p=dict(zip(FIELDS,w[:32]));p.update(zip(TAIL,w[56:64]));p.update(zip(EXTRA,w[64:79]));p.update(zip(WINDOWS,w[80:95]))
    for name,pos in [('f_before',32),('g_before',38),('f_after',44),('g_after',50),('d_before',96),('d_after',102)]:p[name]=dict(zip('mode type speed pull af odr'.split(),w[pos:pos+6]))
    v=json.loads((debug/'result.json').read_text());m=json.loads((CAMPAIGN/'mdio/power_aba/manifest.json').read_text())
    assert v['completed_and_restored'] and v['phy_restored_verified'] and v['proof_stable'] and p==v['proof']
    assert (debug/'proof-before.bin').read_bytes()==raw and (debug/'faults.bin').read_bytes()==bytes(8)
    assert sha(debug/'diagnostic-readback.bin')==sha(debug/'diagnostic-after.bin')==m['sha256']==v['code_sha256']
    assert v['pc']==m['park'] and v['cfsr']==v['hfsr']==0
    exact=dict(magic=0x33414241,version=3,state=8,error=0,cleanup=0,dwt_hz=400000000,cfgr1=0x33330000,cfgr2=0x100000,ic1=0x20000,pll1a=0x404b00,pll1b=0,pll1c=0x49000005,clock_low_fail=0,clock_high_fail=0,restore_match=1,control=0,ipsr=0,msplim=0x343af000,id1=7,id2=0xc131,bmcr0=0x3000,bmcr1=0x3000,requested=0x3800,after0=0x3800,after1=0x3800,restored0=0x3000,restored1=0x3000,writes=1,restore_writes=1,restored=1,restore_error=0,failure_stage=0,restore_id1=7,restore_id2=0xc131,settle_cycles=40000000,hold_cycles=120000000,marker_error=0,d_safe=1)
    assert all(p[k]==x for k,x in exact.items())
    assert [p[k] for k in ('mdio_high0','mdio_low','mdio_high1','mdc_low','mdc_high','mdc_low2')]==[1,0,1,0,1,0]
    assert p['rcc0']==p['rcc1'] and p['bit_count']>=780 and p['bit_count']%65==0 and 1<=p['polls']<=100
    assert p['a_loops']==p['b_loops']==p['c_loops']>0
    assert all(p[s+'_before']==p[s+'_after'] for s in ('f','g','d'))
    signals,checks=load(folder/'trace');st,gpi=signals['gpi0'];ei=np.flatnonzero(gpi[1:]!=gpi[:-1])+1
    edges=[dict(sample_id=int(st+x),level=int(gpi[x])) for x in ei];pulses=[]
    for a,b in zip(edges,edges[1:]):
        if a['level']==1 and b['level']==0:pulses.append(dict(sample_id=a['sample_id'],end_sample_id=b['sample_id'],width_us=(b['sample_id']-a['sample_id'])/FS*1e6))
    expected=list(range(11,17));trains=[]
    for k in range(len(pulses)-5):
        t=pulses[k:k+6];offsets=[x['width_us']-2*i for x,i in zip(t,expected)];overhead=float(np.median(offsets))
        if not(-.25<=overhead<=3 and max(abs(x-overhead) for x in offsets)<=.75):continue
        if all(abs(((t[j+1]['sample_id']-t[j]['sample_id'])/FS)/(((p[phase+'_end']-p[phase+'_start'])&0xffffffff)/400e6)-1)<.02 for j,phase in ((0,'a'),(2,'b'),(4,'c'))):trains.append((t,overhead))
    assert len(trains)==1,('Unique waveform/proof signature',trains,pulses)
    t,overhead=trains[0];origin=t[0]['sample_id'];intervals={};spikes={}
    for name,j in [('baseline',0),('powerdown',2),('restored',4)]:
        a,b=t[j]['sample_id'],t[j+1]['sample_id'];intervals[name+'_full']=metrics(signals,a,b,origin)
        a+=50000;b-=50000;intervals[name+'_middle']=metrics(signals,a,b,origin)
        start,cur=signals['current'];x=np.asarray(cur[a-start:b-start]);n=len(x)//200;means=x[:n*200].reshape(-1,200).mean(axis=1,dtype=np.float64)
        median=float(np.median(means));high=means>median+.003;rise=np.flatnonzero(high[1:]&~high[:-1])+1
        times=(a-origin+rise*200)/FS*1000
        bursts=[float(x) for j,x in enumerate(times) if j==0 or x-times[j-1]>3]
        periods=np.diff(bursts)
        spikes[name]=dict(rule='100us mean current exceeds its window median by3mA. Group rising edges separated by<=3ms into one burst; preserve all raw crossings. This is not an electrical/protocol classification.',median_current_mA=median*1000,detected_rising_times_ms=times.tolist(),raw_crossing_count=len(rise),burst_start_times_ms=bursts,burst_count=len(bursts),median_period_ms=float(np.median(periods)) if len(periods) else None,min_period_ms=float(np.min(periods)) if len(periods) else None,max_period_ms=float(np.max(periods)) if len(periods) else None,max_100us_current_mA=float(np.max(means))*1000)
    a,b,c=(intervals[s+'_middle'] for s in ('baseline','powerdown','restored'));baseline_i=(a['current_mean_mA']+c['current_mean_mA'])/2;baseline_p=(a['power_mean']+c['power_mean'])/2
    result=dict(run=run,scope=v['scope'],proof=p,proof_sha256=sha(debug/'proof-after.bin'),result_sha256=sha(debug/'result.json'),code_sha256=m['sha256'],checks=checks,markers=[dict(id=i,name=v['markers'][str(i)],**x) for i,x in zip(expected,t)],marker_width_offset_us=overhead,interval_boundary='Rising marker edges, and middle windows discard25ms from each end. Each hold follows100ms settling. Native JS sample IDs provide wall time.',intervals=intervals,spikes=spikes,all_gpi0_edges=edges,unclassified_gpi0_edges=len(edges)-12,
        comparison=dict(baseline_surrounding_mean_mA=baseline_i,original_baseline_mA=a['current_mean_mA'],restored_baseline_mA=c['current_mean_mA'],powerdown_mA=b['current_mean_mA'],saving_mA=baseline_i-b['current_mean_mA'],saving_mW=(baseline_p-b['power_mean'])*1000,saving_fraction_percent=100*(baseline_p-b['power_mean'])/baseline_p,original_minus_powerdown_mA=a['current_mean_mA']-b['current_mean_mA'],restored_minus_powerdown_mA=c['current_mean_mA']-b['current_mean_mA'],restored_minus_baseline_mA=c['current_mean_mA']-a['current_mean_mA']),
        caveats=['Difference includes PHY and its upstream conversion losses, not pure PHY silicon power.', 'Remaining power is whole Nucleo plus MCU, not MCU-only attribution.', 'Specific link-pulse mechanism is inferred from current modulation; no Ethernet waveform was measured.', 'Restored BMCR/IDs and DC draw do not mean the full baseline waveform has returned: periodic bursts are absent from the measured100..400ms post-restore hold.'])
    (HERE/(run+'-phy-analysis.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(run=run,comparison=result['comparison'],spikes=spikes),indent=2))
    # Standalone current figure: actual gaps between measured holds retained.
    im=Image.new('RGB',(1500,820),'white');d=ImageDraw.Draw(im)
    def font(s,b=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),s)
    d.text((65,35),run+': Ethernet PHY power-down and restoration',fill='#182536',font=font(30,True))
    d.text((65,82),'Same400MHz busy loop · camera and SD disconnected · one BMCR write down, one write restoring original value',fill='#526477',font=font(19))
    end=t[-1]['sample_id'];x0,x1,y0,y1=100,1410,160,630;duration=(end-origin)/FS*1000
    def xy(ms,ma):return(x0+(x1-x0)*ms/duration,y1-(y1-y0)*ma/90)
    for n,col,j in [('Normal','#e4ecf8',0),('Powered down','#dbf2e7',2),('Restored','#e4ecf8',4)]:
        xx,_=xy((t[j]['sample_id']-origin)/FS*1000,0);xx2,_=xy((t[j+1]['sample_id']-origin)/FS*1000,0);d.rectangle((xx,y0,xx2,y1),fill=col);d.text((xx+20,125),n,fill='#24364a',font=font(21,True))
    for ma in range(0,91,15):
        _,y=xy(0,ma);d.line((x0,y,x1,y),fill='#ced9e4');d.text((45,y-12),str(ma),fill='#526477',font=font(18))
    for ms in range(0,int(duration)+1,100):
        x,_=xy(ms,0);d.text((x-12,y1+12),str(ms),fill='#526477',font=font(18))
    start,cur=signals['current'];pts=[]
    for a0 in range(origin,end-1999,2000):pts.append(xy((a0-origin+1000)/FS*1000,float(np.mean(cur[a0-start:a0-start+2000],dtype=np.float64))*1000))
    d.line(pts,fill='#1e5a91',width=3);d.text((40,125),'mA',fill='#526477',font=font(19))
    d.text((1050,675),'ms since baseline-start marker',fill='#526477',font=font(18))
    d.text((65,722),f"Mean normal/restored {baseline_i:.2f}mA → power-down {b['current_mean_mA']:.2f}mA: saving {result['comparison']['saving_mA']:.2f}mA ({result['comparison']['saving_fraction_percent']:.1f}%)",fill='#182536',font=font(23,True))
    d.text((65,770),'Current shown as1ms means; reported means trim25ms from each hold end. White gaps include register transactions and settling.',fill='#526477',font=font(18))
    im.save(HERE/(run+'-phy-current.png'));return result

if __name__=='__main__':
    reports=[analyze(x) for x in sys.argv[1:]]
    (HERE/'phy-summary.json').write_text(json.dumps(reports,indent=2)+'\n')
