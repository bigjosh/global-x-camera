"""Reconstruct an editable KiCad schematic from audited Flux source data.

No source export is edited. Deliberate reconstruction decisions are written
separately, and KiCad's own exported netlist is checked by validate_schematic.py.
"""
import base64
import copy
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import uuid

from kicad_sexpr import Atom as A, child, children, dumps, parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware' / 'kicad'
REC = ROOT / 'hardware' / 'reconstruction'
FLUX = ROOT / 'imports' / 'flux' / '2026-09-05'
KICAD = Path.home() / 'AppData/Local/Programs/KiCad/10.0'
PROJECT = 'global-x-camera'
NS = uuid.UUID('f155a839-ec29-47c8-9c13-c147f896fdd2')
S = lambda text: parse(text)
Q = lambda text: json.dumps(str(text), ensure_ascii=False)
UID = lambda text: str(uuid.uuid5(NS, text))
GRID = 1.27
def snap(x): return round(round(x / GRID) * GRID, 4)
def num(x): return round(float(x), 4)
def natural(text): return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)', str(text))]
def yes(value): return str(value).lower() in ('true', 'yes', '1')


def fx(size=1.27, justify='', hide=False):
    return S(f'(effects (font (size {size} {size})) {"(justify " + justify + ")" if justify else ""} {"(hide yes)" if hide else ""})')


def prop(name, value, x=0, y=0, hide=False, size=1.27, justify=''):
    return [A('property'), name, str(value), [A('at'), num(x), num(y), 0], fx(size, justify, hide)]


def clean(text):
    return str(text).replace('Ω', 'ohm').replace('µ', 'u').replace('μ', 'u').replace('\r', ' ').replace('\n', ' ')


def pin_name(ref, name, pin):
    fixes = {'VDDA18A_DC':'VDDA18ADC','VDD33US_B':'VDD33USB','VDDA18P_MU':'VDDA18PMU',
             'VDDA18A_ON':'VDDA18AON','VDDA18C_SI':'VDDA18CSI','VDDA18U_SB':'VDDA18USB',
             'VDDA18P_LL':'VDDA18PLL','UCPD1_C_C1':'UCPD1_CC1','UCPD1_C_C2':'UCPD1_CC2',
             'PC15-_OSC32_O_UT':'PC15-OSC32_OUT','PH0-_OSC_IN':'PH0-OSC_IN',
             'PH1-_OSC_OUT':'PH1-OSC_OUT','PC14-_OSC32_IN':'PC14-OSC32_IN'}
    name = fixes.get(name, name)
    if name == '~': name = pin
    if ref == 'U5' and pin in ('3','7'): name = {'3':'IO2', '7':'IO3'}[pin]
    return name


def default_type(ref, pin, info):
    name = info['name']; n = name.upper()
    if n.startswith('NC') or n in ('DNU','N.C.'): return 'no_connect'
    if ref == 'U1':
        if n.startswith(('VDD','VSS','VREF')) or n == 'VBAT': return 'power_in'
        if n.startswith('VLXSMPS') or n == 'V08CAP': return 'power_out'
        if n in ('PWR_ON', 'PH1-_OSC_OUT'): return 'output'
        if n.startswith('CSI_') or n in ('NRST','BOOT0','PDR_ON','VFBSMPS','PH0-_OSC_IN'): return 'input'
        if n.startswith('OTG') and n.endswith('_ID'): return 'input'
        return 'bidirectional'
    return 'passive'


LIBCACHE = {}
def standard_symbol(library, name):
    if library not in LIBCACHE:
        tree = parse((KICAD / 'share/kicad/symbols' / (library + '.kicad_sym')).read_text(encoding='utf-8'))
        LIBCACHE[library] = {s[1]: s for s in children(tree, 'symbol')}
    original = copy.deepcopy(LIBCACHE[library][name])
    extends = child(original, 'extends')
    if extends:
        parent = standard_symbol(library, extends[1])
        replaced = {p[1] for p in children(original, 'property')}
        parent = [p for p in parent if not (isinstance(p,list) and p and p[0]=='property' and p[1] in replaced)]
        parent.extend(p for p in original[2:] if p[0] not in ('extends',))
        parent[1] = name
        original = parent
    return original


def rotate_graphics(node):
    if not isinstance(node,list) or not node:return
    if node[0] in ('at','start','end','mid','center','xy') and len(node)>=3:
        x,y=float(node[1]),float(node[2]);node[1:3]=[num(-y),num(x)]
        if node[0]=='at' and len(node)>3:node[3]=num((float(node[3])+90)%360)
    for item in node:
        if isinstance(item,list):rotate_graphics(item)


class Symbol:
    def __init__(self, ref, record, component, units, types):
        self.ref, self.record, self.component = ref, record, component
        self.units = units
        self.libid = 'GX:' + ref
        p = record['properties']
        self.value = clean(p.get('Manufacturer Part Number') or next((p[k] for k in ['Resistance','Capacitance','Inductance'] if p.get(k)), ref))
        self.footprint = self.make_footprint()
        self.dnp = ref in ('SW2','SW3')
        self.board = not yes(p.get('Exclude from PCB', False)) and ref != 'CAM1'
        self.bom = not yes(p.get('Exclude from BOM',False))
        self.positions = {}
        self.body = {}
        self.standard = None
        if ref.startswith('C') and ref != 'CAM1': self.standard = ('Device','C')
        elif ref.startswith('R'): self.standard = ('Device','R')
        elif ref.startswith('L') and not ref.startswith('LED'): self.standard = ('Device','L')
        elif ref in ('D2','D3'): self.standard = ('Device','D_Schottky' if ref=='D2' else 'D')
        elif ref == 'LED1': self.standard = ('Device','LED')
        elif ref in ('Q1','Q3'): self.standard = ('Transistor_FET','Q_PMOS_GSD')
        elif ref == 'Q2': self.standard = ('Transistor_FET','Q_NMOS_GSD')
        elif ref.startswith('SW'): self.standard = ('Switch','SW_SPST')
        elif ref == 'Y1': self.standard = ('Device','Crystal_GND24')
        elif ref.startswith('TP'): self.standard = ('Connector','TestPoint')
        self.lib = self.make_library(types)

    def make_footprint(self):
        ref = self.ref
        if ref == 'CAM1': return ''
        p = self.record['properties']
        package = p.get('Package','')
        if ref.startswith('TP'):
            diameter=float(p.get('Testpoint Size',0.5))
            data=f'(footprint "TestPoint" (version 20240108) (generator "global_x_reconstruction") (layer "F.Cu") (attr smd) (pad "1" smd circle (at 0 0) (size {diameter} {diameter}) (layers "F.Cu" "F.Mask")))'
        elif package.startswith('SMD_') and ref[0] in 'RCL' and ref != 'LED1':
            metric = package[4:]
            family, prefix = {'R':('Resistor_SMD','R'),'C':('Capacitor_SMD','C'),'L':('Inductor_SMD','L')}[ref[0]]
            path = KICAD/'share/kicad/footprints'/f'{family}.pretty'/f'{prefix}_{metric}.kicad_mod'
            if not path.exists(): raise ValueError(f'Missing standard footprint {path}')
            data = path.read_text(encoding='utf-8')
        elif (REC/'generated-footprints'/f'{ref}.kicad_mod').exists():
            data=(REC/'generated-footprints'/f'{ref}.kicad_mod').read_text(encoding='utf-8')
        else:
            cache = NATIVE['elements'][self.record['element_uid']]['part_version_data_cache']
            nodes = [n for n in cache.get('pcbLayoutNodes',{}).values() if n.get('type')=='footprint']
            payloads = [n['pcbNodeRuleSet']['asset'].get('payloadAsBase64') for n in nodes if n.get('pcbNodeRuleSet',{}).get('asset',{}).get('payloadAsBase64')]
            if len(payloads) != 1: raise ValueError(f'{ref}: expected one cached footprint, got {len(payloads)}')
            data = base64.b64decode(payloads[0]).decode('utf-8-sig')
        tree = parse(data)
        tree[1] = ref + '_Recovered'
        # Missing external model paths do not belong in a portable project.
        models = children(tree,'model')
        if models: MODEL_REFS[ref] = [m[1] for m in models]
        tree = [x for x in tree if not (isinstance(x,list) and x and x[0]=='model')]
        (OUT/'GX.pretty'/f'{ref}_Recovered.kicad_mod').write_text(dumps(tree)+'\n',encoding='utf-8')
        return 'GX:' + ref + '_Recovered'

    def make_library(self, types):
        pins = self.component['pins']
        if self.standard:
            lib = standard_symbol(*self.standard)
            lib[1] = self.libid
            groups = children(lib,'symbol')
            for g in groups:
                suffix = re.search(r'_(\d+_\d+)$',g[1]).group(1)
                g[1] = self.ref + '_' + suffix
                if self.ref[0] in 'RCL' and self.ref!='LED1':rotate_graphics(g)
            lib = [x for x in lib if not (isinstance(x,list) and x and x[0] in ('property','extends','in_pos_files','duplicate_pin_numbers_are_jumpers'))]
            lib.extend([prop('Reference',self.ref),prop('Value',self.value),prop('Footprint',self.footprint,hide=True),prop('Datasheet','',hide=True)])
            pos = {}
            for g in groups:
                for pin in children(g,'pin'):
                    number = str(child(pin,'number')[1]); at = child(pin,'at')
                    if number in pins:
                        pin[1] = A(types.get(self.ref,{}).get(number,default_type(self.ref,number,pins[number])))
                    pos[number] = (float(at[1]), float(at[2]), float(at[3]))
            assert set(pos)==set(pins),(self.ref,set(pos),set(pins))
            self.positions[1] = pos
            self.body[1] = (10.16,10.16)
            return lib
        lib = S(f'(symbol {Q(self.libid)} (pin_names (offset 0.8)) (exclude_from_sim no) (in_bom yes) (on_board yes))')
        lib.extend([prop('Reference',self.ref),prop('Value',self.value),prop('Footprint',self.footprint,hide=True),prop('Datasheet','',hide=True)])
        for unit, (title, numbers) in enumerate(self.units, 1):
            count = len(numbers); half = math.ceil(count/2)
            width = 55.88 if self.ref=='U1' else (45.72 if count>8 else 35.56)
            height = max(12.7,(half+1)*3.81)
            group = S(f'(symbol {Q(self.ref+"_"+str(unit)+"_1")} (rectangle (start {-width/2} {height/2}) (end {width/2} {-height/2}) (stroke (width 0.254) (type default)) (fill (type background))))')
            pos = {}
            for i, number in enumerate(numbers):
                side = 0 if i<half else 1
                row = i if side==0 else i-half
                x = (-1 if side==0 else 1)*(width/2+5.08)
                y = snap(height/2 - (row+1)*3.81)
                angle = 0 if side==0 else 180
                info = pins[number]
                typ = types.get(self.ref,{}).get(number,default_type(self.ref,number,info))
                name = pin_name(self.ref,info['name'],number)
                group.append(S(f'(pin {typ} line (at {x} {y} {angle}) (length 5.08) (name {Q(name)} (effects (font (size 1.016 1.016)))) (number {Q(number)} (effects (font (size 1.016 1.016)))))'))
                pos[number] = (x,y,angle)
            lib.append(group); self.positions[unit]=pos; self.body[unit]=(width,height)
        return lib


class Page:
    def __init__(self, name, title, subtitle, number):
        self.name,self.title,self.number = name,title,number
        self.uuid=UID('sheet:'+name)
        self.sheet_uuid=UID('hierarchy:'+name)
        self.items=[];self.libs={};self.placed=[]
        self.text(title,12.7,15.24,2.54)
        self.text(subtitle,12.7,22.86,1.27)
        self.text('RECONSTRUCTED SOURCE - review notes and ERC report apply',12.7,280.67,1.016)

    def text(self,text,x,y,size=1.27):
        self.items.append(S(f'(text {Q(text)} (at {num(x)} {num(y)} 0) (effects (font (size {size} {size})) (justify left)) (uuid {Q(UID(self.name+":text:"+str(len(self.items))))}))'))

    def wire(self,x,y,xx,yy,key):
        if (x,y)==(xx,yy): return
        self.items.append(S(f'(wire (pts (xy {num(x)} {num(y)}) (xy {num(xx)} {num(yy)})) (stroke (width 0) (type default)) (uuid {Q(UID(key))}))'))

    def label(self,net,x,y,side,key):
        angle=0 if side=='left' else 180
        self.items.append(S(f'(global_label {Q(net)} (shape passive) (at {num(x)} {num(y)} {angle}) (effects (font (size 1.016 1.016)) (justify {"right" if side=="left" else "left"})) (uuid {Q(UID(key))}) (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {num(x)} {num(y)} {angle}) (effects (font (size 1.016 1.016)) (hide yes))))'))

    def place(self,sym,unit,x,y,angle=0):
        ref=sym.ref; key=self.name+':'+ref+':'+str(unit)
        self.libs[sym.libid]=sym.lib
        bw,bh=sym.body[unit]
        # Ref/value above symbol; label space is outside the symbol on each side.
        top=y-bh/2-7.62 if not sym.standard else y-10.16
        instance=S(f'(symbol (lib_id {Q(sym.libid)}) (at {num(x)} {num(y)} {angle}) (unit {unit}) (exclude_from_sim no) (in_bom {"yes" if sym.bom else "no"}) (on_board {"yes" if sym.board else "no"}) (dnp {"yes" if sym.dnp else "no"}) (uuid {Q(UID(key))}))')
        instance.extend([prop('Reference',ref,x,top,size=1.524),prop('Value',sym.value,x,top+3.81,size=1.27),prop('Footprint',sym.footprint,x,y,hide=True)])
        props=sym.record['properties']
        ds=props.get('Datasheet URL','');ds=ds.get('text') or ds.get('url') or '' if isinstance(ds,dict) else ds
        if ref=='J2':ds='${KIPRJMOD}/../../datasheets/connectors/TC2030-IDC-NL_datasheet_footprint.pdf'
        instance.append(prop('Datasheet',ds,x,y,hide=True))
        for name in ['Manufacturer Part Number','Manufacturer Name','Package','Voltage Rating','Tolerance','Role','Role Details','Functional Group']:
            if props.get(name) not in ('',None):instance.append(prop(name,clean(props[name]),x,y,hide=True))
        instance.append(prop('Flux Element UUID',sym.record['element_uid'],x,y,hide=True))
        if not sym.standard and len(sym.units)>1:self.text(sym.units[unit-1][0],x-bw/2,top-4.445,1.27)
        for pin,(dx,dy,pa) in sym.positions[unit].items():
            rad=math.radians(angle)
            px=snap(x+dx*math.cos(rad)-dy*math.sin(rad));py=snap(y-dx*math.sin(rad)-dy*math.cos(rad))
            info=sym.component['pins'][pin]
            instance.append(S(f'(pin {Q(pin)} (uuid {Q(UID(key+":pin:"+pin))}))'))
            if info['status']=='no_connect':
                self.items.append(S(f'(no_connect (at {px} {py}) (uuid {Q(UID(key+":nc:"+pin))}))'))
            elif info.get('net'):
                theta=math.radians(pa+angle)
                xx=snap(px-5.08*math.cos(theta));yy=snap(py+5.08*math.sin(theta))
                self.wire(px,py,xx,yy,key+':wire:'+pin)
                side='left' if xx<x else 'right'
                self.label(info['net'],xx,yy,side,key+':label:'+pin)
            else:
                self.text('UNRESOLVED '+pin,px,py-1.27,1.016)
        instance.append(S(f'(instances (project {Q(PROJECT)} (path {Q("/"+ROOT_UUID+"/"+self.sheet_uuid)} (reference {Q(ref)}) (unit {unit}))))'))
        self.items.append(instance);self.placed.append((ref,unit))

    def write(self):
        tree=S(f'(kicad_sch (version 20250114) (generator "global_x_reconstruction") (uuid {Q(self.uuid)}) (paper "A3") (title_block (title {Q(self.title)}) (date "2026-09-05") (rev "A") (company "Global X Camera") (comment 1 "Source recovery; electrical design review pending")))')
        tree.append([A('lib_symbols'),*self.libs.values()]);tree.extend(self.items)
        tree.append(S('(embedded_fonts no)'))
        (OUT/(self.name+'.kicad_sch')).write_text(dumps(tree)+'\n',encoding='utf-8')


def mcu_groups(component):
    g=defaultdict(list)
    for pin,info in component['pins'].items():
        n=info['name'];net=info.get('net') or ''
        if n.startswith('VSS') or n=='VREF-':group='MCU grounds'
        elif n.startswith(('VDDSMPS','VLXSMPS','VDDCORE')) or n in ('VFBSMPS','V08CAP'):group='Core supply and internal SMPS'
        elif n.startswith(('VDD','VREF')) or n=='VBAT':group='I/O and analog supplies'
        elif info['status']=='no_connect':
            group='Unused GPIO A-D' if re.match(r'P[A-D]\d',n) else 'Unused GPIO E-M' if re.match(r'P[E-M]\d',n) else 'Unused GPIO N-Q and interfaces'
        elif net.startswith('BOOT_XSPI'):group='Boot flash interface'
        elif net.startswith('NAND_'):group='NAND interface'
        elif net.startswith(('CAM_','I2C4_','CSI_')):group='Camera interface'
        elif net.startswith('USB_'):group='USB interface'
        elif net.startswith(('RTC_','ACCEL_')):group='RTC and accelerometer interface'
        else:group='Clock, boot, debug and system control'
        g[group].append(pin)
    order=['I/O and analog supplies','Core supply and internal SMPS','MCU grounds','Clock, boot, debug and system control',
           'Boot flash interface','NAND interface','Camera interface','USB interface','RTC and accelerometer interface',
           'Unused GPIO A-D','Unused GPIO E-M','Unused GPIO N-Q and interfaces']
    return [(k,sorted(g[k],key=lambda p:natural(component['pins'][p]['name']))) for k in order if g[k]]


def category(ref,p):
    if ref=='U1':return None
    group=p.get('Functional Group','')
    if ref=='R17':return 'camera'
    if ref=='R18':return 'usb'
    if ref in ('R19','C69'):return 'mcu_core'
    if ref in ('Y1','C36','C37','C38','R8','R9','SW2','SW3') or group=='Debug and Test':return 'control'
    if 'Orientation Accelerometer' in group:return 'aux'
    if 'RTC and Backup' in group and ref not in ('R22','R23'):return 'aux'
    if 'Camera' in group:return 'camera_power' if group=='Camera Power' else 'camera'
    if 'Boot Flash' in group:return 'boot'
    if 'Raw NAND Storage' in group:return 'nand'
    if ref in ('D2','C13','C14','U4') or 'USB-C' in group:return 'usb'
    if 'Battery Latch' in group or 'Shutter and Status' in group:return 'latch'
    if 'Regulators and Rails' in group:return 'rails'
    if group=='MCU Core':return 'mcu_power'
    raise ValueError((ref,group))


def main():
    global NATIVE, ROOT_UUID, MODEL_REFS
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'GX.pretty').mkdir(exist_ok=True)
    REC.mkdir(parents=True,exist_ok=True)
    NATIVE=json.loads((FLUX/'bigjosh-global-x-camera.flx').read_text(encoding='utf-8'))
    inventory=json.loads((FLUX/'native-inventory.json').read_text(encoding='utf-8'))['instances']
    # Flux sometimes stores value and engineering unit separately. The older
    # inventory flattened values only; restore units directly from native data.
    for record in inventory.values():
        raw=NATIVE['elements'][record['element_uid']]['properties']
        for pr in raw.values():
            value=pr.get('value');unit=pr.get('unit')
            if unit and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',str(value)):
                record['properties'][pr['name']]=clean(str(value)+str(unit))
    source=json.loads((REC/'connectivity.json').read_text(encoding='utf-8'))
    circuit=copy.deepcopy(source['components']);types={};decisions=[]
    for name in ['aux-pin-map-review.json','pin-map-review.json']:
        path=REC/name
        if path.exists():
            review=json.loads(path.read_text(encoding='utf-8'))
            for ref,pins in review.get('pin_types',{}).items():types.setdefault(ref,{}).update(pins)
            for ref,pins in review.get('recommended_additional_pins',{}).items():
                for pin,info in pins.items():
                    assert pin not in circuit[ref]['pins']
                    circuit[ref]['pins'][pin]={'name':info['name'],'terminal_uid':None,'net':info['recommended_net'],
                        'status':'connected','evidence':[{'source':'pin-map-review.md','method':'Manufacturer module schematic and connector power contacts'}]}
                    types.setdefault(ref,{})[pin]=info['pin_type']
                    decisions.append({'reference':ref,'pin':pin,'net':info['recommended_net'],'kind':'manufacturer_documented_missing_contact',
                        'basis':'Exact ST camera module schematic grounds contacts 31-34; native J3 footprint already contains these copper pads.'})
    # Explicitly distinguish intended optional circuitry from fully recovered nets.
    optional={'SW2':{'1':'BOOT0','2':'1V8'},'SW3':{'1':'NRST','2':'GND'}}
    for ref,pins in optional.items():
        for pin,net in pins.items():
            info=circuit[ref]['pins'][pin]
            if info.get('net'):continue
            decisions.append({'reference':ref,'pin':pin,'net':net,'kind':'documented_intent_inference',
                              'basis':'Native Role Details specifies optional BOOT0-to-1V8 / NRST-to-GND switch. Two-terminal contact polarity is interchangeable.'})
            info.update(net=net,status='connected')
    # ERC models one driver for each internally common switching node.
    for ref,pins,net in [('U2',['1','2','3'],'BUCK3V3_SW'),('U1',['J1','J2','J3','J4','J5','J6'],'MCU_SMPS_SW')]:
        assert all(circuit[ref]['pins'][pin]['net']==net for pin in pins)
        for pin in pins[1:]:types.setdefault(ref,{})[pin]='passive'
        types.setdefault(ref,{})[pins[0]]='power_out'
    # QOD is an analog discharge terminal with internal resistance, tied to VOUT
    # as expressly allowed in TPS22918 datasheet section 8.3.2.
    types.setdefault('U12',{})['5']='passive'
    # In this source CS is held high: LIS2DW12 is in I2C mode, and SDO/SA0
    # is its strapped address input rather than an active SPI data output.
    assert circuit['U11']['pins']['2']['net']==circuit['U11']['pins']['9']['net']=='ACCEL_1V8_SW'
    types.setdefault('U11',{})['3']='input'
    ROOT_UUID=UID('root');MODEL_REFS={}
    symbols={}
    for ref in sorted(inventory,key=natural):
        component=circuit[ref]
        units=mcu_groups(component) if ref=='U1' else [(ref,sorted(component['pins'],key=natural))]
        symbols[ref]=Symbol(ref,inventory[ref],component,units,types)
    groups=defaultdict(list)
    for ref,sym in symbols.items():
        if ref!='U1':groups[category(ref,sym.record['properties'])].append((sym,1))
    unit_categories={'I/O and analog supplies':'mcu_power','Core supply and internal SMPS':'mcu_core','MCU grounds':'mcu_ground',
        'Clock, boot, debug and system control':'control','Boot flash interface':'boot','NAND interface':'nand','Camera interface':'camera',
        'USB interface':'usb','RTC and accelerometer interface':'aux','Unused GPIO A-D':'unused','Unused GPIO E-M':'unused','Unused GPIO N-Q and interfaces':'unused'}
    for unit,(title,pins) in enumerate(symbols['U1'].units,1):groups[unit_categories[title]].insert(0,(symbols['U1'],unit))
    # Put the internal SMPS network beside its dedicated MCU unit.
    for item in list(groups['mcu_power']):
        ref=item[0].ref
        if ref in ('L3','C15','C16','C17','C18','C19') or any((p.get('net') or '').startswith('MCU_SMPS_') for p in circuit[ref]['pins'].values()):
            groups['mcu_power'].remove(item);groups['mcu_core'].append(item)
    titles=[('latch','Battery latch and shutter','External battery stack, power hold, shutter sense and status LED.'),
        ('rails','Main regulated rails','3V3 and 1V8 converters. Values and package choices recovered from Flux.'),
        ('mcu_power','MCU I/O and analog power','Individual supply balls and local bypass components; placement still to be reviewed.'),
        ('mcu_core','MCU core supply','Internal SMPS terminals and external core supply components.'),
        ('mcu_ground','MCU grounds','Every ground ball remains individually numbered for package and netlist review.'),
        ('control','Clock, boot and debug','40 MHz oscillator, reset, boot straps, SWD and system controls. SW2/SW3 are DNP intent reconstruction.'),
        ('camera_power','Camera power','1.2V core and switched 2.8V analog rails. Check firmware sequencing separately.'),
        ('camera','Camera and CSI-2','One CSI-2 data lane plus clock. CAM1 is an external module and is excluded from the host PCB.'),
        ('boot','Boot NOR flash','W25Q128JVPIQ, Quad-SPI boot. IQ variant has fixed QE; pins 3/7 are IO2/IO3.'),
        ('nand','Raw NAND storage','MX30LF2G18AC-TI, x8 parallel interface. Firmware ECC and timing review remains separate.'),
        ('usb','USB-C and USB High-Speed','USB2 device interface, CC pull-downs, protection and USB-derived power.'),
        ('aux','RTC and orientation','Backup timekeeping, switched accelerometer supply and MCU interfaces.'),
        ('unused','Unused MCU terminals','Explicit source no-connects, shown individually. No hidden or omitted MCU pins.')]
    pages=[]
    for cat,title,subtitle in titles:
        entries=groups[cat]
        big=[i for i in entries if not i[0].standard]
        small=[i for i in entries if i[0].standard]
        # Two 190mm columns with independent vertical packing.
        page=None;columns=None;part=0
        def new_page():
            nonlocal page,columns,part
            part+=1;name=f'{len(pages)+2:02d}_{cat}_{part}'
            page=Page(name,title+(' - continued' if part>1 else ''),subtitle,len(pages)+2)
            pages.append(page);columns=[38.1,38.1]
            return page
        new_page()
        for sym,unit in big:
            height=sym.body[unit][1]+25.4
            col=min(range(2),key=lambda i:columns[i])
            if columns[col]+height>264.16:new_page();col=0
            cy=snap(columns[col]+12.7+sym.body[unit][1]/2)
            page.place(sym,unit,snap(105.41+col*199.39),cy)
            columns[col]+=height+5.08
        # Small devices occupy 95mm cells. Rows do not intersect larger blocks.
        rowbase=snap(max(columns))
        col=0
        for sym,unit in small:
            if rowbase+25.4>265.43:new_page();rowbase=38.1;col=0
            cx=snap(57.15+col*100.33);cy=snap(rowbase+15.24)
            page.place(sym,unit,cx,cy,0)
            col+=1
            if col==4:col=0;rowbase+=27.94
    for page in pages:page.write()
    root=S(f'(kicad_sch (version 20250114) (generator "global_x_reconstruction") (uuid {Q(ROOT_UUID)}) (paper "A3") (title_block (title "Global X Camera - source reconstruction") (date "2026-09-05") (rev "A") (company "Global X Camera")) (lib_symbols))')
    cover=Page(PROJECT,'Global X Camera','STM32N657 / VD55G0 camera | Functional schematic index',1)
    cover.text('Recovered from Flux on 2026-09-05. Editable source transcription; hardware signoff remains pending.',12.7,30.48)
    cover.text('Global net labels connect sheets. Each physical component pin is explicit. Original reference designators are retained.',12.7,36.83)
    cover.text('Read ../reconstruction/README.md for source reconciliation, assumptions, pin audits and ERC findings.',12.7,43.18)
    for i,page in enumerate(pages):
        col=i%3;row=i//3;x=12.7+col*133.35;y=55.88+row*30.48
        sheet=S(f'(sheet (at {x} {y}) (size 120.65 20.32) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid {Q(page.sheet_uuid)}) (property "Sheetname" {Q(str(page.number)+"  "+page.title)} (at {x} {y-1.27} 0) (effects (font (size 1.27 1.27)) (justify left))) (property "Sheetfile" {Q(page.name+".kicad_sch")} (at {x} {y+21.59} 0) (effects (font (size 1.016 1.016)) (justify left))) (instances (project {Q(PROJECT)} (path {Q("/"+ROOT_UUID)} (page {Q(str(page.number))})))))')
        root.append(sheet)
    flags=['BAT_PLUS','BAT_CELL1_TAP','USB_VBUS','SYS_IN','3V3','1V8','VCORE_0V81','GND']
    flag=standard_symbol('power','PWR_FLAG');flag[1]='GX:PWR_FLAG'
    child(root,'lib_symbols').append(flag)
    flag_y=228.6
    cover.text('ERC supply-source declarations: external inputs and post-passive power paths; these are not a power-design signoff.',12.7,217.17,1.016)
    for i,net in enumerate(flags):
        x=snap(30.48+i*49.53);key='powerflag:'+net;ref='#FLG'+str(i+1).zfill(3)
        inst=S(f'(symbol (lib_id "GX:PWR_FLAG") (at {x} {flag_y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid {Q(UID(key))}))')
        inst.extend([prop('Reference',ref,x,flag_y,hide=True),prop('Value','PWR_FLAG',x,flag_y-5.08,hide=True)])
        inst.append(S(f'(pin "1" (uuid {Q(UID(key+":pin"))}))'))
        inst.append(S(f'(instances (project {Q(PROJECT)} (path {Q("/"+ROOT_UUID)} (reference {Q(ref)}) (unit 1))))'))
        root.append(inst);cover.wire(x,flag_y,x,flag_y+5.08,key+':wire');cover.label(net,x,flag_y+5.08,'right',key+':label')
    root.extend(cover.items)
    root.append(S('(sheet_instances (path "/" (page "1")))'));root.append(S('(embedded_fonts no)'))
    (OUT/(PROJECT+'.kicad_sch')).write_text(dumps(root)+'\n',encoding='utf-8')
    library=[A('kicad_symbol_lib'),S('(version 20250114)'),S('(generator "global_x_reconstruction")')]
    for sym in symbols.values():
        lib=copy.deepcopy(sym.lib);lib[1]=sym.ref;library.append(lib)
    localflag=copy.deepcopy(flag);localflag[1]='PWR_FLAG';library.append(localflag)
    (OUT/'GX.kicad_sym').write_text(dumps(library)+'\n',encoding='utf-8')
    (OUT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "GX") (type "KiCad") (uri "${KIPRJMOD}/GX.kicad_sym") (options "") (descr "Recovered Global X Camera symbols")))\n',encoding='utf-8')
    (OUT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "GX") (type "KiCad") (uri "${KIPRJMOD}/GX.pretty") (options "") (descr "Recovered package data; footprint review pending")))\n',encoding='utf-8')
    pro=OUT/(PROJECT+'.kicad_pro')
    if not pro.exists():pro.write_text(json.dumps({'meta':{'filename':pro.name,'version':1},'text_variables':{}},indent=2)+'\n',encoding='utf-8')
    (REC/'reconstruction-decisions.json').write_text(json.dumps(decisions,indent=2)+'\n',encoding='utf-8')
    (REC/'schematic-connectivity.json').write_text(json.dumps({'components':circuit,'decisions':decisions},indent=2)+'\n',encoding='utf-8')
    (REC/'external-model-references.json').write_text(json.dumps(MODEL_REFS,indent=2)+'\n',encoding='utf-8')
    summary={'project':str(pro.relative_to(ROOT)),'component_count':len(symbols),'pin_count':sum(len(c['pins']) for c in circuit.values()),
             'sheet_count':len(pages)+1,'pages':[{'file':p.name+'.kicad_sch','title':p.title,'components':p.placed} for p in pages],
             'inferred_endpoints':decisions}
    (REC/'build-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='pages'},indent=2))


if __name__=='__main__':main()
