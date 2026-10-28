"""Render completed offline gap analyses; no hardware imports/actions."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
FS=2000000
def font(n,b=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n)
def render(rows,title,subtitle,path,ymax):
    width=1560;pitch=340;height=225+len(rows)*pitch
    im=Image.new('RGB',(width,height),'white');d=ImageDraw.Draw(im)
    d.text((65,28),title,fill='#183047',font=font(29,True));d.text((65,73),subtitle,fill='#566b7e',font=font(19))
    xmax=math.ceil(max(max(q['time_ms'] for q in r['profile']) for r in rows)/100)*100
    left,right=95,1470
    x=lambda t:left+(right-left)*t/xmax
    for idx,r in enumerate(rows):
        top=150+idx*pitch;bottom=top+175
        y=lambda a:bottom-(bottom-top)*a/ymax
        d.text((65,top-36),r['label'],fill='#183047',font=font(21,True))
        for value in range(0,ymax+1,50):
            yy=y(value);d.line((left,yy,right,yy),fill='#dce4eb');d.text((left-50,yy-9),str(value),fill='#566b7e',font=font(15))
        for t in range(0,xmax+1,100):
            xx=x(t);d.line((xx,top,xx,bottom),fill='#e8edf2');d.text((xx-13,bottom+38),str(t),fill='#566b7e',font=font(15))
        markers=r['markers'];bands=[('Frame acquisition',2,3,'#98bfeb'),('SD init',4,5,'#f8ba6b'),('Scan/prep',5,6,'#d9b7ec'),('Write',6,7,'#76c5af')]
        if 11 in markers:bands+=[('STOP/validation',3,11,'#efd68f'),('200 ms gap',11,12,'#c0d5d7')]
        for name,a,b,color in bands:
            if b not in markers or markers[b]<=markers[a]:continue
            xa,xb=x(markers[a]),x(markers[b])
            upper=name in ('Frame acquisition','STOP/validation')
            ya,yb=(bottom+4,bottom+17) if upper else ((bottom+4,bottom+34) if name=='200 ms gap' else (bottom+20,bottom+34))
            d.rectangle((xa,ya,xb,yb),fill=color)
            if xb-xa>105:d.text(((xa+xb)/2-35,ya-1),name,fill='#183047',font=font(12))
        for event in (3,11,12,4):
            if event in markers:
                xx=x(markers[event]);d.line((xx,top,xx,bottom),fill='#a7b7c2',width=1)
        assert all(0<=q['current_mA']<=ymax for q in r['profile']),'Do not clip measured current'
        d.line([(x(q['time_ms']),y(q['current_mA'])) for q in r['profile']],fill=r['color'],width=2)
        d.text((65,top+262),r['detail'],fill='#566b7e',font=font(17))
    lx=65
    for label,color in [('Frame acquisition','#98bfeb'),('STOP/validation','#efd68f'),('Gap','#c0d5d7'),('SD init','#f8ba6b'),('Scan/prep','#d9b7ec'),('Write','#76c5af')]:
        d.rectangle((lx,height-87,lx+13,height-74),fill=color);d.text((lx+20,height-90),label,fill='#566b7e',font=font(16));lx+=len(label)*9+65
    d.text((65,height-62),'Current in mA; time in ms. Bars mark firmware intervals. The SD card stays electrically powered throughout the gap.',fill='#263c50',font=font(19))
    d.text((65,height-29),'Curves are 1 ms means. Peak windows use a 0.1 ms search grid; native instantaneous peaks are not qualified.',fill='#566b7e',font=font(18))
    im.save(path)

warm=HERE/'ram-gap01-proof-aligned.json'
if warm.exists():
    r=json.loads(warm.read_text());origin=r['clock_alignment']['origin_sample'];m={x['id']:(x['sample_id']-origin)/FS*1000 for x in r['markers']}
    peak=r['overall_peaks']['1ms'][0];g=r['windows']['gap_last100ms']
    row=dict(label=f'RAM gap01 — peak 1 ms mean {peak["current_mean_mA"]:.1f} mA at {peak["start_ms"]:.1f} ms',profile=json.loads((HERE/'ram-gap01-profile.json').read_text()),markers=m,color='#007b6a',detail=f'GPIO gap {r["windows"]["gap_GPIO"]["duration_ms"]:.3f} ms; last 100 ms mean {g["current_mean_mA"]:.3f} mA. SD init peak {r["windows"]["SD_init"]["peaks_1ms"][0]["current_mean_mA"]:.1f} mA.')
    render([row],'Warm diagnostic: camera STOP, then a 200 ms gap, then SD','Warm RAM run; time from aligned runtime begin. GAP1 confirms zero SD commands through the gap; no automatic shutdown.',HERE/'warm-gap-current.png',150)

summary=HERE/'gap-comparison.json'
if summary.exists():
    s=json.loads(summary.read_text());gaps=[x['run'] for x in s['runs'] if x['group']=='gap']
    if gaps:
        names=(['control-before'] if (HERE/'control-before-analysis.json').exists() else ['normal02'])+gaps
        if (HERE/'control-after-analysis.json').exists():names+=['control-after']
        rows=[]
        for name in names:
            r=json.loads((HERE/(name+'-analysis.json')).read_text());peak=r['peaks_1ms'][0]
            m={x['id']:x['time_ms'] for x in r['marker_events']};gap=r['group']=='gap'
            detail=f'Post-5-ms energy {r["post5ms_to_plateau"]["energy_mJ"]:.1f} mJ; low plateau at {r["whole_cycle_raw_unqualified"]["duration_ms"]:.1f} ms.'
            if gap:detail+=f' Last 100 ms of gap: {r["gap_phase_windows_overlapping_not_additive"]["gap_last100ms"]["current_mean_mA"]:.2f} mA.'
            rows.append(dict(label=f'{name} — peak 1 ms mean {peak["current_mean_mA"]:.1f} mA at {peak["start_ms"]:.1f} ms',profile=json.loads((HERE/(name+'-profile.json')).read_text()),markers=m,color='#007b6a' if gap else '#3266a1',detail=detail))
        render(rows,'Cold capture: separating sensor STOP from SD initialization','Time from current onset; first 5 ms excluded. Fresh normal controls versus diagnostic gap cycles.',HERE/'cold-gap-current-comparison.png',250)
print('Rendered available completed gap plots only.')
