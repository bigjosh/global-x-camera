# ST-LINK VCP recovery-signal experiment — October 19, 2026

**UART bytes reach PE6 without disturbing NRST. UART BREAK instead asserts
NRST and leaves PE6 high on this ST-LINK firmware.** This qualifies the observed
control signals, not a working bootloader recovery implementation. No firmware
or storage contents were changed. Installed v44 still checks PE1.

The user confirmed SD wiring, ST-LINK USB and target power through JS110, and
reported the OUT0 recovery wire no longer reaches. They then connected Saleae
ground to CN5.6, CH6 to CN15.2/PE6 and CH0 to CN3.14/NRST for this test.
CH0 preserves the historical reset assignment; CH6 was unused. Channel numbers
provide no electrical advantage.

## Observations

| Test | Measured result |
|---|---|
| Power preflight | JS110 IN+ averaged 4.882 V, current 74.38 mA; ST-LINK reported 3.28 V target supply. JS opened in restore mode and restored automatic range 128 on clean close. No current-range/power-switch command was issued. |
| Debug access | Bounded HOTPLUG AP1/AP0 reads could not identify the core. A documented HWRSTPULSE connection attempt also failed to identify it. No claim that the failed command physically pulsed NRST. No `DEV_USB_COMM_ERR`, no USB pipe reset. |
| Original probes | Old channels 0–5 read approximately zero despite powered target evidence; those readings did not establish power loss. |
| Reconnected passive probes | NRST averaged 3.187 V. PE6 initially averaged 0.049 V with VCP unopened. Do not assume idle HIGH immediately after debugger enumeration. |
| Open COM8, no data | PE6 rose to about 3.27 V after port configuration; NRST stayed HIGH. PE6 stayed HIGH through the observed port-close tail. |
| Assert UART BREAK for nominal 750 ms | PE6 remained HIGH. NRST went LOW for **752.46128 ms**, then returned HIGH. A single 0.16 µs digital low sample at release is retained in the raw trace, not interpreted as a distinct firmware reset. |
| 4,096 zero bytes at 115,200 baud | 4,096 LOW runs and 4,095 interior HIGH gaps. LOW widths 78.08–78.24 µs; interior HIGH gaps 8.64–85.76 µs. Burst duration 355.96944 ms. NRST stayed HIGH. |
| 4,096 zero bytes at 1 Mbaud | 4,096 LOW runs and 4,095 interior HIGH gaps. LOW widths 8.96–9.12 µs; interior HIGH gaps 0.96–104.64 µs. Burst duration 41.48912 ms. NRST stayed HIGH. |
| 115,200-baud stream plus BREAK-controlled reset | All 4,096 LOW pulses remained observable. Main NRST LOW interval was 101.11056 ms; 1,163 complete UART LOW pulses occurred during reset and 2,354 started after release, with about 204.63 ms of data remaining. Maximum interior HIGH gap was 70.72 µs. Two isolated 0.16 µs LOW samples at reset release are retained without interpreting them as separate resets. |
| Debug after BREAK | AP1 still could not identify the core. The cause remains unestablished. |

Digital capture used 6.25 MS/s (0.16 µs spacing); analog capture used
31.25 kS/s, with the 3.3 V logic-family threshold setting. The first and last
idle-HIGH intervals are excluded from the within-burst gap statistics.
Pulse counts/widths support transmission of the requested zero-byte pattern;
they do not establish reception by MCU firmware. Host event timestamps are
separate from the analyzer's hardware timestamps.

## Consequences for recovery

Use ordinary UART data as the candidate PE6 recovery stimulus; **do not use
BREAK as a way to pull PE6 low**. BREAK provides a measured reset-control path
on this specific V3J15M6 unit, but should not be issued casually during a write.
The final serial cleanup released BREAK and closed COM8; the final capture has
NRST HIGH and PE6 HIGH. The target remains powered, with v44 unchanged.

115,200 baud is the preferred starting point. The 1 Mbaud test demonstrates
that a fixed 100 µs observation interval can fit entirely inside a transmission
gap, so faster baud is not automatically more reliable. Even the 115,200 result
is an observed sample, not a worst-case USB/host latency bound.

**User decision after the signal tests:** missed requests can be retried by
resetting the MCU again. Keep the existing nominal 100 µs startup budget as
the implementation target, rather than requiring a guaranteed hit on every
attempt. Require a genuine transition/pulse pattern, not just a LOW sample:
PE6 was LOW with the port initially unopened. The exact pattern/baud remains
to choose when implementing it; a 1 Mbaud LOW pulse is easier to fit entirely
inside 100 µs, while its observed long gap can require a retry.

The combined test confirms the host can transmit through VCP while BREAK holds
reset, then continue transmitting after release. The future host controller
can use that combination, verify the exact recovery park and retry a bounded
number of times if necessary. It must not repeatedly reset a target during an
active or uncertain storage write. This is physical signal-path evidence,
not a successful firmware recovery attempt.

The next implementation must retain PE1 as an escape path, configure PE6 as
a digital input before observing it, ensure the host opens/configures the VCP
before boot, and qualify normal/requested boot selection over real resets and
cold cycles. Establish a measured detection window/retry policy and avoid
mistaking unrelated host serial traffic for a recovery request. No firmware
detector, cold-cycle test, NOR maintenance operation or power-off leakage
qualification was performed here. Installing that detector still requires
restoring usable debug access; the lost OUT0 wire remains unavailable.

## Reproduction and evidence

The API-only host tool is
[`test_vcp_signal.py`](../../../boot-timing/test_vcp_signal.py).
It does not alter target memory or switch power. Run passive mode first, then
an open-only capture if the unopened UART pin is low. Review actual NRST/TX
levels before transmitting or asserting BREAK. Its baseline gate is procedural,
not automatically enforced.

```powershell
python firmware/boot-timing/test_vcp_signal.py <new-output-directory> `
  --mode passive --probes-confirmed
# Other separately reviewed modes: open, break, bytes, reset-bytes.
# bytes supports --baud 115200 or --baud 1000000.
# reset-bytes is a 115200-baud stream with an overlapping reset pulse.
```

`source-index.json` records source paths, sizes and SHA-256 hashes. Compact
events, configuration, raw digital CSV, interval summaries and debugger logs
are committed. Full analog CSV and `.sal` files remain under
`tmp/bringup/vcp-recovery-20261019`. Recordings use UTC October 20; the local
America/New_York date was October 19.
