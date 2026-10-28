"""Offline current comparison around standalone busy-hold then shallow-WFI probe."""
from pathlib import Path
import argparse,csv,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from analyze_warm_ablations import load
from analyze_existing_baseline import FS,metrics,sha
BASE=Path(__file__).resolve().parent

def analyze(folder):
    signals,checks=load(folder/'trace');st,g=signals['gpi0'];ei=np.flatnonzero(g[1:]!=g[:-1])+1;ps=[]
    for a,b in zip(ei,ei[1:]):
        if g[a]==1 and g[b]==0:
            width=(b-a)/2;ids=[i for i in (11,12) if abs(width-(i*2+.24))<=.8]
            if ids:ps.append({'id':ids[0],'start':int(st+a),'end':int(st+b),'width_us':width})
    assert [p['id'] for p in ps]==[11,12],ps
    t0=ps[0]['start'];t1=ps[1]['start'];assert .18*FS<t1-t0<.22*FS
    windows=[]
    for name,a,b in [('busy_hold_middle',t0+FS//40,t1-FS//40),('after12_100to300ms',t1+FS//10,t1+3*FS//10),('after12_500to1500ms',t1+FS//2,t1+3*FS//2)]:
        m=metrics(signals,a,b,t0);m['name']=name;windows.append(m)
    observation=folder/'observation.json';obs=json.loads(observation.read_text()) if observation.exists() else None
    result={'run':folder.name,'checks':checks,'markers':ps,'busy_hold_observed_ms':(t1-t0)/FS*1000,'windows':windows,'postwindow_observation':obs,'wfi_independently_proven_here':bool(obs and obs.get('passed')),'scope':'Current association after emitted phase12. Absent/failed live proof is not relabeled as successful WFI/unchanged-register qualification. Retained proof after recovery, if obtained, belongs to a separate record.','current_delta_middle_to_late_mA':windows[0]['current_mean_mA']-windows[2]['current_mean_mA'],'power_delta_middle_to_late_mW':1000*(windows[0]['power_mean']-windows[2]['power_mean'])}
    profile=[]
    for a in range(t0,t1+2*FS-9999,10000):
        m=metrics(signals,a,a+10000,t0);profile.append({'time_ms':(a+5000-t0)/FS*1000,'current_mean_mA':m['current_mean_mA'],'voltage_mean':m['voltage_mean']})
    (BASE/(folder.name+'-current-analysis.json')).write_text(json.dumps(result,indent=2)+'\n')
    with (BASE/(folder.name+'-current-5ms.csv')).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(profile[0]));w.writeheader();w.writerows(profile)
    font=lambda n,b=False:ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n)
    im=Image.new('RGB',(1400,650),'white');d=ImageDraw.Draw(im);L,R,T,B=100,1330,150,490
    xx=lambda t:L+t/2200*(R-L);yy=lambda a:B-a/100*(B-T)
    d.text((60,30),'Busy hold followed by the requested shallow-sleep path',font=font(28,True),fill='#17243b')
    d.text((60,76),'Measured current only; live post-window debugger read failed. Retained execution proof is separate.',font=font(18),fill='#42536b')
    for a in (0,20,40,60,80,100):
        y=yy(a);d.line((L,y,R,y),fill='#e1e5eb');d.text((L-45,y-10),str(a),font=font(17),fill='#536177')
    for t in range(0,2201,200):
        x=xx(t);d.line((x,T,x,B),fill='#ebedf1');d.text((x-15,B+9),str(t),font=font(17),fill='#536177')
    d.line([(xx(p['time_ms']),yy(p['current_mean_mA'])) for p in profile],fill='#7c3aed',width=2)
    x=xx((t1-t0)/FS*1000);d.line((x,T,x,B),fill='#e11d48',width=2);d.text((x+10,T+8),'Marker12: hold ends, then WFI instruction path',font=font(18),fill='#b91c1c')
    d.text((L,T-30),'Current (mA); 5 ms means',font=font(20,True),fill='#17243b');d.text((550,B+40),'Milliseconds from marker11',font=font(18),fill='#536177')
    d.text((60,590),f"Busy middle {windows[0]['current_mean_mA']:.3f} mA; later plateau {windows[2]['current_mean_mA']:.3f} mA; reduction {result['current_delta_middle_to_late_mA']:.3f} mA.",font=font(21,True),fill='#17243b')
    im.save(BASE/(folder.name+'-current.png'))
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('run');args=ap.parse_args();analyze(BASE/args.run)
