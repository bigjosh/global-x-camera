# Control-input diagnostic notes

The [root notes](../../NOTES.md) define the append-only convention. This folder
owns the RAM-only control-input probe and its ADC bring-up constraints; capture
firmware behavior and physical control choices retain their existing homes.

## 2026-11-08  Match ADC12 security to secure GPIOs before external conversions

**Why:** STM32N6 GPIOs reset secure, while ADC12 remained nonsecure in the
minimal boot environment. RM0486 section15.3.16 specifies that this combination
leaves the external analog switches open. ADC register access, calibration and
the internal0.8V reference still worked, misleadingly suggesting a healthy
external conversion path. The controlled security-only change restored the
ground/high endpoint readings and a moving wiper. The diagnostic now always
sets only ADC12's security bit, verifies it and leaves GPIO security, privilege
and every other peripheral attribute unchanged.

**Rejected:** interpreting successful HAL conversion calls as proof that an
external pad is connected; compensating the floating readings in software;
changing board wiring, VREFBUF output, ADC clock, calibration or VDDIO2 supply
selection to fix this isolation. Enabling the VREFBUF peripheral clock and
switching ADC to HSI/8 were separate negative experiments. Those options remain
explicit diagnostics, not required parts of the fix. VREF+ is externally supplied
through R146, so internal VREFBUF output must not be enabled concurrently.

**Evidence:** [diagnosis archive](evidence/2026-11-08-diagnosis/);
[RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf),
Rev4 section15.3.16 pp791–792; official
[ADC example SystemIsolation_Config](https://github.com/STMicroelectronics/STM32CubeN6/blob/main/Projects/NUCLEO-N657X0-Q/Examples/ADC/ADC_MultiChannelSingleConversion/FSBL/Src/main.c).
Before the change, GPIOA/F/G SECCFGR were0xFFFF and RIFSC RISC_SECCFGRx[2]
was0. After setting only bit0, A3 measured2–3 codes, A5 measured3840 and A4
about2900 at the then-current knob position. Internal VREFINT had already
measured1819–1825 codes with the user's1.79V VREF+ reading. The controlled
v10 build SHA256 was`5a110e38a77486684a056c8ad45cf63307f41f6ca5864f912da9911d7c182f8a`;
the clean HCLK/32 v11 diagnostic is
`3bed14f57abf64211d5ea8794cacf45741797c6163c42b3abf8ae1bfddefc86a`.
The source-executing [offline regression](test_adc_security.py) covers4096
preservation cases and five refusal paths. Exact live evidence and final bench
state belong to the root-owned experiment record; no NOR change is implied.

## 2026-11-08  Keep warm ADC verification separate from default cold-start qualification

**Why:** the clean v11 diagnostic retained HCLK/32 and removed the optional
internal-reference measurement and VREFBUF-clock write, but it inherited the
enabled VREFBUF peripheral clock from an earlier warm diagnostic. Its successful
full knob sweep proves warm operation, not that this clock can be absent after
a cold boot. This qualifies the preceding entry's rejection of clock changes as
the cause: the security-only change is causally demonstrated, while a separate
clock dependency has not been excluded by a fresh cold test.

**Rejected:** declaring VREFBUF clock unnecessary from the v11 result, claiming
cold-start qualification or installing a new camera FLASH image as part of this
RAM-only smoke test. Further bench changes are deferred after the user's
confirmation that the control now works.

**Evidence:** root-owned v11 warm run measured A3=3–4, A5=3841 and A4 min0/max3841;
the user measured TP9 following the wiper and confirmed normal operation.
The [diagnosis archive](evidence/2026-11-08-diagnosis/) records the executable,
telemetry and live-console handoff. The source-executing regression and v11
build identity are recorded in the preceding entry.

## 2026-11-09  Move the diagnostic to A0–A2 without ever lowering A3 HOLD

**Why:** the user moved exposure to A0 LOW/A1 wiper/A2 HIGH and assigned A3
to the power latch. The former diagnostic actively drove A3 LOW, so reusing
it unchanged would remove HOLD. The new diagnostic asserts PA2/A3 before
request validation, drives only PF5/PF6 for excitation, samples PA9/ADC1
input10 and keeps PC10 input/no-pull. PA8/input5 and PA10/input11 provide
endpoint checks; PA12, A3's buffered companion, remains analog/no-pull.
PF5, PF6 and PA2 use main VDD, so the former VDDIO4 checks/monitor writes are
removed. All completion/error paths remove only A2 excitation and keep HOLD
asserted for awake debugger access. ADC security alignment remains mandatory.

**Rejected:** silently relabelling schema2 readings, using the old A3-low
binary on the new hookup, driving the wiper's raw companion, applying the
old VDDIO4 excitation assumptions, or claiming new bench qualification from
the prior A4 knob sweep. Schema3 and its manifest name the new pin-specific
telemetry; historical builds remain readable, but new launch/replacement
rejects old-schema or mismatched wiring. The historical launcher is not
automatically compatible with the later installed native PTP recovery path.

**Evidence:** current `control.c`, `build.py`, `console.py` and README;
`test_control_pins.py` executes the actual setup/output/stop code over4096
randomized GPIO states and checks the host schema gate; `test_adc_security.py`
retains4096 security-preservation cases and five refusal paths. Root's board
pin audit identifies A0 PF5/PA8, A1 PC10/PA9, A2 PF6/PA10 and A3 PA2/PA12;
the user explicitly confirmed the low/wiper/high order on November9. The
new builds are offline artifacts under `tmp/bringup/control-a0-a2-20261109/`;
no instrument, NOR or SD action occurred in this migration.

## 2026-11-09  Launch the knob diagnostic through the exact installed USB package guard

**Why:** after native PTP installation, the historical October28 launcher
rejects the longer installed prefix even though the original UART park and
SRAM bridge remain unchanged. The new `--package` route delegates the live
guard to the existing USB recovery verifier, requires its independent exact
admission, binds package/recovery copies and then uses the same frozen
1,324-byte SRAM bridge. Before mutation it checks ADC12/USB/SD/camera clocks
off. The PA2 package additionally requires HOLD HIGH before and after the
bridge. The disconnected sensor is not a dependency of this ADC-only path.

**Rejected:** globally widening the historical allowlist, trusting only a
self-consistent new manifest, reusing a stale park result, bypassing the
bridge's context checks, resetting an active device from this launcher, or
assuming unchanged pin modes without checking them after the bridge. The
launcher adds no recovery admissions or reset/power/NOR/SD commands.

**Evidence:** `console.py`, `test_package_launch.py`, and the exact archived
[PA2 package](../usb-ptp/evidence/2026-11-09-a3-hold/README.md). Eight offline
diagnostic tests passed, including corrupted package/recovery-copy refusal,
every forbidden peripheral-clock bit, PA2 mode/pull/output/input failures
and launch ordering. Hardware execution and final target state remain owned
by the root bench campaign; preparing this launcher accessed no instruments.

## 2026-11-09  Qualify the relocated knob independently of capture and latch timing

**Why:** the camera was physically disconnected during the user's requested
HOLD/knob/recovery smoke test. The package-aware launcher could exercise the
A0–A2 ADC path without a sensor, using the exact installed early UART park and
the unchanged SRAM bridge. The full sweep and endpoint readings now provide
hardware evidence for schema3 rather than borrowing the old A4 result. Its
cooperative stop deliberately leaves PA2 HOLD HIGH while removing PF6/A2
excitation, preserving debugger access instead of testing power shutdown from
inside the ADC helper.

**Rejected:** using a passing ADC conversion or old pin-map result as proof of
the new wiper wiring; claiming that the diagnostic changes normal camera
exposure; treating an unqualified constant-LOW JS input as a measured HOLD
release; or promoting retained Standby history into direct release/entry-time
proof. Normal exposure integration, ADC electrical calibration and a dedicated
cold-start ADC qualification remain separate work.

**Evidence:** [November9 live archive](evidence/2026-11-09-a3-live/README.md),
root-owned campaign `tmp/bringup/a3-smoke-20261109/`. Diagnostic SHA256
`bd8ab98dad9f457f9a631e1840be099a83839d3e4b4a9b6a1a3f24987ee18b8a`
launched through package prefix
`852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084`.
The full 1,463-sample run recorded A1 extrema 0–3840, A0 extrema 0–6, A2=3840,
no HAL/CPU faults and HOLD IDR1; subsequent direct pin reads confirmed A2 LOW
and A3 HIGH after clean STATE8 stop. Exact UART recovery passed after the
diagnostic and after the separate no-sensor error/shutdown cycle. The root's
final checkpoint leaves JS output OFF; no live ownership is retained here.

## 2026-11-13  Isolate header faults with a standalone all-output blinker

**Why:** the user explicitly removed external header wiring and requested
A0–A5 at2Hz to resolve conflicting external A3 voltage and internal PA2
readings. The temporary FLASH test bypasses camera, USB, storage and shutdown,
while preserving exact UART recovery and a backed-up restoration image.
It deliberately toggles A3; the normal diagnostic's HOLD-preservation rule
still applies whenever the latch is attached. A1/PC10, as well as A4/PC12 and
A5/PH2, requires VDDIO4 supply-valid with stock3.3V voltage selection.

**Rejected:** reusing the exposure diagnostic while treating all contacts as
unloaded, interpreting MCU IDR as an independently measured external voltage,
or leaving a modified image without a verified recovery route. The earlier
ADC13 cross-check is deferred in favor of the user's simpler physical test.

**Evidence:** [test behavior and mapping](gpio-blink.md),
[programming, live reads and recovery](evidence/2026-11-13-a0-a5-blink/README.md).
The user confirmed all header wiring removed and direct5V/ST-LINK ready.
All six input/output bits alternated, and exact UART recovery passed9valid/
0bad pulses. External waveform verification remains with the user.

## 2026-11-13  Move the control helper to D3 and bind host checks to the exact HOLD hook

**Why:** after A3 and its direct PA2 tap failed the user's physical blinker
check, the user moved the latch to Arduino D3/CN13.4/PE9. Schema4 retains
A0 LOW/A1 wiper/A2 excitation and the mandatory ADC12 security fix while
asserting only PE9 as HOLD. PA2 and PA12 are untouched. Stop/error paths
remove A2 excitation and retain D3 HIGH for debugger access. Both the old
PA2 hook and new PE9 hook enter at0x34181DF1, so a reset-vector check cannot
identify which GPIO to verify before replacing firmware in SRAM.

**Rejected:** driving the suspect PA2 pad, changing exposure/ASA integration,
using a common hook address as a pin identity, silently relabelling historical
schema3 telemetry, or admitting new hardware recovery identities from this
diagnostic. New launches/replacements require schema4 and an installed D3
package; schema1–3 remain monitorable. Package inspection recognizes schema3
PA2 and schema4 PE9 only when their explicit metadata and exact76-byte hook
hash agree. GPIO clocks are checked before the before/after-bridge reads.

**Evidence:** `control.c`, `build.py`, `console.py`, `test_control_pins.py`
and `test_package_launch.py`; ten offline tests pass, including4096 GPIO
preservation cases,4096 ADC security cases and five security refusals.
Offline build `tmp/bringup/d3-hold-20261113/control-pe9` is5808bytes with
SHA256`263bba342c602d5e17d99c1d66f8a5f809be5b804f2276220a975ad3d8d8f875`.
Official MB1940C02 sheet10 and manufacturing ODB identify D3 as PE9 with
alternate tap CN15.31; DS14791Rev10 Table18 pp100/112 places it on mainVDD.
This diagnostic migration performed no instrument operation or NOR/SD write;
live installation and qualification remain the root bench campaign's record.

## 2026-11-13  Follow the user's D8 HOLD substitution without repeating tests

**Why:** the user subsequently selected D8/CN14.1/PD12 instead of D3 and
requested a simple substitution/reload without further testing. Schema5
changes only the diagnostic HOLD pin and its host identity/telemetry while
retaining A0–A2, ADC security and terminal HOLD-HIGH behavior. Historical
PA2/schema3 and PE9/schema4 packages remain inspectable; new launches require
the exact PD12/schema5 package. PA2 and PA12 remain untouched.

**Rejected:** retaining D3 as current, silently relabelling old diagnostics,
or sharing PD12 with the former phase-marker output. The capture build owns
that marker's removal; this helper never emits it. Further diagnostic builds,
regression execution and live ADC testing are deferred as the user requested.

**Evidence:** current `control.c`, `build.py`, `console.py` and README;
existing test expectations are remapped but not executed. Official MB1940C02
sheet10/ODB identify D8=PD12 with alternate tap CN15.21; DS14791Rev10
Table18 identifies mainVDD through footnote1. No diagnostic hardware operation
or new ADC qualification is implied by this source update.
