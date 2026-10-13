"""Create an independent, electrically equivalent human-readable schematic.

Reads the recovered KiCad files, preserving symbol pin identities and component
properties. Only this script's sibling output directory is written.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import uuid
from collections import defaultdict
from kicad_sexpr import Atom as A, child, children, dumps, parse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'hardware/kicad'
OUT = ROOT / 'hardware/kicad-readable'
PROJECT = 'global-x-camera-readable'
NS = uuid.UUID('925dba91-f425-48a4-b761-7e8ce873cc6e')
uid = lambda s: str(uuid.uuid5(NS, str(s)))
Q = lambda s: json.dumps(str(s), ensure_ascii=False)
S = parse
snap = lambda n: round(round(float(n)/1.27)*1.27, 4)
xy = lambda p: tuple(snap(v) for v in p)
ROOT_ID = uid('root')
CIRCUIT = json.loads((ROOT/'hardware/reconstruction/schematic-connectivity.json').read_text())['components']
INST = {}
LIB = {}
BASE_HASH = {}
for f in SRC.glob('*.kicad_sch'):
    BASE_HASH[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    t = parse(f.read_text(encoding='utf8'))
    for lib in children(child(t, 'lib_symbols'), 'symbol'):
        LIB[lib[1]] = copy.deepcopy(lib)
    for inst in children(t, 'symbol'):
        ref = next(p[2] for p in children(inst, 'property') if p[1]=='Reference')
        INST[ref, int(child(inst,'unit')[1])] = copy.deepcopy(inst)

def pins(ref, unit=1):
    return [p for g in children(LIB['GX:'+ref], 'symbol')
            if re.search(r'_(?:0|'+str(unit)+r')_[01]$',g[1])
            for p in children(g,'pin')]

def pnum(p): return str(child(p,'number')[1])
def net(ref,p): return CIRCUIT[ref]['pins'][str(p)]['net']
def bynet(ref,unit=1):
    d=defaultdict(list)
    for p in pins(ref,unit): d[net(ref,pnum(p))].append(pnum(p))
    return d

PAGES=[]
PLACED=set()

class Page:
    def __init__(self,name,title,subtitle):
        self.name=f'{len(PAGES)+2:02d}_{name}'
        self.title=title; self.num=len(PAGES)+2
        self.id=uid(self.name);self.sid=uid(self.name+':sheet')
        self.items=[];self.usedlibs=set();self.pts={};self.done=set();self.placed=[]
        self.seq=0;self.junc=set();self.wires=[]
        self.text(title,12.7,15.24,2.54)
        self.text(subtitle,12.7,22.86,1.27)
        PAGES.append(self)
    def u(self):
        self.seq+=1;return Q(uid(self.name+':'+str(self.seq)))
    def text(self,s,x,y,size=1.27):
        x,y=xy((x,y))
        self.items.append(S(f'(text {Q(s)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {self.u()}))'))
    def wire(self,*points,bus=False):
        points=[xy(p) for p in points]
        for a,b in zip(points,points[1:]):
            if a==b:continue
            self.items.append(S(f'({"bus" if bus else "wire"} (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid {self.u()}))'))
            if not bus:self.wires.append((a,b))
    def dot(self,p):
        p=xy(p)
        if p in self.junc:return
        self.junc.add(p)
        self.items.append(S(f'(junction (at {p[0]} {p[1]}) (diameter 0) (color 0 0 0 0) (uuid {self.u()}))'))
    def label(self,n,p,glob=False,side='right'):
        p=xy(p)
        # Retain the original global net names, including on bus member wires.
        if not n.startswith('{'):glob=True
        if glob:
            angle=0 if side=='right' else 180
            self.items.append(S(f'(global_label {Q(n)} (shape passive) (at {p[0]} {p[1]} {angle}) (effects (font (size 1.016 1.016)) (justify {"left" if side=="right" else "right"})) (uuid {self.u()}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {p[0]} {p[1]} 0) (effects (font (size 1.016 1.016)) (hide yes))))'))
        else:
            self.items.append(S(f'(label {Q(n)} (at {p[0]} {p[1]} 0) (effects (font (size 1.016 1.016)) (justify left bottom)) (uuid {self.u()}))'))
    def instance(self,ref,unit,x,y,angle=0,bounds=None):
        assert (ref,unit) not in PLACED,(ref,unit)
        PLACED.add((ref,unit));self.placed.append((ref,unit));self.usedlibs.add('GX:'+ref)
        x,y=xy((x,y));inst=copy.deepcopy(INST[ref,unit])
        child(inst,'at')[1:]=[x,y,angle]
        child(inst,'uuid')[1]=uid(f'{self.name}:{ref}:{unit}')
        child(inst,'instances')[1:]=[S(f'(project {Q(PROJECT)} (path {Q("/"+ROOT_ID+"/"+self.sid)} (reference {Q(ref)}) (unit {unit})))')]
        for p in children(inst,'property'):
            if p[1] in ['Reference','Value']:
                if bounds:
                    px=(bounds[0]+bounds[2])/2;py=bounds[1]-(7.62 if p[1]=='Reference' else 3.81)
                elif angle in (90,270):px=x+(12.7 if angle==90 else 3.81);py=y+(-1.27 if p[1]=='Reference' else 1.27)
                else:px=x;py=y+(-6.35 if p[1]=='Reference' else -3.81)
                child(p,'at')[1:]=[snap(px),snap(py),90 if angle in (90,270) else 0]
                e=child(p,'effects');e[1:]=S(f'(effects (font (size 1.27 1.27)) {"(justify left)" if not bounds and angle==270 else ""})')[1:]
            else:child(p,'at')[1:]=[x,y,0]
        self.items.append(inst)
        a=math.radians(angle)
        for p in pins(ref,unit):
            at=child(p,'at');dx,dy=float(at[1]),float(at[2])
            self.pts[ref,pnum(p)]=xy((x+dx*math.cos(a)-dy*math.sin(a),y-dx*math.sin(a)-dy*math.cos(a)))
    def part(self,ref,x,y,vertical=False):self.instance(ref,1,x,y,270 if vertical else 0)
    def block(self,ref,unit,lx,rx,rows,title=''):
        """Rows map physical pin numbers to (side, absolute page y)."""
        assert set(rows)==set(pnum(p) for p in pins(ref,unit)),(ref,unit,set(rows)^set(pnum(p) for p in pins(ref,unit)))
        lx,rx=snap(lx),snap(rx);top=snap(min(y for _,y in rows.values())-5.08);bottom=snap(max(y for _,y in rows.values())+5.08)
        cx=snap((lx+rx)/2);cy=snap((top+bottom)/2)
        lib=LIB['GX:'+ref]
        oldpins=copy.deepcopy(pins(ref,unit))
        lib[:]=[a for a in lib if not(isinstance(a,list) and a[0]=='symbol' and re.search(r'_'+str(unit)+r'_[01]$',a[1]))]
        g=[A('symbol'),f'{ref}_{unit}_1',S(f'(rectangle (start {lx+5.08-cx} {cy-top}) (end {rx-5.08-cx} {cy-bottom}) (stroke (width 0.254) (type default)) (fill (type background)))')]
        for p in oldpins:
            side,y=rows[pnum(p)];y=snap(y);px=lx if side=='L' else rx
            child(p,'at')[1:]=[snap(px-cx),snap(cy-y),0 if side=='L' else 180]
            child(p,'length')[1]=5.08
            for k in ['name','number']:
                child(child(p,k),'effects')[1:]=S('(effects (font (size 1.016 1.016)))')[1:]
            g.append(p)
        lib.append(g)
        self.instance(ref,unit,cx,cy,bounds=(lx,top,rx,bottom))
        if title:self.text(title,lx+6.35,bottom+5.08,1.016)
    def connect(self,n,keys,trunk=None):
        points=[self.pts[k] for k in keys]
        self.done.update(keys)
        if not points:return None
        if trunk is None:
            self.wire(*points);p=points[0]
        else:
            trunk=snap(trunk)
            for p in points:self.wire(p,(trunk,p[1]))
            ys=sorted(set(p[1] for p in points))
            self.wire(*[(trunk,y) for y in ys]);p=(trunk,ys[0])
            for y in ys:self.dot((trunk,y))
        self.label(n,p,True)
        return p
    def rail(self,n,keys,x,caps=(),capx=None):
        p=self.connect(n,keys,x)
        if caps:
            self.bank(caps,capx or x+17.78,p[1],anchor=p)
        return p
    def bank(self,refs,x,y,anchor=None,spacing=22.86):
        top=xy((x,y));bottom=xy((x,y+20.32));firstnet=net(refs[0],'1');other=net(refs[0],'2')
        assert all(net(r,'1')==firstnet and net(r,'2')==other for r in refs)
        for i,r in enumerate(refs):
            cx=snap(x+i*spacing);self.part(r,cx,y+10.16,True)
            a=self.pts[r,'1'];b=self.pts[r,'2']
            self.wire((cx,y),a);self.wire(b,(cx,y+20.32));self.done.update([(r,'1'),(r,'2')])
            if i:self.wire((cx-spacing,y),(cx,y));self.wire((cx-spacing,y+20.32),(cx,y+20.32))
            self.dot((cx,y));self.dot((cx,y+20.32))
        if anchor:self.wire(anchor,top)
        self.label(firstnet,top,True)
        self.label(other,bottom,True)
        return top,bottom
    def branch(self,ref,anchor,pin='1',x=None,down=True):
        """One two-terminal support part directly connected to an existing wire."""
        anchor=xy(anchor);x=snap(x if x is not None else anchor[0]+12.7)
        wanted=net(ref,pin)
        cy=anchor[1]+(10.16 if down else -10.16)
        angle=270 if (pin=='1')==down else 90
        self.instance(ref,1,x,cy,angle)
        a=self.pts[ref,pin];other=next(p for r,p in self.pts if r==ref and p!=pin)
        b=self.pts[ref,other]
        # Approach the selected terminal from its own side, avoiding the body.
        ay=a[1]-(3.81 if a[1]<cy else -3.81)
        self.wire(anchor,(x,anchor[1]),(x,ay),a)
        by=b[1]-(3.81 if b[1]<cy else -3.81)
        self.wire(b,(x,by));self.label(net(ref,other),(x,by),True)
        self.done.update([(ref,pin),(ref,other)]);self.dot(anchor)
    def tap(self,ref,anchor,x=None):
        a=xy(anchor);x=snap(x if x is not None else a[0]);self.part(ref,x,a[1]-10.16)
        self.wire(a,(x,a[1]),self.pts[ref,'1']);self.dot(a);self.done.add((ref,'1'))
    def bundle(self,name,nets,left,right):
        """Real KiCad named bus with labelled member wires at both ends."""
        self.items.append([A('bus_alias'),name,[A('members'),*nets]])
        lx=snap(left+30.48);rx=snap(right-50.8)
        ys=[]
        for n in nets:
            ends=[k for k,p in self.pts.items() if net(*k)==n and k not in self.done]
            for k in ends:
                p=self.pts[k];isleft=p[0]<(left+right)/2;bx=lx if isleft else rx
                wx=bx-2.54 if isleft else bx+2.54
                self.wire(p,(wx,p[1]));self.label(n,(min(p[0],wx)+1.27,p[1]))
                self.items.append(S(f'(bus_entry (at {wx} {p[1]}) (size {2.54 if isleft else -2.54} 2.54) (stroke (width 0) (type default)) (uuid {self.u()}))'))
                ys.append(p[1]+2.54);self.done.add(k)
        ytop=min(ys)-7.62
        for bx in [lx,rx]:self.wire((bx,ytop),(bx,max(ys)),bus=True)
        self.wire((lx,ytop),(rx,ytop),bus=True);self.label('{'+name+'}',(lx,ytop))
    def finish(self):
        for k,p in self.pts.items():
            if k in self.done:continue
            n=net(*k)
            if n is None:
                self.items.append(S(f'(no_connect (at {p[0]} {p[1]}) (uuid {self.u()}))'))
            else:
                # Unrouted pins are only power / explicitly off-sheet functions.
                ref,pn=k;pp=next(a for _,u in self.placed if _==ref for a in pins(ref,u) if pnum(a)==pn)
                angle=float(child(pp,'at')[3]);sign=-1 if angle==0 else 1
                q=xy((p[0]+sign*7.62,p[1]));self.wire(p,q);self.label(n,q,True,'right' if sign>0 else 'left')
    def tree(self):
        t=S(f'(kicad_sch (version 20250114) (generator "global_x_readable") (uuid {Q(self.id)}) (paper "A3") (title_block (title {Q(self.title)}) (date "2026-09-05") (rev "A-readable") (company "Global X Camera") (comment 1 "Presentation revision; electrical design review remains pending")))')
        t.append([A('lib_symbols'),*[copy.deepcopy(LIB[k]) for k in sorted(self.usedlibs)]])
        t.extend(self.items);t.append(S('(embedded_fonts no)'));return t

def rows_for(ref,unit,groups,side='R',start=45.72,gap=15.24):
    """Return grouped pins, with enough space between rail/support networks."""
    d=bynet(ref,unit);rows={};y=start
    for n in groups:
        for pn in d.pop(n,[]):rows[pn]=(side,y);y+=3.81
        y+=gap
    for n,ps in d.items():
        for pn in ps:rows[pn]=(side,y);y+=3.81
        y+=gap if n else 0
    return rows

def interface(name,title,unit,target,groups,extras=(),subtitle=''):
    p=Page(name,title,subtitle or 'Direct signal paths, grouped interfaces and adjacent support components.')
    a=bynet('U1',unit);b=bynet(target);ra={};rb={};y=48.26;netys={}
    for label,ns,bus in groups:
        p.text(label,139.7,y-10.16,1.524)
        for n in ns:
            if n in ['BOOT_XSPI_NCS','NAND_NCE','NAND_RNB','NAND_NWP']:y+=20.32
            netys[n]=y
            for pn in a.pop(n,[]):ra[pn]=('R',y)
            for pn in b.pop(n,[]):rb[pn]=('L',y)
            y+=5.08
        y+=22.86
    # Remaining MCU support signals are spaced for direct R/C branches.
    for n,ps in a.items():
        for pn in ps:ra[pn]=('R',y);y+=25.4
    by=48.26
    b=dict(sorted(b.items(),key=lambda item:(item[0] is None, item[0]=='GND', item[0] or '')))
    for n,ps in b.items():
        for pn in ps:rb[pn]=('R',by);by+=3.81
        by+=22.86 if n else 0
    if target=='U6':
        for n,start in [('3V3',48.26),('GND',124.46),('NAND_PT',157.48),(None,185.42)]:
            for i,pn in enumerate(b[n]):rb[pn]=('R',start+i*(2.54 if n is None else 3.81))
    p.block('U1',unit,30.48,111.76,ra,'MCU '+name.replace('_',' '))
    p.block(target,1,279.4,355.6,rb)
    for label,ns,bus in groups:
        if bus:p.bundle(bus,ns,111.76,279.4)
        else:
            for n in ns:
                keys=[k for k in p.pts if net(*k)==n]
                pts=sorted((p.pts[k] for k in keys))
                p.wire(*pts);p.label(n,(120.65,pts[0][1]));p.done.update(keys)
    for n,ps in b.items():
        if n:p.rail(n,[(target,pn) for pn in ps],363.22)
    return p,netys

def railpage():
    p=Page('main_power','Main regulated rails','Power flows left to right. Each converter is drawn with its input, output and control network.')
    def converter(ref,lref,top,ins,outs,incaps,outcaps,pg,pgres,extra):
        d=bynet(ref);rows={};ly=top;ry=top
        for n in ins:
            for pn in d.pop(n,[]):rows[pn]=('L',ly);ly+=3.81
            ly+=22.86
        for n in outs:
            for pn in d.pop(n,[]):rows[pn]=('R',ry);ry+=3.81
            ry+=22.86
        for n,ps in d.items():
            for pn in ps:rows[pn]=('L',ly);ly+=3.81
            ly+=20.32
        p.block(ref,1,142.24,218.44,rows)
        for n in ins:
            keys=[(ref,pn) for pn in bynet(ref)[n]]
            a=p.connect(n,keys,132.08)
            if n in incaps:p.bank(incaps[n],48.26,a[1],anchor=a)
        sw=net(lref,'1');a=p.connect(sw,[(ref,pn) for pn in bynet(ref)[sw]],228.6)
        p.part(lref,251.46,a[1]);p.wire(a,p.pts[lref,'1']);p.done.add((lref,'1'))
        o=net(lref,'2');out=(274.32,a[1]);p.wire(p.pts[lref,'2'],out);p.done.add((lref,'2'));p.label(o,out,True)
        p.bank(outcaps,294.64,a[1],anchor=out)
        if o in bynet(ref):
            for pn in bynet(ref)[o]:
                q=p.pts[ref,pn];p.wire(q,(274.32,q[1]),out);p.done.add((ref,pn));p.dot(out)
        a=p.connect(pg,[(ref,pn) for pn in bynet(ref)[pg]],228.6)
        p.branch(pgres,a,pin='2',x=246.38,down=False)
        for n,rs in extra:
            keys=[(ref,pn) for pn in bynet(ref)[n]];a=p.connect(n,keys,132.08 if rows[keys[0][1]][0]=='L' else 228.6)
            for i,r in enumerate(rs):
                pn=next(pn for pn,v in CIRCUIT[r]['pins'].items() if v['net']==n)
                outward=-1 if rows[keys[0][1]][0]=='L' else 1
                p.branch(r,a,pn,x=365.76 if r=='C12' else a[0]+outward*(i+1)*22.86,down=pn=='1')
    converter('U2','L1',43.18,['SYS_IN','GND'],['BUCK3V3_SW','3V3','PG_3V3'],{'SYS_IN':['C1','C2']},['C3','C4','C5','C6','C7'],'PG_3V3','R4',[('BUCK3V3_SS',['C8'])])
    converter('U7','L2',180.34,['3V3','GND'],['BUCK1V8_SW','BUCK1V8_FB','PG_1V8'],{'3V3':['C9']},['C10','C11'],'PG_1V8','R7',[('BUCK1V8_FB',['R5','R6','C12'])])

def powerpages():
    p=Page('mcu_io_power','MCU I/O and analog supplies','Supply balls are grouped by rail; bypass capacitors connect directly to the adjacent rail trunk.')
    d=bynet('U1',1);order=['3V3','1V8','3V3_USB','VCORE_0V81'];rows={};starts=[43.18,124.46,205.74,238.76]
    for n,y in zip(order,starts):
        for pn in d[n]:rows[pn]=('R',y);y+=3.81
    p.block('U1',1,25.4,116.84,rows,'MCU supplies (every supply ball retained)')
    capgroups={'3V3':[f'C{i}' for i in list(range(20,26))+list(range(44,50))], '1V8':[f'C{i}' for i in list(range(26,36))+[60,61]]}
    for n in order:
        a=p.connect(n,[('U1',pn) for pn in d[n]],129.54)
        cs=capgroups.get(n,[])
        for offset in range(0,len(cs),8):
            yy=a[1]+(offset//8)*35.56
            if offset:p.wire(a,(129.54,yy))
            p.bank(cs[offset:offset+8],152.4,yy,anchor=(129.54,yy),spacing=29.21)
    p.text('USB supply decoupling: USB page. CSI supply uses the existing core rail connection.',152.4,223.52)
    p=Page('mcu_core','MCU internal SMPS and core supply','Core rail bypassing and switch-node components are shown beside the MCU power unit.')
    d=bynet('U1',2);order=['VCORE_0V81','1V8','MCU_SMPS_SW','V08CAP'];rows={};starts=[43.18,132.08,185.42,238.76]
    for n,y in zip(order,starts):
        for pn in d[n]:rows[pn]=('R',y);y+=3.81
    p.block('U1',2,25.4,116.84,rows,'MCU internal SMPS')
    anchors={n:p.connect(n,[('U1',pn) for pn in d[n]],129.54) for n in order}
    caps=[f'C{i}' for i in range(15,19)]+['C69']+[f'C{i}' for i in range(50,59)]
    for offset in range(0,len(caps),7):
        yy=43.18+(offset//7)*35.56;p.wire(anchors['VCORE_0V81'],(139.7,43.18),(139.7,yy))
        p.bank(caps[offset:offset+7],157.48,yy,anchor=(139.7,yy),spacing=31.75)
    a=anchors['MCU_SMPS_SW'];p.part('L3',172.72,a[1]);p.wire(a,p.pts['L3','1']);p.done.update([('L3','1'),('L3','2')])
    p.wire(p.pts['L3','2'],(393.7,a[1]),(393.7,43.18),(347.98,43.18));p.dot((347.98,43.18))
    p.part('C59',213.36,213.36,True);p.part('R19',213.36,243.84,True)
    p.wire((147.32,a[1]),(147.32,200.66),(213.36,200.66),p.pts['C59','1']);p.dot((147.32,a[1]))
    p.wire(p.pts['C59','2'],p.pts['R19','1'])
    p.label('MCU_SMPS_SNUBBER',(213.36,226.06));p.wire(p.pts['R19','2'],(213.36,259.08));p.label('GND',(213.36,259.08),True)
    p.done.update([('C59','1'),('C59','2'),('R19','1'),('R19','2')])
    p.bank(['C19'],157.48,238.76,anchor=anchors['V08CAP'])

def memorypages():
    ns=['BOOT_XSPI_IO'+str(i) for i in range(4)]
    p,ys=interface('boot_flash','Boot NOR flash',5,'U5',[('Quad-SPI data',ns,'BOOT_QSPI'),('Clock and select',['BOOT_XSPI_CLK','BOOT_XSPI_NCS'],None)])
    p.branch('R13',(248.92,ys['BOOT_XSPI_NCS']),'2',down=False)
    a=p.pts['U5','8'];p.bank(['C39'],381,a[1],anchor=(363.22,a[1]))
    ns=['NAND_D'+str(i) for i in range(8)]
    control=['NAND_CLE','NAND_ALE','NAND_NWE','NAND_NOE','NAND_NCE','NAND_RNB','NAND_NWP']
    p,ys=interface('nand','Raw NAND storage',6,'U6',[('8-bit data',ns,'NAND_DATA'),('FMC control',control,None)])
    # Bias parts at alternating positions, directly on their control wires.
    for ref,n,x in [('R15','NAND_NCE',190.5),('R14','NAND_RNB',218.44),('R16','NAND_NWP',246.38)]:
        pn=next(pn for pn,v in CIRCUIT[ref]['pins'].items() if v['net']==n)
        p.branch(ref,(x,ys[n]),pn,x=x,down=pn=='1')
    a=p.pts['U6','38'];p.branch('R27',(363.22,a[1]),'1',x=381)
    v=p.pts['U6','12'];p.bank(['C40','C41'],375.92,v[1],anchor=(363.22,v[1]),spacing=17.78)
    p.bank(['C42','C71'],375.92,v[1]+35.56,anchor=(363.22,v[1]+35.56),spacing=17.78)
    p.wire((363.22,v[1]),(363.22,v[1]+35.56))

def camerapages():
    p=Page('camera','Camera connector, module and CSI-2','One CSI-2 data lane plus clock. CAM1 represents the external module; J3 is the host-board receptacle.')
    order=['CAM_CSI_CLK_P','CAM_CSI_CLK_N','CAM_CSI_D0_P','CAM_CSI_D0_N','I2C4_SCL','I2C4_SDA','CAM_MCLK','CAM_XSHUTDOWN']
    ys=dict(zip(order,[48.26,53.34,60.96,66.04,101.6,106.68,142.24,175.26]))
    a=bynet('U1',7);rows={}
    for n,y in ys.items():
        for pn in a.pop(n,[]):rows[pn]=('R',y)
    for n,y in [('CSI_REXT',213.36),('CAM_AVDD_EN',246.38)]:
        for pn in a.pop(n,[]):rows[pn]=('R',y)
    p.block('U1',7,20.32,93.98,rows,'MCU camera interface')
    for ref,lx,rx in [('J3',228.6,264.16),('CAM1',325.12,388.62)]:
        d=bynet(ref);r={}
        for n,y in ys.items():
            for pn in d.pop(n,[]):r[pn]=('L',y)
        for n,y in [('CAM_VANA_2V8',195.58),('CAM_VCORE_1V2',220.98),('1V8',246.38)]:
            for pn in d.pop(n,[]):r[pn]=('L',y)
        yy=45.72
        for pn in d.pop('GND'):r[pn]=('R',yy);yy+=3.81
        yy=137.16
        for pn in d.pop(None,[]):r[pn]=('R',yy);yy+=3.81
        p.block(ref,1,lx,rx,r)
        p.connect('GND',[(ref,pn) for pn,info in CIRCUIT[ref]['pins'].items() if info['net']=='GND'],rx+6.35)
    # U1 and J3 use actual named functional buses; module leads remain explicit.
    camkeys={k for k in p.pts if k[0]=='CAM1'}
    camalready=p.done & camkeys
    p.done.update(camkeys)
    p.bundle('CAM_MIPI',[n for n in order if n.startswith('CAM_CSI')],93.98,228.6)
    p.bundle('CAM_I2C',['I2C4_SCL','I2C4_SDA'],93.98,228.6)
    p.done.difference_update(camkeys-camalready)
    for n in order:
        jp=next(p.pts[k] for k in p.pts if k[0]=='J3' and net(*k)==n)
        cp=next(p.pts[k] for k in p.pts if k[0]=='CAM1' and net(*k)==n)
        # Identical local labels show the mated connector contacts without wires crossing its body.
        p.wire(cp,(cp[0]-12.7,cp[1]));p.label(n,(cp[0]-12.7,cp[1]))
        p.done.update(k for k in p.pts if k[0]=='CAM1' and net(*k)==n)
        if n in ['CAM_MCLK','CAM_XSHUTDOWN']:
            up=next(p.pts[k] for k in p.pts if k[0]=='U1' and net(*k)==n)
            p.wire(up,jp);p.label(n,(up[0]+2.54,up[1]));p.done.update(k for k in p.pts if k[0] in ['U1','J3'] and net(*k)==n)
    # I2C pull-ups on the actual J3 member wires.
    for ref,n,x in [('R22','I2C4_SCL',195.58),('R23','I2C4_SDA',215.9)]:p.branch(ref,(x,ys[n]),'1',x=x,down=ref=='R23')
    p.branch('R20',(190.5,ys['CAM_XSHUTDOWN']),'1',x=190.5)
    p.branch('R17',p.pts['U1','P5'],'1',x=119.38)
    p.done.add(('U1','P5'));p.label('CSI_REXT',p.pts['U1','P5'])
    p.tap('TP13',(177.8,ys['CAM_MCLK']))
    # Adjacent host decoupling bank, connected directly to J3's VDDIO contact.
    p.bank(['C66','C70'],160.02,246.38,anchor=p.pts['J3','5'],spacing=27.94);p.done.add(('J3','5'))
    p.text('CAM_MIPI: differential clock and data lane 0',100.33,33.02,1.27)
    p.text('CAM_I2C: camera control',100.33,86.36,1.27)
    p=Page('camera_power','Camera power rails','Analog and core supplies, with their local input/output capacitors and enable bias.')
    for ref,top,inc,outc,inn,outn,tp in [('U9',55.88,'C62','C63','3V3','CAM_VANA_2V8','TP11'),('U10',170.18,'C64','C65','1V8','CAM_VCORE_1V2','TP12')]:
        d=bynet(ref);r={};ly=top;ry=top
        for n,ps in d.items():
            side='R' if n==outn or n is None else 'L';yy=ry if side=='R' else ly
            for pn in ps:r[pn]=(side,yy);yy+=3.81
            if side=='R':ry=yy+27.94
            else:ly=yy+27.94
        p.block(ref,1,157.48,238.76,r)
        for n,ps in d.items():
            if n is None:continue
            a=p.connect(n,[(ref,pn) for pn in ps],248.92 if n==outn else 144.78)
            if n==inn:p.bank([inc],109.22,a[1],anchor=a)
            if n==outn:p.bank([outc],289.56,a[1],anchor=a);p.tap(tp,(274.32,a[1]))
            if n=='CAM_AVDD_EN':p.branch('R21',a,'1',x=121.92)

def controlpage():
    p=Page('control','Clock, reset, boot and debug','Local oscillator and strap components are wired to the MCU. Optional SW2/SW3 remain DNP.')
    d=bynet('U1',4);r={};ys={'HSE_IN':45.72,'HSE_OUT':73.66,'BOOT0':114.3,'BOOT1':149.86,'NRST':190.5,'SWDIO':226.06,'SWCLK':231.14,'SWO':236.22,'1V8':251.46,'PWR_HOLD':104.14,'SHUTTER_SENSE':139.7,'STATUS_LED_K':175.26}
    for n,ps in d.items():
        for pn in ps:r[pn]=('L' if n in ['PWR_HOLD','SHUTTER_SENSE','STATUS_LED_K','1V8'] else 'R',ys[n])
    p.block('U1',4,66.04,157.48,r,'MCU system control')
    p.part('Y1',220.98,59.69)
    for n,pn,yp,x in [('HSE_IN','A7','1',208.28),('HSE_OUT','B7','3',236.22)]:
        a=p.pts['U1',pn];b=p.pts['Y1',yp]
        p.wire(a,(x,a[1]),(x,b[1]),b);p.label(n,(170.18,a[1]));p.done.update([('U1',pn),('Y1',yp)])
    g=p.pts['Y1','2'];p.wire(g,(g[0],83.82));p.label('GND',(g[0],83.82),True);p.done.update([('Y1','2'),('Y1','4')])
    p.branch('C36',(185.42,45.72),'1',x=185.42)
    p.branch('C37',(261.62,73.66),'1',x=261.62);p.wire((236.22,73.66),(261.62,73.66))
    for ref,n,pn in [('R8','BOOT0','G4'),('R9','BOOT1','P8'),('C38','NRST','G3')]:
        a=p.pts['U1',pn];p.wire(a,(208.28,a[1]));p.label(n,(165.1,a[1]));p.done.add(('U1',pn));p.branch(ref,(208.28,a[1]),'1',x=208.28)
    for ref,n,other,x in [('SW2','BOOT0','1V8',269.24),('SW3','NRST','GND',269.24)]:
        p.part(ref,x,ys[n]);p.wire((208.28,ys[n]),p.pts[ref,'1']);p.wire(p.pts[ref,'2'],(289.56,ys[n]));p.label(other,(289.56,ys[n]),True);p.done.update([(ref,'1'),(ref,'2')])
    p.tap('TP6',(238.76,ys['BOOT0']));p.tap('TP7',(238.76,ys['NRST']))
    jd=bynet('J2');jr={}
    for n,ps in jd.items():
        yy=ys.get(n,205.74 if n=='3V3' else 241.3)
        for pn in ps:jr[pn]=('L' if n in ['SWDIO','SWCLK','SWO','NRST'] else 'R',yy)
    p.block('J2',1,307.34,365.76,jr,'SWD header')
    for n in ['SWDIO','SWCLK','SWO']:
        keys=[k for k in p.pts if net(*k)==n];p.wire(*[p.pts[k] for k in keys]);p.label(n,(170.18,ys[n]));p.done.update(keys)
    # Reset header connection joins the reset net before the optional switch.
    a=p.pts['J2','5'];p.wire(a,(299.72,a[1]),(299.72,175.26),(226.06,175.26),(226.06,190.5));p.dot((226.06,190.5));p.done.add(('J2','5'))
    for i,(ref,n) in enumerate([('TP3','3V3'),('TP4','1V8'),('TP5','VCORE_0V81')]):
        p.part(ref,33.02,55.88+i*30.48);a=p.pts[ref,'1'];p.wire(a,(a[0],a[1]+7.62));p.label(n,(a[0],a[1]+7.62),True);p.done.add((ref,'1'))

def usbpage():
    p=Page('usb','USB-C data, protection and supply','USB data pair is routed as one functional group; connector CC resistors and protection remain local.')
    ur={'B5':('R',55.88),'A5':('R',66.04),'C6':('R',101.6)}
    p.block('U1',8,30.48,111.76,ur,'MCU USB HS')
    jd=bynet('J1');jr={}
    for n,ys in [('USB_DP',[55.88,59.69]),('USB_DM',[66.04,69.85]),('USB_CC1',[101.6]),('USB_CC2',[139.7]),('USB_VBUS',[180.34,184.15]),('GND',[223.52+i*3.81 for i in range(6)]),(None,[195.58,203.2])]:
        for pn,y in zip(jd[n],ys):jr[pn]=('R' if n=='GND' or n is None else 'L',y)
    p.block('J1',1,304.8,375.92,jr,'USB-C receptacle')
    for n,y in [('USB_DP',55.88),('USB_DM',66.04)]:
        uk=next(k for k in p.pts if k[0]=='U1' and net(*k)==n)
        p.wire(p.pts[uk],(289.56,y));p.label(n,(124.46,y));p.done.add(uk)
        for pn in jd[n]:a=p.pts['J1',pn];p.wire(a,(289.56,a[1]),(289.56,y));p.done.add(('J1',pn))
    p.branch('R18',p.pts['U1','C6'],'1',x=139.7);p.done.add(('U1','C6'));p.label('USB_TX_RTUNE',p.pts['U1','C6'])
    for r,n in [('R10','USB_CC1'),('R11','USB_CC2')]:
        pn=jd[n][0];a=p.pts['J1',pn];p.branch(r,a,'1',x=281.94);p.done.add(('J1',pn));p.label(n,(281.94,a[1]))
    p.connect('GND',[('J1',pn) for pn in jd['GND']],383.54)
    p.connect('USB_VBUS',[('J1',pn) for pn in jd['USB_VBUS']],294.64)
    # ESD array presented directly beside the data pair, with both duplicate channels explicit.
    dr={'1':('L',111.76),'6':('L',115.57),'3':('L',124.46),'4':('L',128.27),'5':('R',111.76),'2':('R',147.32)}
    p.block('D1',1,180.34,238.76,dr,'USB ESD array')
    # This block sits below the through pair in a dedicated local view to avoid a line through its body.
    for n in ['USB_DP','USB_DM']:
        ks=[('D1',pn) for pn in bynet('D1')[n]];xx=165.1 if n=='USB_DP' else 157.48;a=p.connect(n,ks,xx)
        p.wire(a,(xx,55.88 if n=='USB_DP' else 66.04));p.dot((xx,55.88 if n=='USB_DP' else 66.04))
    p.branch('C43',p.pts['D1','5'],'1',x=259.08);p.done.add(('D1','5'));p.label('USB_VBUS',p.pts['D1','5'])
    # USB input power: decoupling, LDO, and Schottky feed to SYS_IN.
    rr={'1':('L',190.5),'3':('L',194.31),'2':('L',233.68),'5':('R',190.5),'4':('R',233.68)}
    p.block('U4',1,109.22,187.96,rr,'USB analog supply')
    a=p.connect('USB_VBUS',[('U4','1'),('U4','3')],99.06);p.bank(['C13'],63.5,a[1],anchor=a)
    a=p.connect('3V3_USB',[('U4','5')],198.12);p.bank(['C14'],228.6,a[1],anchor=a)
    p.part('D2',63.5,154.94);p.wire(p.pts['D2','2'],(99.06,154.94),(99.06,190.5));p.wire(p.pts['D2','1'],(43.18,154.94));p.label('SYS_IN',(43.18,154.94),True,'left');p.done.update([('D2','1'),('D2','2')])

def auxpage():
    p=Page('rtc_accelerometer','RTC and accelerometer interfaces','Separate MCU buses for the RTC and switched accelerometer. Bias and bypass networks are local to their ICs.')
    ud=bynet('U1',9);ys={'RTC_I2C1_SCL':50.8,'RTC_I2C1_SDA':58.42,'RTC_INT_N':96.52,'ACCEL_I2C_SCL':139.7,'ACCEL_I2C_SDA':147.32,'ACCEL_INT1':185.42,'ACCEL_PWR_EN':231.14}
    ur={pn:('R',ys[n]) for n,ps in ud.items() for pn in ps};p.block('U1',9,25.4,111.76,ur,'MCU RTC / orientation')
    rd={'3':('L',50.8),'4':('L',58.42),'2':('L',96.52),'7':('R',45.72),'6':('R',81.28),'8':('R',111.76),'5':('L',116.84),'1':('L',111.76)}
    p.block('U8',1,269.24,345.44,rd)
    ad={'1':('L',139.7),'4':('L',147.32),'12':('L',185.42),'9':('R',157.48),'10':('R',161.29),'2':('R',165.1),'3':('R',195.58),'6':('R',199.39),'7':('R',203.2),'8':('R',207.01),'5':('L',213.36),'11':('L',218.44)}
    p.block('U11',1,269.24,345.44,ad)
    p.bundle('RTC_I2C',['RTC_I2C1_SCL','RTC_I2C1_SDA'],111.76,269.24)
    p.bundle('ACCEL_I2C',['ACCEL_I2C_SCL','ACCEL_I2C_SDA'],111.76,269.24)
    for n in ['RTC_INT_N','ACCEL_INT1']:
        ks=[k for k in p.pts if net(*k)==n];p.wire(*[p.pts[k] for k in ks]);p.label(n,(119.38,ys[n]));p.done.update(ks)
    for ref,n,x,down in [('R28','RTC_I2C1_SCL',233.68,False),('R29','RTC_I2C1_SDA',233.68,True),('R26','RTC_I2C1_SDA',256.54,True),('R24','RTC_INT_N',228.6,True),('R31','ACCEL_I2C_SCL',233.68,False),('R30','ACCEL_I2C_SDA',233.68,True)]:
        # Select signal pin 1; pull-ups rise, pull-downs fall. Rotation is adjusted if needed below.
        p.branch(ref,(x,ys[n]),'1',x=x,down=down)
    for ref,n,pn in [('C67','3V3','7'),('C68','BAT_CELL1_TAP','6')]:
        a=p.connect(n,[('U8',pn)],355.6);p.bank([ref],381,a[1],anchor=a)
    a=p.pts['U8','8'];p.branch('R25',a,'1',x=375.92);p.done.add(('U8','8'));p.label('RTC_EVI',a)
    a=p.connect('ACCEL_1V8_SW',[('U11',pn) for pn in ['9','10','2']],355.6);p.bank(['C72','C73'],375.92,a[1],anchor=a,spacing=20.32)
    p.connect('GND',[('U11',pn) for pn in ['3','6','7','8']],355.6)
    # Dedicated switched sensor supply below the interface; port groups are explicit.
    sr={'1':('L',246.38),'3':('L',231.14),'2':('L',261.62),'6':('R',241.3),'5':('R',245.11),'4':('R',261.62)}
    p.block('U12',1,208.28,284.48,sr,'Accelerometer load switch')
    a=p.pts['U1','A9'];p.wire(a,p.pts['U12','3']);p.label('ACCEL_PWR_EN',(119.38,a[1]));p.done.update([('U1','A9'),('U12','3')]);p.branch('R32',(147.32,231.14),'1',x=147.32)
    p.bank(['C74'],180.34,246.38,anchor=p.pts['U12','1']);p.done.add(('U12','1'))
    a=p.connect('ACCEL_1V8_SW',[('U12','6'),('U12','5')],294.64);p.wire(a,(363.22,241.3),(363.22,157.48),(355.6,157.48));p.dot((355.6,157.48))
    p.tap('TP10',(368.3,81.28))
    for ref,n,x in [('TP9','RTC_I2C1_SCL',205.74),('TP8','RTC_I2C1_SDA',185.42)]:
        # Testpoints are on the receiver's labelled member wires.
        p.part(ref,x,119.38);a=p.pts[ref,'1'];p.wire(a,(x,a[1]+5.08));p.label(n,(x,a[1]+5.08),True);p.done.add((ref,'1'))

def latchpage():
    p=Page('battery_latch','Battery latch, shutter and status LED','Original latch topology retained. Gate, source, hold and shutter nets are drawn as explicit local circuits.')
    p.part('Q1',119.38,63.5);p.part('Q3',215.9,63.5)
    # Common sources and gates are joined directly; each drain remains a separate power port.
    q1s=p.pts['Q1','2'];q3s=p.pts['Q3','2'];p.wire(q1s,(q1s[0],93.98),(q3s[0],93.98),q3s)
    p.label('BAT_FET_COMMON_SOURCE',(134.62,93.98))
    q1g=p.pts['Q1','1'];q3g=p.pts['Q3','1'];p.wire(q1g,(99.06,63.5),(99.06,116.84),(195.58,116.84),(195.58,63.5),q3g)
    p.label('PMOS_GATE',(111.76,116.84))
    for ref,n in [('Q1','BAT_PLUS'),('Q3','SYS_IN')]:
        a=p.pts[ref,'3'];p.wire(a,(a[0],40.64));p.label(n,(a[0],40.64),True)
    p.done.update((ref,pn) for ref in ['Q1','Q3'] for pn in ['1','2','3'])
    p.part('R1',157.48,104.14,True);p.wire((157.48,93.98),p.pts['R1','1']);p.wire(p.pts['R1','2'],(157.48,116.84));p.done.update([('R1','1'),('R1','2')]);p.dot((157.48,93.98));p.dot((157.48,116.84))
    p.part('R2',157.48,142.24,True);p.wire((157.48,116.84),p.pts['R2','1'])
    p.part('Q2',154.94,180.34);p.wire(p.pts['R2','2'],p.pts['Q2','3']);p.label('LATCH_PULLDOWN',(157.48,162.56));p.done.update([('R2','1'),('R2','2'),('Q2','3')])
    g=p.pts['Q2','1'];p.wire(g,(104.14,g[1]));p.label('PWR_HOLD',(104.14,g[1]),True,'left');p.done.add(('Q2','1'));p.branch('R3',(121.92,g[1]),'1',x=121.92)
    s=p.pts['Q2','2'];p.wire(s,(s[0],210.82));p.label('GND',(s[0],210.82),True);p.done.add(('Q2','2'))
    p.part('D3',223.52,157.48);p.wire(p.pts['D3','2'],(246.38,157.48),(246.38,147.32),(157.48,147.32));p.dot((157.48,147.32));p.done.add(('D3','2'))
    p.wire(p.pts['D3','1'],(203.2,157.48),(203.2,226.06),(251.46,226.06));p.label('SHUTTER_SENSE',(203.2,226.06),True);p.done.add(('D3','1'))
    p.part('SW1',256.54,226.06);p.wire(p.pts['SW1','2'],(281.94,226.06));p.label('GND',(281.94,226.06),True);p.done.update([('SW1','1'),('SW1','2')])
    p.tap('TP1',(121.92,40.64),x=99.06)
    p.part('TP2',76.2,231.14);a=p.pts['TP2','1'];p.wire(a,(a[0],241.3));p.label('GND',(a[0],241.3),True);p.done.add(('TP2','1'))
    p.text('Status indicator',307.34,45.72,1.778)
    p.part('R12',327.66,73.66,True);p.part('LED1',327.66,114.3)
    a=p.pts['R12','1'];p.wire(a,(a[0],55.88));p.label('3V3',(a[0],55.88),True)
    p.wire(p.pts['R12','2'],(327.66,93.98),(347.98,93.98),(347.98,114.3),p.pts['LED1','2']);p.label('STATUS_LED_A',(330.2,93.98))
    p.wire(p.pts['LED1','1'],(304.8,114.3),(304.8,139.7));p.label('STATUS_LED_K',(304.8,139.7),True)
    p.done.update([('R12','1'),('R12','2'),('LED1','1'),('LED1','2')])

def appendix():
    p=Page('ground_unused','MCU grounds and unused GPIO A-D','All physical ground balls and unused pins remain individually numbered. NC marks preserve source no-connect intent.')
    r={};ps=[pnum(p) for p in pins('U1',3)]
    for i,pn in enumerate(ps):r[pn]=('R',45.72+5.08*i)
    p.block('U1',3,30.48,121.92,r,'MCU ground balls');p.connect('GND',[('U1',pn) for pn in ps],134.62)
    for u,lx,rx in [(10,223.52,370.84)]:
        ps=[pnum(p) for p in pins('U1',u)];r={pn:('L' if i<len(ps)/2 else 'R',45.72+7.62*(i%(math.ceil(len(ps)/2)))) for i,pn in enumerate(ps)};p.block('U1',u,lx,rx,r,'Unused GPIO A-D')
    p=Page('unused_gpio','Unused MCU GPIO and interfaces','Explicit no-connects retained for every unused MCU terminal. These pages are reference appendices.')
    for u,lx,rx in [(11,40.64,172.72),(12,246.38,378.46)]:
        ps=[pnum(p) for p in pins('U1',u)];half=math.ceil(len(ps)/2);r={pn:('L' if i<half else 'R',45.72+7.62*(i%half)) for i,pn in enumerate(ps)};p.block('U1',u,lx,rx,r,'Unused MCU terminals')

def main():
    OUT.mkdir(exist_ok=True);(OUT/'review').mkdir(exist_ok=True)
    for name in ['fp-lib-table','sym-lib-table']:
        shutil.copy2(SRC/name,OUT/name)
    shutil.copytree(SRC/'GX.pretty',OUT/'GX.pretty',dirs_exist_ok=True)
    (OUT/(PROJECT+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':PROJECT+'.kicad_pro','version':1},'text_variables':{}},indent=2))
    latchpage();railpage();powerpages();controlpage();camerapages();memorypages();usbpage();auxpage();appendix()
    expected=set(k for k in INST if not k[0].startswith('#'))
    assert PLACED==expected,('missing',expected-PLACED,'extra',PLACED-expected)
    for p in PAGES:p.finish()
    for p in PAGES:(OUT/(p.name+'.kicad_sch')).write_text(dumps(p.tree())+'\n',encoding='utf8')
    root=S(f'(kicad_sch (version 20250114) (generator "global_x_readable") (uuid {Q(ROOT_ID)}) (paper "A3") (title_block (title "Global X Camera - readable schematic") (date "2026-09-05") (rev "A-readable") (company "Global X Camera")) (lib_symbols))')
    cover=Page('cover','Global X Camera','Functional circuit drawings | Presentation revision of the recovered circuit')
    PAGES.pop()
    cover.text('Local support circuits use direct wires. Named buses group data and control interfaces.',12.7,35.56,1.524)
    cover.text('Global labels join power rails and signals between functional pages. Reference designators and physical pin numbers are unchanged.',12.7,43.18)
    cover.text('This is a layout-only revision. Existing design issues, source assumptions and DNP choices remain for the ongoing electrical review.',12.7,50.8)
    for i,p in enumerate(PAGES):
        col=i%2;row=i//2;x=12.7+col*198.12;y=68.58+row*24.13
        root.append(S(f'(sheet (at {x} {y}) (size 182.88 15.24) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {Q(p.sid)}) (property "Sheetname" {Q(str(p.num)+"  "+p.title)} (at {x} {y-1.27} 0) (effects (font (size 1.27 1.27)) (justify left))) (property "Sheetfile" {Q(p.name+".kicad_sch")} (at {x} {y+16.51} 0) (effects (font (size 1.016 1.016)) (justify left))) (instances (project {Q(PROJECT)} (path {Q("/"+ROOT_ID)} (page {Q(p.num)})))))'))
    flags=sorted((k,v) for k,v in INST.items() if k[0].startswith('#'))
    child(root,'lib_symbols').append(copy.deepcopy(LIB['GX:PWR_FLAG']))
    for i,((ref,u),s) in enumerate(flags):
        inst=copy.deepcopy(s);old=child(s,'at');x=snap(30.48+i*49.53);y=241.3
        oldroot=parse((SRC/'global-x-camera.kicad_sch').read_text(encoding='utf8'))
        flag_nets=['BAT_PLUS','BAT_CELL1_TAP','USB_VBUS','SYS_IN','3V3','1V8','VCORE_0V81','GND']
        n=flag_nets[int(ref[-3:])-1]
        child(inst,'at')[1:]=[x,y,0];child(inst,'uuid')[1]=uid(ref)
        child(inst,'instances')[1:]=[S(f'(project {Q(PROJECT)} (path {Q("/"+ROOT_ID)} (reference {Q(ref)}) (unit 1)))')]
        for pr in children(inst,'property'):child(pr,'at')[1:]=[x,y,0]
        root.append(inst);cover.wire((x,y),(x,y+5.08));cover.label(n,(x,y+5.08),True)
    cover.text('Supply-source declarations retained from the recovered schematic for ERC.',12.7,233.68,1.016)
    root.extend(cover.items);root.append(S('(sheet_instances (path "/" (page "1")))'));root.append(S('(embedded_fonts no)'))
    (OUT/(PROJECT+'.kicad_sch')).write_text(dumps(root)+'\n',encoding='utf8')
    library=[A('kicad_symbol_lib'),S('(version 20250114)'),S('(generator "global_x_readable")')]
    for k,v in sorted(LIB.items()):
        lib=copy.deepcopy(v);lib[1]=k.split(':',1)[1];library.append(lib)
    (OUT/'GX.kicad_sym').write_text(dumps(library)+'\n',encoding='utf8')
    (OUT/'review/source-snapshot.json').write_text(json.dumps(BASE_HASH,indent=2))
    (OUT/'review/layout-summary.json').write_text(json.dumps({'pages':[{'number':p.num,'title':p.title,'file':p.name+'.kicad_sch','components':p.placed} for p in PAGES],'components':len(set(r for r,u in PLACED)),'pins':sum(len(c['pins']) for c in CIRCUIT.values())},indent=2))
    print(f'Created {len(PAGES)+1} sheets with {len(PLACED)} symbol units in {OUT}')

if __name__=='__main__':main()
