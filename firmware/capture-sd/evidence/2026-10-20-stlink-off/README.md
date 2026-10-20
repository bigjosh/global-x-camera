# Two power cycles with ST-LINK USB disconnected

On October 20, 2026, the user unplugged CN10/ST-LINK USB and requested two
power cycles with power logging, followed by their own SD-card inspection.
Both cycles showed the usual active waveform followed by a stable low-current
plateau. Firmware, jumpers and storage configuration were unchanged.

| Run | Current onset to plateau | Energy to plateau | Plateau current | Plateau power |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.97694 s | 1.42206 J | 8.22712 mA | 40.2503 mW |
| 2 | 3.10364 s | 1.49753 J | 8.22746 mA | 40.2508 mW |

These energies include startup/inrush and end at the measured low-current
plateau. A separate one-second plateau confirmation consumed approximately
40.262 mJ per run and is excluded from the table. The time origin is measured
current onset, not reset release or a measured target-power-good edge.

The [preceding three v59 trials](../2026-10-20-low-power/README.md) with CN10
connected measured 1.410–1.424 J over 2.963–2.983 s, with 8.103–8.212 mA idle
current. The first new trial is within that energy/time range. The second took
about 127 ms longer than the first. Scene/compression workload and card behavior
were not controlled or inspected here, so the difference cannot be attributed
to unplugging the debugger. Idle current remained similar.

## What was and was not verified

- JS110 current/voltage/power were recorded at 2 MHz using the API. Full-rate
  samples have contiguous native sample IDs, no dropped chunks, and finite data
  throughout both analysis windows. The initial 71 nonfinite current samples
  occur before either window and were not interpolated into the calculation.
- The two output-off intervals were approximately 15.1 s, with zero measured
  branch current. Target-rail discharge was not independently measured.
- Each run returned to the characteristic approximately 8.23 mA plateau. The
  prior v59 shutdown guard and qualified waveforms supported ending the bench
  run there; these new traces alone do not prove capture, file commit or MCU
  Standby. No firmware status, SBF, filename, file contents or image size was
  read this session. SD inspection remains pending with the user.
- The installed image remains the previously verified v59 sector,
  SHA-256 `7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
  No programming, UART, SWD or formatting commands were issued. Only normal
  firmware execution could write the two new photos.
- Saleae CH0/CH6 traces remained near zero. They are retained as an unsuccessful
  observation, not accepted as NRST, PE6 or power-good evidence. Their present
  connection/reference is unverified; the last historical pin map must not be
  assumed valid for these captures.

The expected new names are **IMG00044.PNG and IMG00045.PNG**, conditional on the
preceding final boot having saved IMG00043.PNG and no intervening captures.
These names were not enumerated from the card.

## Measurement boundary

The JS110 measured the target supply branch with CN10 unplugged, using its
existing auto-range and suppression settings. Reported input-voltage minima
were 1.987/1.989 V and current peaks 7.727/7.752 A during startup. These short
transients are included in the integration; the retained suppression settings
do not establish unsuppressed transient accuracy.

The last confirmed source path was CN8 → CN9.3 → JS110 IN+ → OUT+ → CN9.2,
with D2 and R23 removed. CN8 sense/USB paths remain outside the JS branch.
Unplugging CN10 removes its external USB supply but does not measure current
through every unpowered debugger signal/sense connection. Consequently these
are board-branch measurements, not isolated MCU or production battery energy.

## Evidence and final state

- `analysis/`: exact windows, criteria, context, results, comparison summary,
  compact sample-bin exports and PNG/SVG plot. Every new cycle is explicitly
  marked unqualified for firmware completion; the analyzer required its
  `--allow-unqualified-plateau` option. Strict default behavior is unchanged.
- `raw-metadata/`: original manifest and compressed chunk index, binding the
  local raw files by SHA-256 and per-chunk CRC. Compact exports retain the
  plotted count/sum/min/max bins and checked energy sums. They do not retain
  within-bin order and cannot replace raw onset/plateau replay.
- `bench/`: JS session log, exact cycle controller, command responses and
  Saleae summaries. The controller was called without its optional UART
  argument. Its final repeated `auto` command retained power and did not add
  another off/on cycle.
- `final-state.json`: clean shutdown of the JS API session at
  **19:28:28 UTC**, restored auto range 128 and stream settings, target left
  powered at **4.89285 V / 8.22613 mA**. No bench helper remains active.

Exact local recording and Saleae captures remain under
`tmp/bringup/capture-sleep-20261020/stlink-off/`; the three raw sample files total
about 1.97 GB and are intentionally outside Git. No private images or card
sectors are included in this archive. The preceding firmware/evidence archive
was not modified.

The user was told both cycles had ended and they could power off to inspect the
SD card. Recheck ownership, wiring and card presence before any subsequent
bench action; reconnect CN10 before attempting UART/ST-LINK recovery.
