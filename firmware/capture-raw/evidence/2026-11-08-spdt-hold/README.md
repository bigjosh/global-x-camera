# SPDT trigger and PD7 HOLD preparation — November 8, 2026

**The estimate supports the selected 2.2 µF trigger.** Expect approximately
**25 ms** from the historical input-power reference to early PD7 assertion;
use **30 ms** for prototype planning. At an ideal constant 3.7 V, R1=100 kΩ
and C3=2.2 µF provide about **86 ms** before Q1 gate drive falls below 2.5 V.
That is approximately **56 ms of nominal margin** against the planning value.

The user confirms the SPDT latch is **not connected yet** and requests an
estimate from previous runs. This record contains no new power cycle, GPIO
measurement, target read/write, NOR programming or SD operation. The HOLD
implementation is built and checked offline; **normal FLASH is unchanged**.
Actual latch startup, battery headroom and rail sequencing are unqualified.

## Canonical circuit

Use the [power document and exact connection table](../../../../docs/power/2026-10-14-power-tree-review.md#november-7-lipo-button-and-pd7-hold-wiring).
The [PNG](../../../../docs/power/lipo-latch-wiring.png) and
[SVG](../../../../docs/power/lipo-latch-wiring.svg) show:

- SW1 momentary, break-before-make SPDT; common to C3 top, released/NC to
  R5=1 kΩ then ground, pressed/NO to Q1 gate/Q2 drain.
- C3=2.2 µF X7R, 10–16 V, bottom grounded; R1=100 kΩ Q1 source-to-gate.
- Q1 AO3401 and Q2 AO3400; PD7 through R4=1 kΩ to Q2 gate, R2=100 kΩ
  gate-to-ground. **C1, C2 and D1 omitted**, with R3 already omitted.
- Arduino D9/CN14.2 for HOLD, CN5.5 for target power through the retained
  2.2 Ω resistor, CN5.6 for ground. JS110 stays upstream of the entire latch.

Release before HOLD takeover disconnects C3 from Q1, so the trigger must
remain pressed through startup. Approximately 100 ms is a convenient first
manual test press, not a measured minimum or a guaranteed 100 ms pulse.
The released cap resets to within 1% of zero in about 11 ms nominal.
With the trigger held, Q2 keeps C3 discharged until firmware releases HOLD;
only then does the timeout begin. A firmware hang with HOLD HIGH can still
keep power on.

## Timing estimate from previous runs

The [October 17 boot-size experiment](../../../boot-timing/optimization-results-2026-10-17.md)
measured three 1,472-byte first-GPIO images at **22.563–23.228 ms** after
target input crossed 0.5 V, or **15.063–15.672 ms** after NRST rose.
The HOLD image is 7,840 packaged bytes: 6,368 bytes more. At the documented
32 Mbit/s ROM serial load, that adds approximately **1.592 ms**, producing
a first-order **24.155–24.820 ms** estimate. The empirical size slope was
0.262 ms/KiB, close to the theoretical 0.256 ms/KiB; applying that measured
slope instead gives 24.192–24.857 ms. Both estimates round to about 25 ms.
Neither models every ROM operation or establishes a timing guarantee.

The [November 6 runs with 2.2 Ω installed](../../../../docs/power/evidence/2026-11-06-series-resistor-tested/README.md)
provide a later-event cross-check: receiver markers occurred at
23.4700/24.0045/24.1480 ms and exposure started at
24.5840/25.1220/25.2675 ms after current onset. The prepared HOLD hook runs
before the original startup, UART guard and sensor-loader work. It adds
96 packaged bytes to that normal image, approximately **24 µs** of ROM load.
Thus **26 ms** is a rounded historical comparison allowance and **30 ms**
is the selected planning budget. Neither is a measured PD7 time for the new
latch. Current onset, input crossing 0.5 V and button closure are different
references; a slower LiPo/latch/regulator ramp can change the result.

[Calculation and source identities](historical-hold-window-estimate.json)
retain the individual observations, image sizes, hashes and ideal RC model.

## Trigger window and margin

Before Q2 takes over, with a fully discharged capacitor and constant VBAT:

`|VGS(t)| = VBAT × exp(-t / (R1 × C3))`

`t_strong = R1 × C3 × ln(VBAT / 2.5 V)`

The [AO3401 datasheet](https://www.aosmd.com/sites/default/files/res/datasheets/AO3401.pdf)
specifies on-resistance at VGS=-2.5 V. This is a useful strong-on comparison
point; its much lower gate-threshold voltage is measured at tiny current
and is unsuitable as a load-capable deadline. Falling below 2.5 V does not
mean the MOSFET suddenly turns off.

| Constant VBAT | Nominal 2.2 µF window | Margin after 30 ms | Window at 50% effective C |
|---|---:|---:|---:|
| 4.2 V | 114.1 ms | 84.1 ms | 57.1 ms |
| 3.7 V | 86.2 ms | 56.2 ms | 43.1 ms |
| 3.3 V | 61.1 ms | 31.1 ms | 30.5 ms |
| 3.0 V | 40.1 ms | 10.1 ms | 20.1 ms |

The 50% column is a sensitivity example, not an asserted property of the
unidentified capacitor. Effective capacitance, resistance tolerance, contact
bounce, remaining charge and source droop matter. At 3.0 V that example
loses the specified strong-on margin; it does not prove failure. These
voltages also do not establish that the Nucleo can operate from them.

## Firmware behavior and verification

The existing `--gpio-hold` implementation needs no executable change for
this SPDT circuit. A 76-byte stackless entry hook asserts PD7 before the
original reset handler: preload HIGH, configure push-pull/no-pull, then
continue the original startup. PD7 stays HIGH through capture/save, error
flashes and UART recovery. Success/error shutdown explicitly floats PD7
immediately before WFI. An unexpected WFI return reasserts it; awake and
refused-Standby paths retain HIGH.

Current manifest schema 2 records the accepted **no separate external
off-delay** prototype policy and explicitly leaves AUX rail ordering
unqualified. Exact schema-1 historical manifests remain recognized with
their original policy intact. The frozen November 7 archive is unchanged.
This metadata change does not relax machine-code checks or add hardware
recovery permissions. [Results and binary comparisons](results.json) retain
the current/historical audits and test logs: **320 tests passed, no skips**,
and all 173 frozen November 7 archive files remained unchanged. Both HOLD builds reproduce the
November 7 executable bytes; the disabled default reproduces October 28.

Original UART instructions and all twenty recovery literals remain unchanged;
the early receiver load is still 15,804 bytes. The linked success/error
release groups are checked as actual machine instructions. No ADC-control
integration or DMA-sleep change is bundled into the HOLD profile.

| Artifact | Standby HOLD candidate |
|---|---|
| Receiver SHA-256 | `d7a8202318d95183d7b09b97b728dd50d2e986e5a0ef668cc24f2e4dc320d3d1` |
| Prefix SHA-256 | `8614089a69fb0ca49d4a4d608159129079458a71b0be21f178574869377672f5` |
| 64 KiB sector SHA-256 | `909bc2f5e272a0216940e80f61dc8511c0ff4555df9e4e08c5b59af6b2c83f8c` |

Rebuild into a new output directory:

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/hold-new `
  --flash --standby --error-blinks --magic-format --line-stream --async-stop `
  --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge `
  --sd-clock-negedge-init --sd-review-profile --sd-startup-opt `
  --ethernet-powerdown --sensor-single-frame --gpio-hold
```

`hold-standby/` is the normal capture/save/Standby candidate; `hold-awake/`
omits `--standby` and retains HOLD after success for inspection. `support/`
and `SHA256SUMS` preserve the current builder/auditors and evidence bytes.
`verify_offline.py` is the frozen runner from the named local campaign; its
paths target that original layout, including the default control build.
Intermediate compiler object files are omitted; generated sources, linked
images and disassemblies are retained.

## Installation boundary

Normal FLASH still contains the October 28 profile without GPIO HOLD; no
new physical readback is claimed here. The earlier RAM ADC diagnostic's PD7
HIGH is not the normal cold-boot implementation. Install and verify the
prepared HOLD image on a stable supply before relying on the external latch.

Hardware reset also releases PD7 until ROM reaches the hook. UART code is
preserved, but autonomous reset recovery through the actual latch is not
established by an offline audit. A held SPDT is a finite pulse rather than
a permanent programming bypass. Actual pin timing, minimum press, held-button
cutoff and live recovery remain tests for the assembled circuit.
