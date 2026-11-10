# A3 HOLD and A0–A2 knob: installed and smoke-tested

November 9, 2026, America/New_York. Final checkpoint 23:01:21 EST
(2026-11-10 04:01:21 UTC).

The prepared PA2/A3 capture-plus-USB firmware is **installed**. Both 64 KiB
NOR regions were independently read back and matched exactly; the following
4 KiB was preserved. The sensor and MCU USB/CN8 were **disconnected** throughout.
ST-LINK/CN10 was connected; the user confirmed direct external power through
the Joulescope into the target's 5 V input. This tests firmware/GPIO behavior,
not the LiPo/SPDT power latch or image capture.

| Check | Result |
|---|---|
| A3 / CN4.4 / PA2 | Push-pull HIGH, no pull; ODR and pad IDR HIGH in early UART recovery, before/after the SRAM bridge, during ADC sampling, after ADC stop and during camera-error handling |
| A0 / CN4.1 / PF5 | LOW; conditioned endpoint ADC near zero |
| A1 / CN4.2 / buffered PA9 | User swept full travel: **0–3840** raw counts; approximately **1999–2004** at the reported middle |
| A2 / CN4.3 / PF6 | HIGH during sampling; endpoint ADC **3840**; independently read LOW after cooperative stop |
| ADC diagnostic | Schema 3, no HAL or diagnostic errors; clean STATE 8 stop, HOLD retained |
| UART after installation | First attempt passed: **9 valid / 0 bad pulses** |
| UART after diagnostic | First attempt passed: **9 / 0** |
| UART after power cycle/error shutdown | First attempt passed: **10 / 0** |
| Missing-camera boot | S1ER result **17**, sensor phase **2**, sensor result **−3**; A3 remained HIGH during the error display |
| Low-power result | **3.2055 mA** at **4.9952 V** source; retained CPUCR **0x10201**, SBF=1, PDDS=1, STOPF=0 after UART recovery |

The sensor failure occurs before the receiver/SD code loads. No SD read/write,
erase, deletion, capture or host PTP transaction was performed. Existing photos
were not used for this test. Normal capture exposure remains fixed; the knob
is still a RAM diagnostic, per the user's explicit deferral.

## Firmware identities and evidence

Installed package:
[`usb-ptp/evidence/2026-11-09-a3-hold/package-pa2`](../../../usb-ptp/evidence/2026-11-09-a3-hold/package-pa2).

| Artifact | SHA256 |
|---|---|
| Combined prefix | `852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084` |
| NOR sector 0 | `c822d2333ce265ded2ea420fd4c78e2a20e01c4b392b1decb99b80d9a040516d` |
| NOR sector 1 | `347aa3c1db62cb95bd6b66d421c0d9c3db5a706e493baf2f515ac13cb9f4670f` |
| Temporary ADC diagnostic | `bd8ab98dad9f457f9a631e1840be099a83839d3e4b4a9b6a1a3f24987ee18b8a` |

The diagnostic runs from RAM only and is no longer executing. The combined
normal firmware remains in NOR. The old package08 was independently backed
up and matched before programming sector 1, then sector 0. The new exact
prefix was explicitly admitted to the existing recovery checker after its
offline review; all subsequent live checks compared the complete prefix.

[results.json](results.json) consolidates outcomes. `hardware/` contains
programmer calls, backups/readbacks, exact UART proofs, pre/post-bridge HOLD
checks, ADC samples/stop proof, error snapshot, power statistics and final
state. `diagnostic/` freezes the tested RAM build. `support/` preserves the
package-aware launcher and maintenance/recovery helpers. `archive-index.json`
maps campaign files; `SHA256SUMS` binds this archive. The full local campaign
is `tmp/bringup/a3-smoke-20261109/`.

The new launcher requires an independently admitted exact current package,
fresh early UART park, idle peripheral clocks, and PA2 HIGH before and after
the unchanged SRAM bridge. Eight offline launcher/control tests passed. It
does not weaken old-package rejection or automatically admit new firmware.

## Power-cycle boundary and limits

One API-controlled JS OFF interval lasted **15.063 s**, with zero measured
input current at its end, followed by 15 seconds ON. The missing-camera
record and A3 state were read without halting during error handling. The
reviewed code maps this failure to two red flashes repeated five times,
followed by HOLD release and Standby. No separate LED probe counted the flashes.

The external HOLD probe was optional and was not confirmed connected. The
recorded IN0 stream was LOW and is **not a HOLD measurement**. A3's physical
fall/Hi-Z transition, latch takeover/hold-up, actual battery cutoff and AUX/main
rail sequence remain unmeasured. Retained SBF and low current support the
Standby result; the flag reader retains `trial_entry_proven:false`, rather
than claiming a separately instrumented exact entry time. The ADC trial was
a warm SRAM launch; a cold knob launch and voltage accuracy remain unqualified.
No image or USB-mode behavior was requalified with the missing sensor/CN8.

## Final bench state

**JS output intentionally OFF (range 0); measured current 0 A.** Other JS
settings were restored and its API closed. COM8 is closed with BREAK released;
no monitoring/diagnostic helper remains active. The final pre-off code/prefix
and UART park were checked again. Zero input current is not proof every target
rail is zero through debug paths. The ST-LINK cable remains connected, while
the camera and target USB are absent. On the next normal boot without a
camera, the expected camera-init error remains normal behavior.
