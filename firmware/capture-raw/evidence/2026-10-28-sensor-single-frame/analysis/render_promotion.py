"""Offline current/timing figure from completed promotion analyses."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
def font(n,b=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if b else 'arial.ttf'),n)
summary=json.loads((HERE/'cold-promotion-comparison.json').read_text())
rows=[]
for item in summary['runs']:
    name=item['run'];r=json.loads((HERE/(name+'-analysis.json')).read_text())
    rows.append((item,r,json.loads((HERE/(name+'-profile.json')).read_text())))
width=1600;pitch=280;height=200+pitch*len(rows)
im=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(im)
draw.text((65,24),'Cold capture: before and after automatic one-frame stop',fill='#183047',font=font(31,True))
draw.text((65,70),'Whole-board 5 V input | 1 ms current means | first 5 ms excluded | time from measured current onset',fill='#566b7e',font=font(21))
xmax=math.ceil(max(max(p['time_ms'] for p in profile) for _,_,profile in rows)/100)*100
ymax=math.ceil(max(max(p['current_mA'] for p in profile) for _,_,profile in rows)/50)*50
left,right=105,1515;x=lambda t:left+(right-left)*t/xmax
for index,(item,r,profile) in enumerate(rows):
    top=150+index*pitch;bottom=top+160;y=lambda a:bottom-(bottom-top)*a/ymax
    color='#c45b39' if item['group']=='normal' else '#147d92'
    title=f"{item['run']} | {item['post5ms_energy_mJ']:.2f} mJ | {item['onset_to_low_plateau_ms']:.2f} ms to low plateau | peak 1 ms mean {item['peak1ms_mean_mA']:.2f} mA"
    draw.text((65,top-32),title,fill=color,font=font(21,True))
    for a in range(0,ymax+1,50):
        draw.line((left,y(a),right,y(a)),fill='#dce4eb');draw.text((left-50,y(a)-9),str(a),fill='#566b7e',font=font(16))
    for t in range(0,xmax+1,100):
        draw.line((x(t),top,x(t),bottom),fill='#e8edf2');draw.text((x(t)-13,bottom+38),str(t),fill='#566b7e',font=font(16))
    assert all(0<=p['current_mA']<=ymax for p in profile)
    draw.line([(x(p['time_ms']),y(p['current_mA'])) for p in profile],fill=color,width=3)
    markers={e['id']:e['time_ms'] for e in r['marker_events']}
    bands=[('Receive frame',2,3,'#98bfeb',0),('SD init',4,5,'#f8ba6b',1),('Scan/prep',5,6,'#d9b7ec',1),('Write',6,7,'#76c5af',1)]
    if 11 in markers:bands.append(('Stop observed',3,11,'#c0d5d7',0))
    for name,a,b,c,lane in bands:
        ya=bottom+4+lane*16;draw.rectangle((x(markers[a]),ya,x(markers[b]),ya+13),fill=c)
        if x(markers[b])-x(markers[a])>90:draw.text(((x(markers[a])+x(markers[b]))/2-30,ya-1),name,fill='#183047',font=font(12))
    detail=f"First STROBE {item['first_strobe_ms']:.3f} ms; SD init {item['SD_init_ms']:.3f} ms; transport {item['slot_transport_ms']:.3f} ms."
    if item['group']=='autostop':detail+=f" Exposure envelopes {item['external_exposure_envelopes']}; FRAME to FSM2 observation {item['frame_to_standby_observation_ms']:.3f} ms."
    draw.text((65,bottom+68),detail,fill='#566b7e',font=font(19))
draw.text((65,height-60),'Axes: mA and ms. Energy/time differences include variable SD latency; candidate03 wrote much faster.',fill='#263c50',font=font(20))
draw.text((65,height-29),'Marker11 observes sensor standby; low plateau and phase markers alone do not prove saved-image integrity or fresh Standby flags.',fill='#566b7e',font=font(18))
im.save(HERE/'cold-promotion-current.png');print(HERE/'cold-promotion-current.png')
