"""Offline component locators from ST C02 assembly vectors; no bench access."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'tmp/hardware-review/nucleo-modifications/python-deps'))
import pymupdf
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
SRC=ROOT/'docs/prototype/nucleo-assembly/mb1940-c02-assembly.pdf'
DOC=pymupdf.open(SRC)
INK,RED,BLUE='#203040','#c32642','#176bad'
plt.rcParams.update({'font.family':'DejaVu Sans','text.color':INK})

PARTS={
 'C14':dict(page=0,side='TOP',center_mm=[20.0660,111.2796],rotation=90,
   body=[278.9804992675781,214.1500244140625,295.9270324707031,246.2298583984375],
   value='220 µF input bulk capacitor',package='1206',
   mfr='Murata GRM31CR60J227ME11',
   crop=[215,165,350,280],ground=[287.454,217.0],supply=[287.454,243.4],
   ground_pin=2,supply_pin=1,
   description='Between the removed D2 and R23 sites.\nDo not confuse it with C2 above D2.\nChanging C14 requires startup/shutdown qualification.'),
 'C17':dict(page=1,side='UNDERSIDE',center_mm=[16.4084,23.2918],rotation=180,
   body=[586.7658081054688,1053.76171875,607.4786376953125,1066.9688720703125],
   value='10 µF former U42 input capacitor',package='0805',
   mfr='Yageo CC0805KRX5R8BB106',
   crop=[535,965,655,1100],ground=[589.12,1060.365],supply=[605.124,1060.365],
   ground_pin=1,supply_pin=2,
   description='Directly below the removed U42 footprint.\nC155 beside U42 is its output capacitor; leave it alone.\nC17 is still connected to 5 V after U42 removal.')
}

def assembly(ax,page,clip,scale):
    r=pymupdf.Rect(clip);p=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=r,alpha=False)
    a=np.frombuffer(p.samples,np.uint8).reshape(p.height,p.width,3)
    ax.imshow(a,extent=(r.x0,r.x1,r.y1,r.y0));ax.set_xlim(r.x0,r.x1);ax.set_ylim(r.y1,r.y0)
    ax.set_aspect('equal');ax.axis('off')

for name,part in PARTS.items():
    page=DOC[part['page']];b=part['body'];center=[(b[0]+b[2])/2,(b[1]+b[3])/2]
    fig=plt.figure(figsize=(12,9.3),facecolor='white')
    fig.text(.035,.956,f'{name}: {part["value"]}',fontsize=22,weight='bold')
    fig.text(.035,.920,f'{part["side"]} VIEW  |  ST-LINK USB end at the top.'+
             ('  Flip the board left-to-right.' if part['page'] else ''),fontsize=11)
    ax=fig.add_axes([.035,.11,.40,.76]);assembly(ax,page,[78,5,765,1300],1.6)
    ax.set_title('Locate this area',fontsize=12,pad=8)
    ax.add_patch(Rectangle((b[0]-18,b[1]-18),b[2]-b[0]+36,b[3]-b[1]+36,fill=False,ec=RED,lw=2.2))
    label=(center[0]+130,center[1]-60) if part['page']==0 else (center[0]-150,center[1]-60)
    ax.annotate(name,xy=center,xytext=label,color=RED,fontsize=14,weight='bold',arrowprops={'arrowstyle':'->','color':RED,'lw':1.8})
    ax.text(420,75,'ST-LINK / debugger end',ha='center',fontsize=9,color=BLUE,bbox={'facecolor':'white','edgecolor':'none','pad':3})
    ax.text(420,1258,'Camera / target-USB end',ha='center',fontsize=9,color=BLUE,bbox={'facecolor':'white','edgecolor':'none','pad':3})
    zoom=fig.add_axes([.49,.355,.475,.47]);assembly(zoom,page,part['crop'],4)
    zoom.set_title(f'{name} / {part["package"]}  •  location only',fontsize=15,weight='bold',pad=15)
    zoom.add_patch(Rectangle((b[0]-1.5,b[1]-1.5),b[2]-b[0]+3,b[3]-b[1]+3,fill=False,ec=RED,lw=2.4))
    if name=='C14':
        zoom.annotate('GND / pin 2',xy=part['ground'],xytext=(329,204),color=BLUE,fontsize=9,ha='center',arrowprops={'arrowstyle':'->','color':BLUE})
        zoom.annotate('5 V / pin 1',xy=part['supply'],xytext=(312,267),color=BLUE,fontsize=10,ha='center',arrowprops={'arrowstyle':'->','color':BLUE})
    else:
        zoom.annotate('GND / pin 1',xy=part['ground'],xytext=(554,1087),color=BLUE,fontsize=10,ha='center',arrowprops={'arrowstyle':'->','color':BLUE})
        zoom.annotate('5 V / pin 2',xy=part['supply'],xytext=(631,1087),color=BLUE,fontsize=10,ha='center',arrowprops={'arrowstyle':'->','color':BLUE})
    fig.text(.49,.272,part['description'],fontsize=11.5,va='top',linespacing=1.65)
    fig.text(.49,.16,'Both parts are non-polar ceramic capacitors.\nLabels identify PCB pads, not capacitor polarity.',fontsize=10.5,va='top',linespacing=1.5)
    fig.text(.035,.038,'Source: ST MB1940-N657X0Q-C02 assembly sheets 16–17, C02 BOM and ODB++ pin nets.\nResearch locator only; neither capacitor has been selected for removal or modified in this study.',fontsize=9,color='#536773',va='bottom')
    fig.savefig(HERE/(name.lower()+'-location.png'),dpi=160,facecolor='white')
    fig.savefig(HERE/(name.lower()+'-location.svg'),facecolor='white');plt.close(fig)

evidence=dict(source=str(SRC.relative_to(ROOT)),source_sha256=hashlib.sha256(SRC.read_bytes()).hexdigest(),
    orientation='Each face viewed directly, ST-LINK end at top; bottom is left-right flip of top.',
    parts=PARTS,
    odb_nets={'358':'GND','380':'target 5V'},
    pin_records={
      'C14':['TOP 0 0.79 4.3259669 180 N 380 36 C14-1','TOP 1 0.79 4.4362031 180 N 358 252 C14-2'],
      'C17':['TOP 0 0.6794646 0.917 270 N 358 128 C17-1','TOP 1 0.6125354 0.917 270 N 380 15 C17-2']},
    population='C02 BOM marks both fitted; generic pick/place alone is insufficient population proof.',
    limits='CAD locator, not a delivered-board photograph or authorization to remove parts.')
(HERE/'locations.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({name:str(HERE/(name.lower()+'-location.png')) for name in PARTS}))
