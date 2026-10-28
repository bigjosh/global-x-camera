# Direct 5 V baseline and CN15 Joulescope marker test

Measured October 28, 2026. Both signal connections are confirmed: JS110 IN0
records the normal firmware's ten PD12 phase markers, and IN1 follows a
controlled PD0 low/high test. Three cold capture cycles were recorded without
changing the installed firmware. These are timing/power and wiring results;
the saved images were not independently read back in this campaign.

## Configuration and scope

| Connection | Endpoint |
|---|---|
| JS110 rear IN0 | CN15 pin 21 / PD12 |
| JS110 rear IN1 | CN15 pin 33 / PD0 |
| JS110 rear GPIO GND | CN15 pin 20 / GND |
| Regulated bench supply | JS110 IN+; rated 5 V / 2 A |
| JS110 OUT+ | CN5 pin 5 / target 5 V |
| Common power return | CN5 pin 6 / GND |

The user confirmed the proposed hookup, with CN8 and LTC output disconnected,
CN9 shunts absent and CN10 independently powering ST-LINK. Individual contacts
were not physically inspected. D2/R23 are removed; U24 Ethernet PHY remains.
The selected SD connection is the twisted CLK/GND pair, without resistor or
SD signal probes; SD VCC comes from CN3.5/main VDDIO at 3.3 V.

The installed normal four-bit 25 MHz firmware remained
`tmp/bringup/error-relocate-20261026/flash-normal-v2`. Four fresh recovery checks
matched its exact prefix and early park at `0x3418078C`, with nine good UART
pulses and zero bad each. Prefix SHA256:
`99dbb0f9ecdd56a9313e4e62bbbfec22ec8e5e5901c852d956315844cd066eba`.
No full physical NOR readback, reflash, firmware RAM load or explicit SD erase
was performed. Normal boots may save a new photo each time.

## Cold-cycle observations

Each run followed a fresh recovery-park check, about 15 seconds of JS output
off with near-zero measured current, and one power-on. No debugger or UART
stimulus occurred during the measured cycle.

| Run | Current onset to pre-WFI marker | Current onset to low plateau | Energy from onset + 5 ms to plateau | Plateau current |
|---|---:|---:|---:|---:|
| cold01 | 613.7795 ms | 634.4515 ms | 381.5747 mJ | 8.70576 mA |
| cold02 | 566.1675 ms | 587.3715 ms | 351.2577 mJ | 8.69334 mA |
| cold03 | 550.1685 ms | 570.9840 ms | 340.1795 mJ | 8.69263 mA |

These energy figures deliberately exclude the first 5 ms. The native startup
samples contain very brief extrema near 7.9 A, negative current and roughly
1.7–5.75 V. Actual inrush, instrument range switching and clipping have not
been separated, so those extrema are not qualified as real DUT current or
rail droop. Whole-cycle energy remains unqualified. Raw numerical whole-window
integrals are 385.364, 355.051 and 343.974 mJ; they are retained for comparison,
not promoted as qualified whole-cycle measurements.

After the first 5 ms, the analyzed active intervals are finite and contiguous:
JS input voltage spans approximately 4.934–5.022 V, average current is
120.9–121.95 mA, and the largest nonoverlapping 1 ms current means are
205.6–206.3 mA. JS input voltage does not independently measure downstream
target-rail droop or quantify the instrument's insertion drop.

Definitions used in [the analysis](baseline-analysis.json): current onset is
the first sample at or above 20 mA in the 500 ms before phase 1, with preceding
1 ms mean absolute current below 100 microamps. Plateau begins at the first
whole 1 ms bin after pre-WFI with ten consecutive means between 6 and 12 mA.
The low plateau and final phase markers are firmware/current observations,
not a fresh SBF register check or independent image-content verification.

## Digital qualification

All three cold runs contain one unique, complete PD12 event train in the
semantic order **1, 2, 4, 3, 5, 6, 7, 8, 9, 10**. Per-run event timestamps
are in `cold01/phase-events.csv`, `cold02/phase-events.csv` and
`cold03/phase-events.csv`. The repeated SD transfer loop is not separately
encoded by every pulse in this protocol.

Protocol-v2 pulse widths are nominally 2 microseconds per event ID. The
decoder accounts for approximately 0.24 microseconds hook overhead and the
JS110's 0.5 microsecond sampling grid, accepting absolute width error at most
0.75 microseconds around `2 * ID + 0.24`. Event order and uniqueness are
checked; unmatched transitions remain in the evidence.

Extra startup/off transitions were observed: GPI0 counts 100 / 0 / 28 and
GPI1 counts 326 / 368 / 420. GPIOs can be undriven during startup or early
recovery park. Do not assign these transitions to firmware execution or use
PD0's first threshold crossing as a qualified instruction-entry/reset-release
timestamp. CN15 does not expose target NRST.

To establish IN1 wire identity directly, the fourth recovery park was checked
and only PD0's output bit was commanded LOW/HIGH three times, preserving all
other output bits. Each readable ODR write was checked. IN1 recorded exactly
those six transitions, starting and ending HIGH; original ODR/configuration
were restored. See [wire observations](pd0-identity02/wire-observations.json).
IN0 recorded 134 chatter edges during this parked test, where PD12 is
unconfigured/high impedance. The strict IN0-silence assertion failed and is
retained in [wire-proof.json](pd0-identity02/wire-proof.json); this is not a
claim of no crosstalk. Actively driven PD12 was independently confirmed by
the ten phase markers in all three normal cycles.

The first PD0 attempt used a write-only BSRR destination and CubeProgrammer
reported download/verification failures. Its records remain in
`pd0-identity/`. The explicit restoration in `pd0-restore/` preceded the
corrected readable-ODR test. Failed commands are not relabeled successful.

## Capture integrity and reproducibility

JS110 device 000163 was accessed through its API at 2 MHz, using the internal
3.3 V digital reference and i/v LSB routing for GPI0/GPI1. Analog i/v/p and
packed digital streams were recorded together. Native sample IDs, continuity
and file hashes were checked offline. Analog channels do not begin at the
same sample ID: current begins at 0, voltage/power at 16128. Align channels
by sample ID, not raw-file index or host callback timestamps.

Each full cold recording retains 71 initial NaN current samples before the
actual cold boot. Whole-session finite validity is therefore false; scoped
post-launch windows are checked separately. The final packed digital chunk
is excluded because this Python binding does not expose its valid element
count, so padding must not be interpreted as signal transitions.

[manifest.json](manifest.json) binds the compact archived records. Full raw
`.f32`, `.u1` and chunk logs remain locally under
`D:/Github/global-x-camera/tmp/bringup/js-gpi-smoke-20261028/`; their hashes are
recorded in each run's result. [analyze_baseline.py](analyze_baseline.py) is
the offline analysis. [gpi_capture.py](gpi_capture.py) is the final helper
version, including the later PD0 test; it is not a contemporaneous source
snapshot for every earlier recording. Raw recordings remain needed to replay
the analysis and are not included in this compact archive.

## Final bench checkpoint

After restoring PD0, one normal warm reset without UART recovery bytes
returned the board to the low-current signature. At **17:01:54.672 UTC**,
JS measured **4.99337 V / 8.56799 mA**. This final boot was not separately
read back for a saved photo or SBF flag. Firmware remains unchanged.

JS closed cleanly, restored range 128, EXTIO 0, original LSB routing and
stream settings, and left power enabled. COM8 is closed, BREAK released and
all instrument helpers exited. Recheck ownership and live execution state
before further hardware operations. No additional hardware operation is
required to reproduce the documentation or inspect the saved evidence.
