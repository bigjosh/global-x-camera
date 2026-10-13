import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/review'


def pdf(relative, pages, detail):
    path = ROOT / 'datasheets' / relative
    sidecar = json.loads(Path(str(path) + '.source.json').read_text(encoding='utf-8'))
    return {'type': 'manufacturer_pdf', 'path': path.relative_to(ROOT).as_posix(),
            'pdf_pages': pages, 'url': sidecar['source_url'],
            'sha256': sidecar['sha256'], 'detail': detail}


def source(refs, detail):
    return {'type': 'recovered_design', 'path': 'hardware/reconstruction/schematic-connectivity.json',
            'references': refs, 'detail': detail,
            'values_source': 'imports/flux/2026-09-05/bigjosh-global-x-camera.flx; per-instance properties including unit fields'}


findings = [
    {'id': 'PWR-001', 'severity': 'blocker', 'confidence': 'confirmed',
     'title': 'Battery latch pull-down back-drives the MCU shutter input',
     'references': ['Q1','Q3','R1','R2','D3','SW1','U1'],
     'observed': 'D3 anode is LATCH_PULLDOWN and cathode is SHUTTER_SENSE at U1 F3/PC13. When SW1 and Q2 are open, the path common PFET source -> R1 1 MOhm -> R2 100 kOhm -> D3 remains connected to PC13. There is no voltage translation or independent low-voltage switch contact.',
     'evidence': [source(['U1.F3','D3.1','D3.2','R1','R2','SW1'], 'SHUTTER_SENSE contains only PC13, D3 cathode and SW1.1; LATCH_PULLDOWN contains R2, Q2 drain and D3 anode.'),
                  pdf('processor/STM32N657X0_DS14791_datasheet.pdf', [96,138], 'PC13 is a TT input; Table 21 limits TT input voltage to 3.6 V in the 3.3 V range.'),
                  pdf('discretes/HUASHUO_AO3401A_datasheet_LCSC_copy.pdf', [2], 'AO3401A threshold magnitude 0.5-1.5 V, on-resistance specified at VGS=-2.5 V.')],
     'consequence': 'Full PFET turn-off would raise SHUTTER_SENSE toward the 8-13.2 V battery source, beyond PC13 rating. If input structures clamp near the powered 3.3 V domain, current through R1 instead sustains several volts of negative VGS and can keep the battery switch on. The exact clamp/injection waveform needs measurement, but the circuit cannot both turn fully off and keep PC13 within its allowed voltage range.',
     'quantitative_bounds': {'example_PC13_clamp_V':3.6,'example_D3_drop_V':0.6,'battery_V':[8,13.2], 'resulting_R1_drop_V':[3.454545,8.181818]},
     'recommendation': 'Separate battery-level latch actuation from MCU shutter sensing using an isolated second contact or a properly rated transistor/level-shift circuit. Verify powered-off, boot, release, repeated press and shutdown states before layout; an MCU pull-up or series resistor alone does not remove this latch interaction.'},
    {'id':'PWR-002','severity':'high','confidence':'confirmed',
     'title':'PFET gate divider has no absolute-maximum margin at fresh-cell voltage',
     'references':['Q1','Q3','R1','R2'],
     'observed':'At Q2 pull-down near 0 V, R1=1 MOhm and R2=100 kOhm set |VGS|=Vsource*R1/(R1+R2). At 13.2 V this is exactly 12.0 V; R1/R2 tolerances are unselected.',
     'evidence':[source(['Q1','Q3','R1','R2'],'Common-source PFET pair shares the gate divider; native Role Details explicitly uses the 13.2 V fresh stack bound.'),pdf('discretes/HUASHUO_AO3401A_datasheet_LCSC_copy.pdf',[1,2],'HUASHUO AO3401A absolute maximum VGS is +/-12 V, not +/-20 V.')],
     'quantitative_bounds': {'nominal_Vgs_magnitude_V':12.0,'with_1pct_opposed_resistor_tolerances_V':13.2*1.01/(1.01+.099),'with_5pct_opposed_resistor_tolerances_V':13.2*1.05/(1.05+.095)},
     'consequence':'Ordinary resistor variation can exceed the gate-oxide absolute maximum even without a transient. Equality to an absolute maximum is not an operating-margin design.',
     'recommendation':'Provide substantial gate-voltage margin. For example, R2=330 kOhm with R1=1 MOhm and 1% tolerances gives a DC worst case below 10 V at 13.2 V and about 6 V drive at an 8 V source. Alternatively choose an appropriately rated PFET/clamp scheme. Recheck source/gate transients and clamp leakage at the actual microampere bias; the example divider is a proposal, not an applied edit.'},
    {'id':'PWR-003','severity':'high','confidence':'confirmed',
     'title':'USB startup automatically reconnects the battery stack',
     'references':['U1','Q2','Q1','Q3','D2'],
     'observed':'U1 E2/PWR_ON directly drives Q2, which enables the common-gate PFET pair. PWR_ON automatically asserts during normal startup, including startup powered through USB. No VBUS-qualified inhibit exists in the battery hold path.',
     'evidence':[source(['U1.E2','Q2','Q1','Q3','D2'],'PWR_HOLD has only PWR_ON, Q2 gate and R3. D2 anode USB_VBUS, cathode SYS_IN.'),pdf('processor/STM32N6_AN5967_hardware_design.pdf',[13,15,16],'PWR_ON is the core/secondary-supply enable and asserts before firmware execution.'),pdf('processor/STM32N657X0_DS14791_datasheet.pdf',[89,112],'PWR_ON uses the VDD domain; VDD is 3.3 V in this design.')],
     'consequence':'With a normal 8-13.2 V stack present, the battery raises SYS_IN above USB voltage and reverse-biases D2, so USB download can drain the coin cells. Both conducting PFET channels are bidirectional; if stack voltage is below USB-powered SYS_IN, off-state reverse isolation no longer prevents current into the stack. Normal cells should not reach that condition, but no hardware inhibit enforces it.',
     'recommendation':'Add explicit USB-priority source selection and battery reverse-current control independent of PWR_ON. Coordinate this with the redesigned latch and mandatory MCU main/auxiliary sequencing. Keep the battery path disabled during USB-only download unless its use is intentionally requested.'},
    {'id':'PWR-004','severity':'blocker','confidence':'measurement',
     'title':'Four-CR2032 supply is unqualified for the stated system pulse power',
     'references':['BAT_PLUS','U2','C3','C4','C5','C6','C7'],
     'observed':'The source specifies four series CR2032 cells, 8-13.2 V, and a provisional 3.3 V peak load of 1.2 A. No production battery MPN or measured boot/capture/save current waveform is provided. The main reservoir is only 4x47 uF plus C3=22 uF nominal.',
     'evidence':[source(['U2','C3','C4','C5','C6','C7'],'U2 Role Details contains the 1.2 A provisional peak budget; capacitors are per-instance 22 uF and 47 uF values.'),pdf('reference/CR2032_Energizer_reference.pdf',[1],'Unselected reference candidate: 235 mAh rating at 15 kOhm; published pulse test is approximately 6.8 mA for 2 seconds. These are typical reference conditions, not a universal maximum-current rating.'),pdf('power/TI_TPS6213x_TPS62132_datasheet.pdf',[15,16],'Input/output capacitor selection and DC-bias reduction must be evaluated.')],
     'quantitative_bounds':{'load_W':3.96,'assumed_buck_efficiency':0.9,'ideal_input_current_A_at_13_2V':1/3,'ideal_input_current_A_at_8V':0.55,'nominal_reservoir_uF':210,'nominal_energy_J_to_zero':0.5*210e-6*3.3**2,'nominal_energy_J_3V3_to_3V0':0.5*210e-6*(3.3**2-3**2),'hold_time_s_3V3_to_3V0_at_3_96W':0.5*210e-6*(3.3**2-3**2)/3.96,'max_per_cell_Thevenin_resistance_ohm_at_12V_for_3_96W':12**2/(16*(3.96/.9))},
     'consequence':'At the provisional peak, each cell must carry roughly 333-550 mA before source sag. The 210 uF bank supports only about 50 microseconds between 3.3 and 3.0 V. Series cells multiply both voltage and resistance; the architecture cannot be qualified by the mAh number. This does not prove every CR2032 fails at the actual workload; that workload remains unmeasured.',
     'recommendation':'Before fixing battery mechanics or power routing, select a cell and measure boot, capture and complete NAND-save current over state of charge and temperature with realistic contacts. Replay that waveform on the cell stack and record rail minima and energy. If the source cannot sustain it, change battery chemistry/form factor, lower actual power, or design a deliberately charged energy reservoir with an honest startup-latency budget.'},
    {'id':'PWR-005','severity':'high','confidence':'confirmed',
     'title':'Power magnetics and MLCC footprints are placeholders without production limits',
     'references':['L1','L2','L3','C1','C3','C4','C5','C6','C7','C9','C10','C11','C15','C16','C17','C18'],
     'observed':'All three power inductors use generic 0603/1608 footprints and no MPN. L1 is 2.2 uH/4 A target, L2 0.47 uH/3 A target, L3 1 uH/2 A target. No DCR, RMS-current, inductance-vs-bias or actual body dimensions are specified. High-value MLCCs, including C1 10 uF/25 V 0603 and C4-C7 47 uF/6.3 V 0603, also lack MPN, dielectric/tolerance and DC-bias curves.',
     'evidence':[source(['L1','L2','L3','C1','C3','C4','C5','C6','C7','C9','C10','C11'],'Native per-instance component specifications and generated package choices.'),pdf('power/TI_TPS6213x_TPS62132_datasheet.pdf',[13,14,15,16],'Example 2.2 uH inductor is about 4x4 mm; 10 uF/25 V example input capacitor is 1210. These examples do not prohibit smaller qualified parts but show why generic footprints are not a selection.'),pdf('power/TI_TPS6282x_TPS62825_datasheet.pdf',[12,13,14],'Requires at least 3 uF effective input and 10 uF effective output; inductor selection includes saturation, DCR and size.')],
     'consequence':'The schematic values alone do not guarantee stability, current capability, stored energy or footprints that fit an orderable part. A 10 uF nominal MLCC does not establish a 10 uF effective-at-bias target.',
     'recommendation':'Select exact production magnetics and MLCCs before placement, verify effective L/C, RMS/saturation current and loss over the operating range, then replace generic footprints with manufacturer land patterns. Verify U2 LC transient response around its roughly 210 uF reservoir and downstream load. Do not claim the existing 0603 parts are impossible; they are presently unqualified.'},
    {'id':'PWR-006','severity':'high','confidence':'confirmed',
     'title':'MCU SMPS passive targets and local input bypass do not match the current reference requirements',
     'references':['U1','L3','C10','C11','C15','C16','C17','C18','C19','C26','C27','C28','C29','C30','C31','C32','C33','C34','C35','C59','C60','C61','R19'],
     'observed':'L3 is specified only for 2 A saturation and has no DCR limit. No dedicated VDDSMPS 2x1 uF plus 2x100 nF input bypass is identified; C10/C11 are allocated to the U7 output, and other 1 uF capacitors have VREF, camera or load-switch roles. The core bulk bank is 4x22 uF, while current ST references specify 4x15 uF typical and an output-impedance range.',
     'evidence':[source(['L3','C10','C11','C15','C16','C17','C18','C19','C26','C27','C28','C29','C30','C31','C32','C33','C34','C35','C59','C60','C61','R19'],'Per-instance values/roles, with all VDDSMPS balls connected to 1V8.'),pdf('processor/STM32N6_AN5967_hardware_design.pdf',[12,13],'Rev5 Table6 calls for L=1 uH +/-20%, Isat>3 A, DCR<60 mOhm; VDDSMPS bypass 2x10 uF+2x1 uF+2x100 nF; VLX damping 2.2 nF +2 Ohm and four 15 uF output capacitors.'),pdf('processor/STM32N657X0_DS14791_datasheet.pdf',[142,143],'Table27 external coil1 uH, Cout4x15 uF typical and output impedance16-33 mOhm; internal SMPS supports up to2.2 A.')],
     'consequence':'A part satisfying the existing 2 A target alone need not support the internal converter. Global 1V8 capacitance does not prove the required low-inductance SMPS input bypass. The 88 uF output bank is a deviation to validate, not a proven instability or overvoltage defect.',
     'recommendation':'Raise the L3 procurement requirements to the current ST limits and choose a qualified footprint. Allocate the complete local VDDSMPS bank; if sharing U7 output capacitors, justify placement/loop inductance and still supply the required local small capacitors. Select output MLCCs to meet ST impedance/transient requirements; check whether four15 uF or the existing88 uF bank is appropriate. Retain the correctly connected 2 Ohm/2.2 nF snubber and separate V08CAP capacitor.'},
    {'id':'PWR-007','severity':'medium','confidence':'confirmed',
     'title':'The stated 8 V battery discharge endpoint is not enforced',
     'references':['U2','BAT_PLUS','BAT_CELL1_TAP'],
     'observed':'U2 EN is tied to SYS_IN, with no battery-specific undervoltage divider/comparator. BAT_PLUS has no ADC divider; BAT_CELL1_TAP goes to RTC backup and test access rather than a cell-monitor input. The U2 power-good pins are not routed to control logic.',
     'evidence':[source(['U2.13','U2.4','R4','R7','U7.2','BAT_PLUS','BAT_CELL1_TAP'],'EN=SYS_IN; PG_3V3 and PG_1V8 each have only the regulator and their pull-up resistor.'),pdf('power/TI_TPS6213x_TPS62132_datasheet.pdf',[5],'U2 falling input UVLO is2.6-2.8 V, not an8 V battery cutoff.'),pdf('reference/CR2032_Energizer_reference.pdf',[1],'Reference-cell capacity is specified down to2.0 V per cell; actual selected-cell endpoint remains to be established.')],
     'consequence':'The converter can keep attempting operation far below the stated four-cell endpoint. Pack voltage alone also cannot distinguish one weak cell from three stronger cells. Collapse during a NAND write remains possible; a nominal 8 V assumption does not prevent it.',
     'recommendation':'Define the selected-cell discharge and pulse-sag policy, then implement battery monitoring/cutoff that can act before an unsafe or unreliable capture. Consider cell imbalance and startup pulse sag when choosing thresholds. Maintain power-fail-tolerant storage behavior; regulator PG outputs currently provide no warning to firmware.'},
    {'id':'PWR-008','severity':'medium','confidence':'measurement',
     'title':'Ten-year shelf life is not established by the PFET off-state leakage limits',
     'references':['Q1','Q3','Q2','U8'],
     'observed':'The shelf target is10+ years. The selected HUASHUO PFET permits1 uA drain leakage at25C and5 uA at55C at its specified test voltage. The series off path is not correctly modeled by adding two full IDSS limits, and actual leakage at this lower voltage may be smaller.',
     'evidence':[pdf('discretes/HUASHUO_AO3401A_datasheet_LCSC_copy.pdf',[2],'IDSS maxima1 uA at25C and5 uA at55C, VDS=-24 V; gate leakage100 nA at|VGS|12 V.'),pdf('reference/CR2032_Energizer_reference.pdf',[1],'Unselected reference capacity235 mAh and typical self-dischargeabout1% per year.'),source(['Q1','Q3','Q2','U8'],'Common-source power isolation and single-cell RTC tap.')],
     'quantitative_bounds': {'charge_mAh_at_1uA_for_10_years':87.6,'charge_mAh_at_5uA_for_10_years':438,'reference_self_discharge_equivalent_uA_first_year':235*.01/8760*1000},
     'consequence':'Even1 uA sustained for10 years consumes87.6 mAh, about37% of the candidate235 mAh rating before captures and self-discharge. Maximum datasheet limits cannot support a10-year guarantee by themselves. The existing D3 defect must be fixed before leakage measurement is meaningful.',
     'recommendation':'Set a complete off-state current budget, qualify a selected cell and isolation devices over temperature, and measure cleaned/contaminated assembled-board leakage with all interfaces absent/present as appropriate. RTC single-cell loading must be included when evaluating imbalance.'},
]

result = {'scope':'Power architecture, latch and source selection, battery feasibility, regulator and MCU-SMPS passive review; no schematic edits',
          'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['hardware/reconstruction/schematic-connectivity.json','imports/flux/2026-09-05/bigjosh-global-x-camera.flx']},
          'findings':findings}
(OUT/'power-findings.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('Wrote',len(findings),'power findings')
