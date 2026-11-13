# Exposure knob RAM smoke test

**November10 hardware addition:** the ASA knob is wired high end to **A4 /
CN4.5 / PC12**, low end to **GND**, and wiper to **A5 / CN4.6**, through the
onboard buffer to **PG15 / ADC1 input7**. It will control sensor **analog gain**;
the existing policy is 1×–8× analog with digital gain fixed at 1×. ASA scale
calibration remains pending. This schema5 helper still exercises **exposure
only** and does not excite A4 or sample A5. Future ASA code must keep PH2/A5
input/no-pull and switch PC12/A4 HIGH only for settling/sampling, then LOW.
Do not reuse the old A3–A5 diagnostic: it drives suspect A3 and the new
ASA wiper. See the [canonical wiring and decision](../../docs/prototype/NOTES.md#2026-11-10--put-the-asa-analog-gain-knob-on-a4-a5-and-ground).

The current schema5 diagnostic retains the A0–A2 exposure wiring and moves
HOLD to D8 following the user's November13 follow-up selection. This is a
source-only substitution; no new diagnostic build or tests were requested.

| Knob connection | Arduino contact | MCU function |
|---|---|---|
| Low track end | A0 / CN4.1 | PF5 push-pull LOW |
| Wiper | A1 / CN4.2 | PA9, ADC1 input10 through the onboard divider/buffer |
| High track end | A2 / CN4.3 | PF6 push-pull HIGH |
| Power HOLD | D8 / CN14.1 | PD12 push-pull HIGH throughout the diagnostic and terminal park |

PC10, A1's digital companion, is input/no-pull. PA9 is analog/no-pull.
The diagnostic also samples the conditioned A0 low endpoint through
PA8/ADC1 input5 and A2 high endpoint through PA10/ADC1 input11. These
companions are explicitly analog/no-pull. Suspect PA2/A3 and its buffered
PA12 companion are left untouched; neither is driven by this helper.
Each channel change follows
HAL_ADC_Stop → ConfigChannel → Start → Poll → GetValue, preserving the
calibration factors. A1 is sampled last, so its register snapshot stays current.
ADC12 is explicitly configured secure before ADC initialization to match the
already-secure analog GPIOs. Otherwise the MCU leaves their analog switches
open even though register access and internal-reference conversion succeed.
The setup preserves GPIO security, privilege settings and all other resource
attributes; its before/after record is at `0x343C2300`. See [the reason and
controlled experiment](NOTES.md).

Historical evidence: the November8 schema2/v11 warm RAM run observed A3=3–4, A5=3841 and A4 moving
through0–3841, with the user confirming normal knob operation. That run
inherited the VREFBUF peripheral clock enabled during an earlier diagnostic.
It verifies the security fix and warm sampling; a fresh cold launch of the
clean default has not been separately qualified. The A0–A2 hookup has its
own November9 validation below. See the
[diagnosis archive](evidence/2026-11-08-diagnosis/).
Schema5 assumes the default fitted SB9/SB8/SB7 routing for A0/A1/A2; no
solder-bridge or I2C routing change is needed. Historical schema1/2 manifests,
records and source copies, including schema3 PA2 HOLD, retain their original
meanings and are not rewritten.
The 3.3 V header voltage must not be applied to an unconditioned ADC pin.

`build.py --out <new-directory>` builds offline using the saved CubeN6 SDK
and local GNU Arm compiler. The resulting manifest binds code and copied
sources. No hardware API is imported. Building or launching this RAM helper
does not change normal capture firmware or NOR. A build alone does not prove
a successful bench run.

Launch only from the existing reviewed RAM bridge after confirming the
exact UART recovery park and idle camera/storage. The probe checks the
inherited 400 MHz CPU clock profile, disabled caches/interrupt context,
and disabled CSI/DCMIPP/SDMMC2 clocks before ADC work. It asserts PD12/D8 HOLD
before its checks, preserving power if the experimental latch is fitted.

The excitation pins PF5/PF6 and HOLD PD12 use main VDD. Schema5 neither
checks nor changes VDDIO4 voltage selection, monitoring or isolation.
It monitors the ADC analog supply for ready (bounded20ms wait),
releases analog supply isolation via PWR ASV, selects ADC HCLK/32,
uses 12-bit single-ended software-triggered ADC1 channel10 with1499.5-cycle
sampling, and runs the vendor's bounded calibration routine. Calibration
can reduce usable analog full range; CALFACT is reported. These readings
are direct ADC conversion codes, with no knob-to-exposure mapping or
voltage-accuracy claim. A generous10ms excitation-settling delay precedes
sampling. There is no optimization of settling or power in this diagnostic.

The prior VDDIO4 supply-monitor limitation remains relevant to historical
schema1/2 runs, not to these main-VDD excitation pins.

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
- Status:64words at`0x343C2000`, manifest lists fields in order.
  Status magic`0x31434441`, version5, request nonce;
  STATE4means sampling,8means clean stopped,15means failure.
- For approximately10Hz sampling use maximum6000and period100.
- The host reads the256-byte status once and accepts a sample only when
  `SEQUENCE` equals the trailing sequence at word63 and both are even.
  RAW, MIN_RAW, MAX_RAW, SAMPLE_COUNT, MILLISECONDS and register
  snapshots are published together. The 12-bit digital full-scale is4095;
  actual end stops depend on supplies, conditioning, calibration and wiring.
  Schema5 pin-specific fields: word24/25 are PF5/PF6 digital endpoint
  levels,29–31 are PD12 HOLD IDR/whole-port GPIOD MODER/ODR,
  54/55 are A0_RAW/A2_RAW,56–59 their extrema,60 is ENDPOINT_VALID,
  61 is reserved and62 is A1's PC10 digital level. The manifest names each
  field explicitly; do not decode an old status record with this schema.
- To stop, write`0x504F5453` to request word7(`0x343C1F1C`).
  The firmware stops the ADC, drives A2 LOW and parks awake with PD12/D8 HIGH.
  Sample-limit expiry follows the same path.
- Error codes:1invalid request,2context,3clock profile,4camera/storage active,
  5DWT unavailable (6/7 belong only to older VDDIO4 diagnostics),
  8ADC analog supply not ready,10ADC init,11channel config,12calibration,
  13start,14conversion timeout,15stop,20RIFSC clock unavailable,
  21analog GPIO security mismatch,22ADC security configuration refused;
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
against4096 randomized register states and five refused-configuration cases.
It verifies preservation of unrelated resource/pin attributes and checks that
mandatory security setup precedes ADC initialization/calibration. This native
MMIO simulation supplements the hardware experiment; it does not model analog
behavior or establish electrical accuracy. The pin test executes the actual
output/setup/terminal-excitation code against4096 randomized GPIO states,
checking that PD12 HOLD and unrelated pins, including PA2, are preserved.
The host-contract test rejects schema1–4 or mismatched wiring for any new
launch/replacement. Package tests bind the HOLD schema to the exact early
hook bytes: the PA2, PE9 and PD12 hooks share an entry address, so that
address alone cannot identify the pin. Existing regression expectations are
remapped but were not run for D8, as requested.

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
reviewed D8 package, build the schema5 diagnostic and use its exact SHA:

```powershell
python firmware/control-smoke/console.py launch --cli <programmer.exe> --package <exact-reviewed-D8-package> --build <schema5-build> --sha256 <build-sha256> --samples 6000 --out tmp/new-a1-knob-run
```

New launches/replacements require schema5 and the D8 pin map; replacement
also requires the old running helper to use that map. Monitoring frozen
schema1–4 remains supported with the historical labels. A mismatch refuses
entry; do not bypass its identity checks. The earlier schema3 November9 live
launch, full knob sweep and clean stop are recorded in
[the live evidence](evidence/2026-11-09-a3-live/README.md).

`console.py monitor --cli <programmer.exe> --session <run-folder>/session.json
--out <new-console-folder>` prints raw A1, min/max, sample count, endpoint
logic levels and error state, saving JSONL and the latest snapshot. Host
updates are slower than the MCU's10Hz sampling. This console owns ST-LINK
while open; close it before another debugger client. Ctrl+C stops monitoring
only, not the MCU diagnostic. The stop mailbox above ends the diagnostic
without resetting the board. A legacy session displays its own A3/A4/A5
labels from the earlier schema rather than relabelling historical telemetry.
The diagnostic does not change normal camera FLASH.

D8/PD12 is also the former phase-marker pin at CN15.21. Capture firmware
must disable that marker when D8 HOLD is selected; the control helper does
not emit phase markers. Its ADC security and A0–A2 sampling are unchanged.
