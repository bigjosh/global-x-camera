# Exposure and ASA knob RAM smoke test

The current **schema6** helper reads both physical controls in one coherent
RAM record while holding **D8 / CN14.1 / PD12 HIGH**. This is a diagnostic
only: normal capture exposure and analog gain integration remain deferred.
A3/PA2 is suspect and remains untouched, as does its PA12 analog companion.

| Connection | Header / pin | Diagnostic behavior |
|---|---|---|
| Exposure low | A0 / CN4.1 / PF5 | Driven LOW |
| Exposure wiper | A1 / CN4.2 | PC10 input/no-pull; buffered PA9 / ADC1 channel10 |
| Exposure high | A2 / CN4.3 / PF6 | Driven HIGH while sampling, LOW at completion/error |
| ASA low | GND | Fixed board ground |
| ASA wiper | A5 / CN4.6 | PH2 input/no-pull; buffered PG15 / ADC1 channel7 |
| ASA high | A4 / CN4.5 / PC12 | Driven HIGH while sampling, LOW at completion/error |
| Power HOLD | D8 / CN14.1 / PD12 | HIGH throughout, including terminal awake park |

The onboard divider/buffer routes are verified from official MB1940C02
sheet10. The helper also samples exposure endpoints PA8/channel5 and
PA10/channel11, and the ASA high endpoint **PF3/channel16**. It does not use
PA13 for the ASA endpoint. Only the named analog companions become analog
inputs; unrelated modes and pull resistors are preserved.

PC10, PC12 and PH2 use VDDIO4. This helper requires the stock **3.3V bank**,
rejects an inherited1.8V voltage selection and sets only VDDIO4 supply-valid.
It does not wait for VDDIO4 PVM-ready: ES0620 section2.2.29 says that monitor
is not operational, so its status cannot qualify the rail. PF5/PF6, PD12 and
PG15 use main VDD. No physical rail or jumper changes are made.

ADC12 is explicitly secure before ADC initialization, matching the existing
secure analog GPIOs. The setup checks PA8/PA9/PA10, PF3 and PG15 security;
it changes only ADC12's RIF SEC2 bit0, preserving GPIO security and privilege.
Otherwise the external analog switches can remain open even when internal
reference conversions work. Its14-word before/after record is at0x343C2300.
The board externally supplies VREF+ through R146; internal VREFBUF output
must not be enabled against that supply. See [the diagnosis](NOTES.md).

`build.py --out <new-directory>` builds offline with the saved CubeN6 SDK.
The manifest binds code and frozen source copies; no instruments are used.
Launch requires the exact current D8 package's verified early UART park and
the reviewed SRAM bridge. The helper checks the inherited400MHz clock and
uncached interrupt context, and refuses active camera/storage clocks. HOLD
is asserted before those checks. It sends no camera, card or NOR commands.

Both supplies start LOW, then go HIGH after ADC calibration. A generous10ms
settling interval precedes repeated batches of A0, A2, A4, A1 and A5 reads.
Each channel follows Stop → ConfigChannel → Start → Poll → GetValue; A5 is
last, so the ADC register snapshot describes A5. Each batch is published
under one equal-even sequence fence. The channels are sequential, not truly
simultaneous. HCLK/32,12-bit mode and1499.5-cycle sampling are unchanged.

The console shows raw codes/extrema and electrical position fractions:
exposure=(A1−A0)/(A2−A0), ASA=(A5−A0)/(A4−A0). A0 approximates common ground
for ASA; neither fraction is an exposure or calibrated ASA value. Values
outside0–100% remain visible rather than being clipped. Invalid endpoint
span reports an invalid fraction. CW/center/CCW observations can establish
polarity/endpoints and reveal an obvious taper, not characterize a full curve.

Schema1–5 manifests and frozen records retain their historical meanings and
can still be monitored. New launches and replacements require schema6 with
the exact two-knob map. Package HOLD remains schema5/PD12; it is separate
from this diagnostic's telemetry version6. Do not run the old A3–A5 helper:
it drives the suspect A3 pad and the new ASA wiper.

## November9 live qualification

The remapped schema3 diagnostic was launched through the exact installed
PA2 native-PTP package and the reviewed SRAM bridge. With the camera absent,
the user's full knob sweep produced **A1 raw 0–3840**, with subsequent readings
near 1999–2004. The full run recorded A0 near ground (extrema 0–6), A2=3840,
PA2 HOLD HIGH, and no HAL or CPU faults. The cooperative stop reached STATE8,
disabled ADC excitation and independently confirmed PF6/A2 LOW while PA2/A3
remained HIGH. The [live evidence](evidence/2026-11-09-a3-live/README.md)
contains the bound executable, launch guards, readings and stop snapshots.

The same campaign installed and readback-verified the combined PA2 package's
two NOR regions and preserved the following 4 KiB. Exact UART recovery passed
after installation, after the diagnostic and after a separate power cycle.
With no camera and no CN8 USB connection, that normal boot reported the
expected sensor-initialization failure and later reached a 3.2055 mA plateau.
Retained SBF=1/PDDS=1/STOPF=0 was observed after UART recovery; the flag reader
retains `trial_entry_proven:false`. No external HOLD probe was qualified, so
neither the physical release edge nor the external latch's timing is measured.

This validates the relocated control wiring and RAM diagnostic, not automatic
exposure adjustment in normal captures: **normal exposure remains fixed**.
It also does not establish ADC voltage accuracy, a new cold-start ADC baseline,
camera/image operation with this hookup, or USB-host behavior in this campaign.
The final recorded target state is **Joulescope output OFF**, measured input
current zero, with settings restored and no active console/helper. Camera and
CN8 were absent; CN10 was connected and target power came from direct 5 V through
the Joulescope. This checkpoint is historical; recheck actual connections and
ownership before the next launch.

## SRAM host interface

- Code/vectors: `0x34300000`; exact entry and terminal park in manifest.
- Stack: `0x343AF000` through `0x343B0000`.
- Request: eight32-bit words at `0x343C1F00`:
  magic`0x31544F50`, nonzero nonce, maximum sample count(1–36000),
  period in milliseconds(20–1000), zero, zero, zero, stop command(initially0).
- Status:96words at`0x343C2400`, manifest lists78 named fields in order;
  unused words78–94 remain reserved, word95 is the sequence end.
  Status magic`0x31434441`, version6, request nonce;
  STATE4means sampling,8means clean stopped,15means failure.
- For approximately10Hz sampling use maximum6000and period100.
- The host reads the384-byte status once and accepts a sample only when
  `SEQUENCE` equals the trailing sequence at word95 and both are even.
  RAW, MIN_RAW, MAX_RAW, SAMPLE_COUNT, MILLISECONDS and register
  snapshots are published together. The 12-bit digital full-scale is4095;
  actual end stops depend on supplies, conditioning, calibration and wiring.
  Schema6 retains these pin-specific fields: word24/25 are PF5/PF6 digital endpoint
  levels,29–31 are PD12 HOLD IDR/whole-port GPIOD MODER/ODR,
  54/55 are A0_RAW/A2_RAW,56–59 their extrema,60 is ENDPOINT_VALID,
  61 is reserved and62 is A1's PC10 digital level. The manifest names each
  field explicitly; do not decode an old status record with this schema.
  Words63–65 are ASA raw/min/max;66–68 are A4 raw/min/max;69/70 are
  A4/A5 digital levels;71/72 GPIOG/H modes;73 ASA channel7;74 batch-start ms;
  75 total sampling-batch cycles;76/77 cumulative cycles from batch start
  through exposure/ASA wiper completion. Divide cycles by400MHz for time;
  these are cumulative markers, not isolated channel-conversion durations.
- To stop, write`0x504F5453` to request word7(`0x343C1F1C`).
  The firmware stops the ADC, drives A2 and A4 LOW and parks awake with PD12/D8 HIGH.
  Sample-limit expiry follows the same path. The final stored GPIO snapshot
  precedes excitation shutdown, so use a direct pin/register read to verify
  the resulting LOW supplies; do not mistake that historical HIGH snapshot
  for a failure to stop.
- Error codes:1invalid request,2context,3clock profile,4camera/storage active,
  5DWT unavailable (6/7 belong only to older VDDIO4 diagnostics),
  8ADC analog supply not ready,10ADC init,11channel config,12calibration,
  13start,14conversion timeout,15stop,20RIFSC clock unavailable,
  21analog GPIO security mismatch,22ADC security configuration refused,
  23VDDIO4 is configured for1.8V,25supply-valid refused;
  `0xF000|IPSR` means fault.
  FAIL_STAGE retains the preceding state, and CFSR/HFSR/HAL error are saved.

The helper sends no SD/NOR/camera commands, makes no reset or power-switch
request, and never enters Standby. It does not use the recovery UART, so the
local console can display SRAM readings via ST-LINK without occupying COM8.
RAM residency ends on reset/power loss; the unchanged FLASH program then boots.

This makes no promise that the external HOLD circuit bridges an NRST/reset
interval. The root bench owner must establish actual supply and recovery
conditions before launch and record the final hardware state afterward.

## Diagnostic options and regression check

The normal diagnostic uses HCLK/32 and mandatory ADC12 security alignment.
The following retained options isolate earlier hypotheses and are off by default:

- `--vrefbuf-clock` enables the VREFBUF peripheral clock and verifies external
  reference mode (`ENVR=0,HIZ=1`). It never enables the internal reference output.
  Word53 records CSR before and after, low16/high16 respectively. Errors16/17
  report a refused clock or mode. The board supplies VREF+ through fitted R146.
- `--adc-hsi8` selects the already-running HSI divided by8 for ADC only. It
  changes neither the HSI divider nor system clocks. Four words at `0x343C2100`
  report HSICFGR, RCC SR, nominal ADC frequency and CCIPR1. Errors18/19 report
  HSI not ready or a refused selector/divider.
- `--internal-vref` also samples ADC1 channel17 after a10ms initial settling
  interval. This N6 reference is0.8V typical. Sixteen words at `0x343C2200`
  report the result, extrema, count and register context; words1/15 are the
  equal-even sequence check. The manifest gives the complete layout.

`python -m unittest discover -s firmware/control-smoke -p "test_*.py" -v`
includes the actual security setup
against4096 randomized register states and seven refused-configuration cases.
It verifies preservation of unrelated resource/pin attributes and checks that
mandatory security setup precedes ADC initialization/calibration. This native
MMIO simulation supplements the hardware experiment; it does not model analog
behavior or establish electrical accuracy. The pin test executes the actual
output/setup/terminal-excitation code against4096 randomized GPIO states,
checking that PD12 HOLD and unrelated pins, including PA2, are preserved.
The host-contract test rejects schema1–5 or mismatched wiring for any new
launch/replacement. Package tests bind the HOLD schema to the exact early
hook bytes: the PA2, PE9 and PD12 hooks share an entry address, so that
address alone cannot identify the pin. All13 focused tests passed for the schema6 build, including historical/new
telemetry extents, coherence fencing and endpoint normalization. No capture or
USB regression campaign is implied.

## Local console

`console.py launch --cli <programmer.exe> --package <exact-D8-package>
--build <frozen-build> --sha256 <hash>
--out <new-run-folder>` checks the exact installed UART park, executes the
existing reviewed SRAM bridge, verifies the full diagnostic readback and
starts the RAM test. It does not send UART recovery itself. The default
36000 samples at100ms expire after approximately one hour.

For an installed native PTP package, supply **`--package <exact-package>`**.
This checks its prefix and sector against the independent admission in
`firmware/usb-ptp/recovery.py`, checks both recovery copies, then runs that
tool's fresh live UART/context verifier. It sends no recovery stimulus or
reset itself. Unknown packages remain refused; this launcher cannot add an
allowlist entry. New D8 launches require an exact D8 package; historical PA2/PE9
packages remain inspectable but cannot launch this current helper.

After the exact early park, the unchanged hash-pinned SRAM bridge is used.
Before any bridge write, the host confirms ADC12, USB, SD and camera clocks
are disabled. The package's explicit HOLD contract determines the port and
pin; current schema5 selects GPIOD/PD12. Its exact early-hook hash must agree
with that contract. The launcher confirms mode, pull, ODR and IDR show HOLD
driven HIGH and checks its GPIO clock before each read, before and after
the bridge. The bridge contains no sensor/card/NOR command, so a physically
disconnected camera does not prevent this ADC diagnostic. This does not
qualify camera capture or the external latch's reset hold-up.

After independently establishing UART recovery and admitting the exact
reviewed D8 package, build the schema6 diagnostic and use its exact SHA:

```powershell
python firmware/control-smoke/console.py launch --cli <programmer.exe> --package <exact-reviewed-D8-package> --build <schema6-build> --sha256 <build-sha256> --samples 6000 --out tmp/new-a1-knob-run
```

New launches/replacements require schema6 and the dual-knob/D8 pin map; replacement
also requires the old running helper to use that map. Monitoring frozen
schema1–5 remains supported with the historical labels. A mismatch refuses
entry; do not bypass its identity checks. The earlier schema3 November9 live
launch, full knob sweep and clean stop are recorded in
[the live evidence](evidence/2026-11-09-a3-live/README.md).

`console.py monitor --cli <programmer.exe> --session <run-folder>/session.json
--out <new-console-folder>` prints raw A1 and A5, both min/max and normalized positions, sample count,
endpoint levels, batch timing and error state, saving JSONL and the latest snapshot. Host
updates are slower than the MCU's10Hz sampling. This console owns ST-LINK
while open; close it before another debugger client. Ctrl+C stops monitoring
only, not the MCU diagnostic. The stop mailbox above ends the diagnostic
without resetting the board. A legacy session displays its own A3/A4/A5
labels from the earlier schema rather than relabelling historical telemetry.
The diagnostic does not change normal camera FLASH.

D8/PD12 is also the former phase-marker pin at CN15.21. Capture firmware
must disable that marker when D8 HOLD is selected; the control helper does
not emit phase markers. Its ADC security fix is retained and extended to the new ASA analog pins.

The [November13 dual-knob calibration](evidence/2026-11-13-dual-knobs/README.md)
records the live CW/center/CCW readings, clean excitation-off stop and repeated
UART recovery. Exposure voltage increases clockwise and ASA voltage increases
counterclockwise. Three manually positioned samples support approximate taper;
they do not establish full angle calibration or absolute ASA sensitivity.
