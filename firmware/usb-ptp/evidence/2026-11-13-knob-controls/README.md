# Exposure and ASA control integration — November 13

The user requested loading the firmware and explicitly delegated functional
testing to themselves. Offline build and required programming checks are
distinct from live capture, image, USB or recovery qualification. Consult
`hardware/final-state.json` for whether installation has completed.

Each battery capture reads the two installed knobs after confirming USB VBUS
absent and before sensor START. Exposure is continuous logarithmic1/1000–1/2s;
ASA100/200/400/800 selects1×/2×/4×/8× analog gain, with digital gain1×.
Both increase counterclockwise, using the measured opposite ADC polarities.
ASA numbers are provisional rather than calibrated sensitivity.

Exposure wiring remains A0 LOW/A1 wiper/A2 HIGH; ASA A4 HIGH/A5 wiper/GND.
Both excitation supplies return LOW immediately after sampling. D8/PD12 HOLD
and the exact original UART recovery guard are retained. USB-selected mode
keeps HOLD LOW and bypasses knob sampling. Early HOLD before mode selection
and early UART-recovery HIGH remain as in the previous D8 build.

The sensor uses constant line length1280 and a 2000-line exposure reserve;
500000us requests round to62813 coarse lines, nominal500003.98us, frame64813.
The default READ_OFFSET18 remains valid. Maximum analog-gain code is explicitly
set/read back as28 to permit8×; the documented default24 would limit4×.
The helper reads the actual sensor exposure margin instead of assuming either
of the conflicting published34/68 values. Post-frame logic checks applied
exposure, frame/margin and analog/digital gain before declaring success.

A128-byte CKN1/schema1 record fits the existing152-byte front metadata area;
slot layout/stride stay unchanged. The first-sector snapshot records whether
settings are configured or already applied-verified and is never rewritten.
USB PNG comments report valid settings and label ASA as provisional; older
photos remain readable without fabricated settings. Metadata has a CRC.

The CRC-loaded selector is7716bytes in its8192-byte allocation. Two exact
sensor prefix relocations call its fixed helper before sensor START. The
selector at0x34200000 lies beyond image DMA (ending0x341D2400); a later host
RAW-read helper uses that region. The controls record at0x343F9400 also lies
outside image DMA. This corrects the original frame-overwrite explanation.
No runtime instruction patching or fixed UART/error-layout movement occurs.

| Artifact | SHA256 |
|---|---|
| Combined prefix7160B | b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242 |
| NOR sector0 | 6ddf4499865264aec845150597aa6b8d44cb89e7d5e621dd324a0e1a9170b499 |
| NOR sector1 | 206da4c0a8bdcda6205d7ccdb3d9ac02548e9db6852b1fa47afa6327b76473d8 |
| USB payload | 06dca8da9d220833935f79c23f041b7c4df84e9283a0cfe9044d713229e1d6bf |
| Capture receiver | 8cd86fa71e1cd2422897558567b9c66035c66ca103cea537e50ad3ebd4d5caaa |

The earlier live [dual-knob diagnostic](../../../control-smoke/evidence/2026-11-13-dual-knobs/README.md)
established polarity and approximate taper; it did not test this integration.
Offline capture regression ran327 tests (four optional linked checks initially
skipped), then25 final linked HOLD tests passed with no skips. The old D8
default receiver/prefix/sector reproduce byte-for-byte. Mapping/ADC/helper
tests and19 USB storage/EXIF tests passed before the user's load-only request.
No further functional test campaign is claimed.

Build commands, from repository root:

```powershell
python firmware/capture-raw/build.py --out tmp/controls-capture --flash --standby --sensor-single-frame --error-blinks --ethernet-powerdown --magic-format --line-stream --async-stop --transport idma --sd-bus-width 4 --sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt --gpio-hold --knob-controls
python firmware/usb-ptp/build.py --out tmp/controls-usb
python firmware/usb-ptp/package.py --usb tmp/controls-usb --capture tmp/controls-capture/staged --capture-controls --out tmp/controls-package
```

The exact package is frozen here; compiler object intermediates are omitted.
SHA256SUMS covers build evidence, excluding this README and later hardware
records. Installation records maintain a separate hash list.
