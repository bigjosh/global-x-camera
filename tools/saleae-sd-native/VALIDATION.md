# Validation — 2026-10-25

Windows x64 Release build: MSVC 19.44.35228, Windows SDK 10.0.26100,
official Saleae AnalyzerSDK `e3c4b4ffda1c162c024a5913520aed17c6edb238`.
The DLL exports `GetAnalyzerName`, `CreateAnalyzer` and `DestroyAnalyzer`.

Prepared local DLL: `dist/windows-x64/GlobalXNativeSD.dll`, 130,048 bytes,
SHA-256 `bf2fe4cbd7935d2a3767fab470bd836b8ab1ac1ca1dea0cc26fadc45dc10e292`.
This identifies the prepared binary, not a promise of byte-identical rebuilds
with another toolchain or build path. The SDK runtime is not redistributed.

## Completed offline checks

CTest Release: **3/3 suites passed**:

1. **native_sd_decoder** — ten grouped protocol scenarios, including width
   negotiation, rejected commands, all four data CRC lanes, missing/reserved
   write status, R2/R3 distinctions, stopped-clock busy, interrupted/truncated
   traffic, small register data, CMD23 versus ACMD23, and explicit data-only
   inference. Checks execute in Release and do not depend on `assert`.
2. **recorded_sd_waveforms** — seven Python regression tests against the two
   compressed, hash-verified raw transition clips in `tests/fixtures`.
3. **native_sd_adapter** — the actual `SdNativeAnalyzer::WorkerThread` against
   the official SDK's test library plus test-only modern API shims. Both
   recorded clips pass both waveform views; V1/V2 frames agree and do not
   overlap within a view. A positive sample offset leaves raw busy timing
   unchanged. A clearly synthetic continuation releases DAT0 after all CLK
   edges have stopped and is still decoded correctly. Complete mode returns
   normally, with bounded availability-query counts.

The recorded tests verify:

| Observation | Expected and decoded |
|---|---:|
| ACMD23 pre-erase hint | 3,730 sectors |
| CMD25 raw argument | 14,920 (`0x00003A48`) |
| First complete packet | 512 bytes; all four CRC16s valid |
| First payload prefix | `47 58 52 32 00 00 00 00 00 00 00 00 00 00 00 00` |
| First card write-status | Accepted (`010`) |
| Per-block DAT0 busy | samples 105704624–105765650; **244.104 µs** |
| Final CMD12 DAT0 busy | samples 159918394–160132045; **854.604 µs** |
| CMD12 response starts | sample 159918457, after busy has already begun |
| Subsequent card status | PRG/not-ready, then TRAN/ready |

All times use the recorded acquisition rate of 250 MS/s. No transitions were
filtered. The first clip ends during CMD25, so its transfer summary must be
incomplete even though its first packet is valid. The final clip starts after
the payload and cannot establish the full image's validity.

The replay Python scripts also pass bytecode compilation. Build instructions
and the CTest targets reproduce these checks without instrument access.

## Logic 2 integration completed

The same DLL was copied and hash-verified in the user's configured folder,
`C:\Users\joshd\OneDrive\Documents\Logic Pro Analyzers`. Logic 2 2.4.48
successfully loaded it in a fresh visible instance on API port **10431**.
The older background instance on 10430 predates the configuration change and
was left intact; restarting a separate visible window had not updated it.

The full `phase01/signals/signals.sal` recording is open with **SD Commands**
and **SD Data and busy** views, automatic width, rising edge and offset zero.
The annotated capture and two CSV exports are saved locally under
`tmp/sd-analyzer-replay-20261025/`. Both the all-events CSV and Logic's data
table reproduce the two exact busy intervals above, including the final busy
starting 252 ns before the CMD12 response. The subsequent CMD13 responses
show PRG/not-ready while busy and TRAN/ready after release.

The pre-resistor recording is noisy. Data decoding suspends at block 11's
malformed write-status token; the transfer is flagged erroneous. **This is
not a successful decode of all 3,730 blocks.** Command decoding continues and
the final CMD12 busy still matches the raw-edge reference. The exports contain
150 events (18 error-flagged) and 141 table rows; eight transfer summaries and
one width-change event are intentionally omitted from the sequential table.

The [integration record](tests/fixtures/logic2-integration.json) preserves
settings, export hashes and reference events. No new hardware capture,
firmware change, reset, SD write or power operation was performed. Saved-trace
decoding does not qualify analog signal integrity or current board wiring.

## October 26 user recording: command sampling and write abort

Read-only replay of `Global X SD card with 27ohm on clkSession 2.sal` used
250 MS/s, rising CLK, CLK=1/CMD=0/DAT0..3=2..5. Offset 0 produced misleading
startup command labels. Offset 3 (+12 ns) decoded 193 genuine commands with
valid CRC7; one preceding CRC-bad CMD63 is a startup-framing artifact.
An independent raw-transition decoder confirmed the command sequence and
the card's rejection below. The installed DLL and firmware were unchanged.

The startup sequence contains 61 CMD55/ACMD41 readiness polls, followed by
CMD2/CMD3/CMD9/CMD7, status checks, SCR read, ACMD6(2), a second SCR read,
and 15 CMD17 slot-header reads. Slot 14 at LBA 52,220 was blank. ACMD23
announced 3,730 sectors, then CMD25 started there.

| Raw event | Time relative to capture trigger |
|---|---:|
| CMD25 start | 266.341940 ms |
| Block 1 start; accepted | 266.347016 ms |
| Block 2 start; accepted | 266.595424 ms |
| Block 3 start; CRC-rejected | 266.638284 ms |
| CMD12 start | 266.697384 ms |
| Final DAT0 busy | 266.699460–267.690712 ms (991.252 us) |

The third DAT0 status token is `0 101 1` (start, CRC-error status, end),
unchanged at sampling offsets -4 through +16 ns. All four outgoing CRC16s
pass on all three blocks in the analyzer's sampled signal. That does not
prove what the card saw at its pins. CMD12 starts only 355.444 us after
CMD25; its busy begins before its R1b response. Two subsequent CMD13 replies
are TRAN/ready (`0x900`). **This is an aborted three-block save, not a complete
image or evidence of 25 MHz reliability with these probes attached.** The
capture alone does not establish the electrical cause of the CRC rejection.

Reproducibility metadata and export hashes are in
[the evidence record](evidence/2026-10-26-session2.json). Original waveform,
raw exports and an annotated copy with `SD Commands` and `SD Data and busy`
views remain locally under `tmp/sd-analyzer-fresh-20261026/`. The original
user recording was not modified. No capture, reset, power operation or
debugger access was performed in this analysis.
