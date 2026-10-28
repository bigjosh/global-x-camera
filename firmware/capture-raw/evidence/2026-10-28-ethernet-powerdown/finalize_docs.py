"""Record completed checks and final bench state; no hardware operations."""
from pathlib import Path
import json
H=Path(__file__).resolve().parent;R=H.parents[2]
f=json.loads((H/'final-state.json').read_text());assert f['normal_flash_restored']
summary=json.loads((H/'cold-images-readback/summary.json').read_text());assert summary['passed']
rows=[]
for slot in (123,124,125,127,128,129):
    v=json.loads((H/f'cold-images-readback/slot-{slot}/readback-validation.json').read_text())
    assert v['passed'] and v['full_slot_read'] and v['png_samples_match_read_raw']
    assert not v['original_sensor_frame_comparison']
    rows.append(f"| {slot} | {'baseline' if slot<126 else 'Ethernet off'} | {v['minimum_sample']}–{v['maximum_sample']} | `{v['raw_sha256']}` |")
with (H/'README.md').open('a',encoding='utf-8') as out:
    out.write('\n## Completion addendum\n\nAll six measured cold images passed complete 3,730-sector readback at 25 MHz,\nstart/end markers and independent PNG sample decoding. These post-Standby\nimages cannot be compared with original RAM, which was lost in Standby.\nThe separate awake trials above provide that exact source equality.\n\n| Slot | Firmware | Sample range | RAW SHA256 |\n|---|---|---|---|\n'+'\n'.join(rows)+'\n')
    out.write(f"\nThe board was returned to a normal cold boot of the new installed firmware.\nAll ten phase markers appeared; the final low plateau was **{f['low_plateau']['current_mean_mA']:.3f} mA**.\nJS closed cleanly at **{f['logger_closed_utc']}**, restored its starting settings\nand left output enabled. COM8 is closed/BREAK released; no helper remains\nactive after the finalization script exits. Expected extra slot 130 was proven\nFREE before this final boot but was not reread afterward. This final state is\na phase/current observation, not a fresh SBF or final-photo proof. The three\nmeasured candidate photos and prior retained Standby flags provide the\ncomplete qualification above. No firmware changes followed the verified NOR\ninstallation.\n")
checkpoint=f"""**Latest checkpoint — Ethernet power-down normal firmware qualified, October 28, {f['logger_closed_utc']}:** user reconnected camera/SD and confirmed lit scene. New normal four-bit25MHz capture/RAW-save/Standby firmware is installed, build `tmp/bringup/ethernet-normal-20261028/flash-candidate`, receiver `69c5a5c0cc434eb7496371d9e5b9c007db346b8bb7b9a1a650c90f0eade79d28`, sector `a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645`, prefix `2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344`. Independent physical64KiB readback matched; following4KiB unchanged. PHY power-down runs once after camera arm; its bounded warnings do not fail the photo. All recovery instructions/literals and relocated error engine remain unchanged. [Evidence, build and limits](firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown/README.md).

Three baseline and three candidate cold cycles completed. Median qualified post5ms energy224.824→173.653mJ (22.8% lower), median onset-to-plateau396.120→413.880ms, transport mean-power median603.393→431.933mW; first-strobe median24.980→24.966ms. Initial5ms/full-cycle inrush remains unqualified, card timing varies, and no LTC/battery loss is included. Baseline slots123–125 and candidate127–129 passed all3730sectors at25MHz and independent PNG decoding; originalRAM is lost afterStandby. Separate awake122/126 passed original-RAM equality and recognizable previews. CandidatePHY3000→3800 verified twice,5.319825ms, pins/clocks restored. Host CONTROL0xC false rejection corrected without repeating the successful capture. 223capturetests/14reader-recoverytests passed; warmUART exactpark checks passed9good/0bad after each measuredcoldcycle; guardedSBF1/PDDS1/STOPF0 aftercandidate3 with generic`trial_entry_proven:false` retained.

**Final target is powered after a normal cold boot, not a RAM helper**, with all10markers and {f['low_plateau']['current_mean_mA']:.3f}mA low plateau. Extra expectedslot130 was provenFREE beforehand but not reread; finalSBF not reread. JS closed cleanly/restoredrange128,streams,EXTIOsettings and leftoutputon; COM8closed/BREAKreleased, noactivebenchhelper. NoSDerase/deletion. Wiring: bench5V→JSIN+→JSOUT+CN5.5,returnCN5.6; CN8/LTCdisconnected,CN9shuntsabsent,CN10separatelypowered,D2/R23removed,U24fitted,JP1/JP2normal. JSIN0CN15.21/PD12,IN1CN15.33/PD0,GPIOGNDCN15.20. SDtwistedCLK/GND CN3.3/CN3.8,VCCCN3.5/main3V3,noresistor/signalsprobes. No physical change pending. Recheck ownership/live state before future hardware work. Earlier active/isolated checkpoints below are historical.

"""
p=R/'AGENTS.md';text=p.read_text(encoding='utf-8-sig');marker='# Instrument access\n\n'
assert marker in text and 'Latest checkpoint — Ethernet power-down normal firmware qualified' not in text
p.write_text(text.replace(marker,marker+checkpoint,1),encoding='utf-8')
print('Completed report and final bench checkpoint recorded')
