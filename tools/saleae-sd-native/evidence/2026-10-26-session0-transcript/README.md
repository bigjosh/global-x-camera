# Session 0: measured SD-bus transcript

The supplied recording contains one complete native four-bit SD write:
**265 genuine commands, 264 responses and 3,730 accepted write blocks**.
All applicable command/response CRC7 checks and all data-lane CRC16 checks pass.
The final card status is TRANSFER / READY_FOR_DATA.

- [Complete command/response transcript — 529 rows](TRANSCRIPT.md)
- [Every write block, acceptance token and busy interval — 3,730 rows](BLOCK-WRITES.md)
- [Command/response and read-data records](commands.json)
- [Write-block timing records](block-writes.json)
- [Decode checks, clock transition and source hashes](decode-summary.json)
- [Source recording identity and replay provenance](source.json)

The transcript includes every initialization poll and slot-header command;
none are replaced by an ellipsis. Data-packet repetitions are separated into
their own appendix so the command sequence stays readable. Image payloads
are not copied into these reports.

## What this recording shows

| Logic time (s) | Observed step | Meaning |
|---:|---|---|
| 0.030360990 | CMD0 | Reset the card into native initialization; no response expected. |
| 0.030964314 | CMD8 `0x000001AA` | Check voltage compatibility and the `0xAA` echo pattern. |
| 0.033286768 | First CMD55 + ACMD41 loop reaches ACMD41 | Request operating conditions; 64 ACMD41 requests are observed. |
| 0.242843870 | Final ACMD41 R3 begins | Power-up-complete and high-capacity addressing are now reported. This response ends at 0.243315926 s. |
| 0.243446548 | CMD2, then CMD3/CMD9 | Read identity, obtain RCA `0xAAAA`, read capacity/capabilities. |
| 0.248744182 | CMD7 | Select the card. This command and the following first CMD13 readiness check still use the slow clock. |
| 0.251046218–0.251046300 | First short rising-CLK interval | Recorded clock transitions from about 100 kHz to the nominal 12.5 MHz profile, after selection/readiness. |
| 0.251215286 | ACMD51 | Request SCR; its eight-byte data reply arrives at 0.253146840 s. |
| 0.253247764 | ACMD6 `0x00000002` | Select four data lines; accepted by 0.253256042 s. |
| 0.253424322 | First CMD17 slot-header read | Read slot 0, then one first-sector read per slot through slot 37. There are 38 header reads. |
| 0.278729188 | Last header data begins | LBA 138,010, slot 37, has a zero-filled first sector and is selected for the new image. |
| 0.279154222 | ACMD23 `0x00000E92` | Give a 3,730-block pre-erase hint. This is not an explicit transfer-length command. |
| 0.279181646 | CMD25 `0x00021B1A` | Start one multiblock write at LBA 138,010, slot 37. |
| 0.279191050 | First image-slot data packet | Begin the 3,730 sequential 512-byte packets; each has four valid lane CRCs and an accepted status token. |
| 0.606964112 | CMD12 | Stop the multiblock transfer. Its response reports RECEIVING DATA / not ready. |
| 0.607017458 | CMD13 response | Card reports PROGRAMMING / not ready while the final DAT0 busy interval is active. |
| 0.607879554 | DAT0 rises | Final CMD12 busy ends after 911.464 µs. |
| 0.608082230 | CMD13 response | Card reports TRANSFER / ready. A final status check repeats this at 0.608181996 s. |

The first ACMD41 request through the end of the ready R3 spans
**210.029158 ms**. The command-and-poll exchange is included in that interval;
it is not a direct measurement of internal card initialization time.
The first CMD0 through the end of the final CMD13 response spans
**577.824782 ms**. Neither interval is the complete camera power-up cycle.

The clock ordering is the **later transition after CMD7**, not the experimental
transition before CMD7 discussed in the early-clock comparison. This is an
observation of the recorded sequence, not proof of a particular firmware hash.
Short recorded clock periods are approximately 80–82 ns; the transcript calls
this the nominal 12.5 MHz profile rather than claiming an exact measured 12.500 MHz.

Card registers identify `SE32G`, revision 8.0, manufacturer ID `0x03`,
OEM `SD`, and **62,333,952 × 512-byte sectors = 31,914,983,424 bytes**.
SCR advertises one- and four-bit support and erased byte `0x00`.
Slot numbering is a project-format interpretation using 3,730 sectors per slot,
not a concept carried by SD commands themselves.

## Write timing and overlap

The data-packet train spans **327.758434 ms**. Across it, the first-to-last-bit
data spans sum to **312.115436 ms**, acceptance-token spans to **1.200568 ms**,
and per-block DAT0 busy intervals to **10.847962 ms**. The remaining
**3.594468 ms** consists of gaps between these markers. Packet spans omit
the final sampled bit's remaining period, so that remainder is not all software
overhead. The final stop busy adds **0.911464 ms** separately.

Median per-block busy is **0.564 µs**, with one **7.459114 ms** outlier.
See the appendix for each individual measurement. These are observed pin-level
intervals; the card's internal buffering/programming schedule is not exposed.

CMD12's busy starts at **0.606968090 s**, before its R1b response begins,
and overlaps both that response and the following PROGRAMMING status exchange.
Those overlapping durations must not be summed as sequential work.
ACMD23 is a pre-erase hint; this capture has no explicit CMD23 block-count
command. CMD12 terminates the observed 3,730-block CMD25.

## Time definitions and validation

Source is the user's `Session 0.sal` under `Documents/Logic Pro/Captures`,
SHA-256 `2dfa9ccb1f2e0baea4d204c01366e1e75bf3d3a5d6aab9cf506d08f6fe73b057`.
The original file was preserved. Analysis used an owned copy and the Logic API
to export the saved data, followed by offline decoding; no live acquisition,
reset, flash write or power operation was performed.

Channels: **CMD=0, CLK=1, DAT0=2, DAT1=3, DAT2=4, DAT3=5**.
Acquisition is **500 MS/s**. CMD/DAT sampling uses rising CLK plus eight
acquisition samples (**16 ns**). Independent replays at +24 ns and +32 ns
produce identical decoded event contents, validity results and raw busy boundaries.
This sampling agreement does not establish analog setup/hold margin.

Time zero is the recording's Logic trigger. The raw recording begins at
display **−6.060466260 s**. No qualified power or reset signal is present
in these six channels, so time zero must not be labeled power-on/reset release.
CMD/response timestamps are decoder sampling instants; DAT0 busy boundaries
come from raw pin transitions. Resolution is 2 ns, not guaranteed absolute accuracy.

In `TRANSCRIPT.md`, delta is **start-to-start from the preceding command/response
row**, not response latency, idle time or time since power-on. Durations are
first-to-last sampled bit. The JSON preserves start/end sample indices and
the corresponding display times. Busy intervals and transfer summaries are
kept separate because they overlap the individual events.

There is one CRC-bad startup `CMD63` annotation spanning a clock gap. It is
the previously documented decoder framing artifact, retained explicitly in
the transcript rather than counted as a genuine command. Every genuine
command except CMD0 has one associated response; R3 intentionally has no CRC7.
All 39 read-data packets (SCR plus 38 sectors) also pass their lane CRCs.

These results verify the recorded bus exchange and the card's reported
acceptance/readiness. They do not independently read back the newly saved image,
compare it with camera RAM, establish power-loss durability, or measure energy.

Protocol interpretation uses the local **SD Physical Layer Simplified v2.00**:
command tables in §§4.7–4.8, responses in §4.9 (printed pp58–60),
card status in Table 4-35 (pp62–63), and CID/CSD/SCR in chapter 5.
The evidence distinguishes ACMD41 power-up completion from R1's
READY_FOR_DATA card-buffer bit, and interprets R1 CURRENT_STATE as the
state when the command arrived.

## Reproduction

`binary_replay.cpp` is the frozen offline adapter for the existing native-SD
decoder. Source identities and exported-channel hashes are in `source.json`
and `decode-summary.json`. The original recording and large raw-edge exports
remain local under `tmp/bringup/sd-transcript-20261026/session0/`.

`build_transcript.py` and `human_semantics.py` regenerate the command report
without connecting to any device:

```powershell
python tools/saleae-sd-native/evidence/2026-10-26-session0-transcript/build_transcript.py tmp/bringup/sd-transcript-20261026/session0/events-offset8.jsonl
```

The generator asserts row counts, command/response associations, CRC validity,
monotonic timestamps, read-packet count and final ready status. It preserves
the invalid startup annotation separately.
An independent review compared all 529 generated command/response rows and
39 read-data rows with the canonical events, including every timestamp,
delta, raw field and semantic label. The block appendix was separately checked
for all 3,730 contiguous LBAs, event ordering and sample-derived durations.
