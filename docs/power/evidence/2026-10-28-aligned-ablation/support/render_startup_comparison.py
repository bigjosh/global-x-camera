"""Render the saved startup range comparison; all numeric values remain observations."""
import csv,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
BASE=Path(__file__).resolve().parent
rs=json.loads((BASE/'startup-range-comparison.json').read_text())
with (BASE/'startup-range-profile-10us.csv').open() as f:rows=list(csv.DictReader(f))
def font(n,bold=False):return ImageFont.truetype('C:/Windows/Fonts/'+('arialbd.ttf' if bold else 'arial.ttf'),n)
W,H=1450,1000;im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im);left,right=110,1370
colors={'fixed10a01':'#7c3aed','auto01':'#059669'}
d.text((65,30),'Startup transient repeats with the current range held fixed',font=font(28,True),fill='#17243b')
d.text((65,77),'10 microsecond means, aligned to the first current sample at or above 20 mA.',font=font(19),fill='#42536b')
for i,(name,c) in enumerate(colors.items()):
    d.line((110+i*270,120,140+i*270,120),fill=c,width=4);d.text((150+i*270,107),'Fixed 10 A' if name.startswith('fixed') else 'Automatic range',font=font(20),fill='#17243b')
for k,(field,label,lo,hi,ticks) in enumerate([('current_mean_A','Measured current (A)',-1,9,[-1,0,2,4,6,8]),('voltage_mean_V','JS input voltage (V)',1,6,[1,2,3,4,5,6])]):
    top=185+k*335;bottom=top+230
    xx=lambda t:left+t/300*(right-left)
    yy=lambda v:bottom-(v-lo)/(hi-lo)*(bottom-top)
    d.text((left,top-33),label,font=font(21,True),fill='#17243b')
    for val in ticks:
        y=yy(val);d.line((left,y,right,y),fill='#e1e5eb',width=1);d.text((left-45,y-10),str(val),font=font(17),fill='#536177')
    for t in range(0,301,50):
        x=xx(t);d.line((x,top,x,bottom),fill='#e1e5eb');d.text((x-13,bottom+9),str(t),font=font(17),fill='#536177')
    for name,color in colors.items():
        ps=[(xx(float(p['time_us'])),yy(float(p[field]))) for p in rows if p['run']==name and 0<=float(p['time_us'])<=300]
        d.line(ps,fill=color,width=3)
    first=next(r for r in rs if r['run']=='auto01')['range_transitions_minus1_to_plus10ms'][1]['time_from_onset_us']
    x=xx(first)
    for y in range(top,bottom,10):d.line((x,y,x,min(y+5,bottom)),fill='#e11d48',width=2)
    if k==0:d.text((x+10,top+7),'First auto range change: 128.5 us',font=font(18),fill='#b91c1c')
    d.text((570,bottom+38),'microseconds from current onset',font=font(18),fill='#536177')
d.text((65,865),'First 100 us mean: fixed 5.878 A / auto 5.885 A. First 5 ms charge: 0.934 / 0.945 mC.',font=font(20,True),fill='#17243b')
d.text((65,905),'The peak precedes autoranging, but both runs share the OFF-to-ON transition and measurement startup.',font=font(18),fill='#42536b')
d.text((65,939),'These traces do not independently qualify physical inrush, clipping or target-rail droop. Input voltage is source-side.',font=font(18),fill='#42536b')
im.save(BASE/'startup-fixed-vs-auto.png')
text=['STARTUP RANGE COMPARISON — saved observations only','Both runs completed ten expected phase markers; all raw stream hashes and sample-ID continuity passed.','The final range chunk is excluded because the original uint4 valid tail is not independently known.','']
for r in rs:
    q=r['first5ms_raw'];p=r['first5ms_native_peak_unqualified']
    text.append(f"{r['run']}: peak {p['current_A']:.6f} A at {p['time_us']:.1f} us, range code {p['raw_range_code']}; first5ms charge {q['charge_mC']:.6f} mC, raw energy {q['energy_mJ']:.6f} mJ; negative charge {q['negative_charge_mC']:.6f} mC.")
text += ['', 'Fixed10A stayed on raw range code0 throughout the first5ms. Auto first changed from code0 to code1 at128.5us, well after its35.5us peak. The first peak therefore cannot be explained solely by subsequent autoranging.', 'No additional boot is inferred from restoring fixed range1 to auto128; neither setting is OFF.', 'Both retain negative-current and source-voltage extrema. A common switch-on/measurement response is not ruled out. Physical inrush and clipping remain unqualified; whole-cycle qualification is not claimed.']
(BASE/'startup-comparison-report.txt').write_text('\n'.join(text)+'\n')
print('Startup figure and report rendered')
