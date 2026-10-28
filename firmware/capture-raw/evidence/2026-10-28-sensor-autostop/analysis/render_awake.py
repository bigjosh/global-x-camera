"""Offline figure using the prior gap campaign's installed Pillow runtime."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
HERE=Path(__file__).resolve().parent
def font(size,bold=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),size)
names=['ram-control']+[name for name in ('ram-auto01','ram-auto02') if (HERE/(name+'-awake-analysis.json')).exists()]
colors=['#c45b39','#147d92','#4d6ed1']
reports={name:json.loads((HERE/(name+'-awake-analysis.json')).read_text()) for name in names}
height=980+45*(len(names)-2);im=Image.new('RGB',(1600,height),'white');draw=ImageDraw.Draw(im)
draw.text((65,25),'One-frame automatic stop removes the long post-capture tail',fill='#183047',font=font(34,True))
draw.text((65,78),'Warm RAM captures | 1 ms current means | aligned at the first complete-frame interrupt',fill='#566b7e',font=font(22))
draw.text((65,110),'Tradeoff: ~0.324 ms of extra pre-START setup/readback; first STROBE ~0.387 ms later from warm runtime start.',fill='#566b7e',font=font(18))
left,right,top,bottom=105,1515,180,665
x=lambda t:left+(right-left)*(t+25)/100
y=lambda current:bottom-(bottom-top)*current/225
draw.rectangle((x(3),top,x(35),bottom),fill='#edf4e9')
for t in range(-20,76,10):
    draw.line((x(t),top,x(t),bottom),fill='#e2e8ed');draw.text((x(t)-14,bottom+10),str(t),fill='#566b7e',font=font(18))
for current in range(0,201,50):
    draw.line((left,y(current),right,y(current)),fill='#dce4eb');draw.text((left-55,y(current)-12),str(current),fill='#566b7e',font=font(18))
draw.text((65,136),'Whole-board 5 V input current (mA)',fill='#183047',font=font(22))
draw.text((520,bottom+43),'Time from first complete-frame interrupt (ms)',fill='#183047',font=font(22))
draw.line((x(0),top,x(0),bottom),fill='#8a969f')
for i,(name,r) in enumerate(reports.items()):
    color=colors[i];profile=json.loads((HERE/(name+'-awake-profile.json')).read_text())
    frame=r['mapped_proof_events']['frame_done']['time_ms'];m={q['id']:q for q in r['markers']}
    relative=lambda ident:(m[ident]['sample_id']-m[3]['sample_id'])/2000
    points=[(q['time_ms']-frame,q['current_mA']) for q in profile if -25<=q['time_ms']-frame<=75]
    assert all(0<=current<=225 for _,current in points),'Do not clip current data'
    draw.line([(x(t),y(current)) for t,current in points],fill=color,width=3)
    stop=r['windows_overlapping_not_additive']['frame_IRQ_to_sensor_stop_observation']['duration_ms']
    for yy in range(top,bottom,12):draw.line((x(stop),yy,x(stop),min(yy+6,bottom)),fill=color,width=2)
    label='Normal: explicit STOP' if i==0 else f'Auto-stop run {i}: one exposure observed'
    legend_x=700 if i==0 else 850;legend_y=135 if i==0 else 590+(i-1)*30
    draw.line((legend_x,legend_y+12,legend_x+30,legend_y+12),fill=color,width=4)
    draw.text((legend_x+42,legend_y),label,fill=color,font=font(18))
    row=790+45*i
    draw.text((65,row-3),'Normal' if i==0 else 'Auto '+str(i),fill=color,font=font(19,True))
    bx=lambda t:300+(right-300)*(t+25)/100
    draw.rectangle((bx(relative(2)),row,bx(stop),row+17),fill=color)
    draw.text((bx(stop)+8,row-3),f'{stop:.3f} ms after FRAME',fill=color,font=font(17))
draw.text((x(36.0815)+8,top+25),'Normal STOP acknowledged',fill=colors[0],font=font(20,True))
draw.text((x(3)+12,top+55),'Auto standby observed 2.73–2.78 ms after FRAME',fill=colors[1],font=font(20,True))
draw.text((65,750),'Bars: first STROBE interrupt to sensor STOP / standby observation',fill='#183047',font=font(21))
draw.text((65,height-95),'Shaded +3 to +35 ms window: 128.78 → 75.00 mA (two-repeat mean); 8.53 mJ less over the same 32 ms.',fill='#183047',font=font(21))
draw.text((65,height-57),'Whole-board effect, not isolated sensor power. Card behavior is not controlled. STOP/FSM2 are software observations.',fill='#566b7e',font=font(19))
im.save(HERE/'warm-tail-comparison.png');print(HERE/'warm-tail-comparison.png')
