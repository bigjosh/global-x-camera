# October 23: native one-bit SD baseline

This archive records the current one-bit SDMMC2 implementation before changing
the breakout or negotiating four-bit operation. Three fresh runs of the
**unchanged v59** firmware measured **1.279–1.291 J** over **2.685–2.721 s** from
observed current onset to a selected low-current plateau. These are measurements
of the JS110-fed Nucleo branch, not card-only energy or a precisely timed
power-good-to-Standby interval.

The separate instrumented firmware has useful phase edges, but **its strict
pulse-width qualification failed**. Its original failed decoder output remains
intact. Any labels assigned below from the reviewed source order are explicitly
inferences, not successfully decoded event IDs.

The baseline is complete. Three same-frame SAVE repetitions passed full PNG
readback, and the original v59 firmware was restored and independently verified.
No camera pixels, RAW frame, PNG file contents, or large native waveforms are
published here.

## What was measured

The SD interface remains native one-bit SDMMC2 at 25 MHz and 3.3 V, using
PC2/PC3/PC4 for CLK/CMD/DAT0 and PE4 as an input with pull-up on the breakout's
unused DAT3/CS connection. The chosen encoder is the cached, `-Os`, byte-safe
v8b fast-none implementation. The current measurement boundary includes the
Nucleo circuitry supplied through JS110; remaining CN8/debugger paths are
outside it. Source voltage means JS IN+, not the downstream target rail.

| Unchanged-v59 recording | Current onset to plateau (s) | Energy over that interval (J) | Plateau mean current (mA) |
| --- | ---: | ---: | ---: |
| repeat-01 | 2.714624 | 1.291083 | 8.1804 |
| repeat-02 | 2.721454 | 1.288948 | 8.1865 |
| repeat-03 | 2.684675 | 1.278877 | 8.1910 |

The descriptive medians are 2.714624 s, 1.288948 J, and 8.1865 mA. The separate
one-second plateau confirmation tails used about 0.040 J each and are excluded
from the interval energy above. The detector uses measured current onset and
1 ms plateau bins; settling can affect that boundary. Current alone does not
prove WFI, Standby, or a valid saved file, so the individual energy records keep
their completion and terminal qualification flags false. These three samples
are not a worst-case or population guarantee. The scene also differs from
October 20, so the difference from earlier measurements is not an optimization
result. See [summary and limits](energy/summary.json), the
[plot](energy/cold-baseline.png), and the hash-bound [manifest](energy/manifest.json).

The earlier five-cycle recording had incomplete raw coverage. It is retained
under [failed-five-cycle-recording](failed-five-cycle-recording/) and excluded
from the baseline; no missing samples were filled in.

## Probe and firmware qualification

The probe test first found a real connection problem: the MCU's PD12 input
readback followed all six commanded levels, but Saleae CH1 remained near zero.
After the user reseated the connection, all six physical transitions were
observed, with approximately 3.35 V HIGH. GPIO configuration was restored, and a
fresh exact v59 recovery-park check passed. The retained compact evidence
distinguishes that failed first test from the successful second test. See
[probe records](probes/README.md).

The instrumented pin is **PD12 / CN15 pin 21**, also Arduino D8 / CN14 pin 1.
The intended encoding is a HIGH pulse of event ID multiplied by 0.5 microseconds
at the existing 400 MHz CPU clock. The nominal total HIGH time for all ten
events is 27.5 microseconds; total execution and extra NOR-loading overhead are
not established by that number. No timing-overhead correction is subtracted.

| Firmware | Purpose | Full 64 KiB sector SHA-256 |
| --- | --- | --- |
| v59 | Unchanged baseline and intended final restoration | `7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63` |
| v60c | Instrumented awake capture; retained frame for repeated SAVE | `20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e` |
| v61b | Instrumented complete capture/save/Standby path | `cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f` |

The isolated overlays preserve the early recovery logic and its exact park.
The original v59 and canonical v8b artifacts remain unchanged. The awake
diagnostic uses the established maintenance architecture, rather than relaxing
the late-completion ownership guards. Source copies, manifests, firmware
payloads, and portable rebuild instructions are in [build](build/README.md).
Both instrumented sectors rebuilt byte for byte; see
[rebuild verification](build/rebuild-verification.json).

The first v61 installation encountered the NOR helper's WEL-clear failure.
That failed operation remains failed. Explicit repair from independently read
partial contents, using the same guards, was followed by exact full-sector
readback and a check of the following 4 KiB. See the
[NOR incident and repair](nor-maintenance/README.md); the cause of the observed
WEL state is not established.

## Instrumented v61: timing by source-order inference

The full NOR sector was independently read before the run. Ten complete PD12
pulses had LOW capture boundaries; a later guarded warm recovery observed
SBF=1. Those facts support a separate interpretation using the reviewed source
call order. The pulse widths were 0.74, 1.24, 1.74, 2.56, 2.73, 3.07, 3.58,
4.07, 4.87, and 5.34 microseconds. The strict tolerance was not widened, and
`width_qualification` remains false.

| Checkpoint inferred from source call order | After observed NRST release (ms) |
| --- | ---: |
| Receiver main entry | 21.511 |
| First STROBE interrupt observed | 22.817 |
| First complete-frame interrupt observed | 44.679 |
| SAVE entry | 501.784 |
| SD initialization complete | 618.875 |
| FAT32 mount complete | 620.556 |
| PNG encode complete | 2249.727 |
| File close/rename/card-ready complete | 2271.761 |
| Cache cleanup, uncached frame validation, and snapshots complete | 2718.908 |
| Pre-Standby WFI checkpoint | 2732.168 |

These are same-capture GPIO edge intervals. STROBE includes interrupt latency,
event 7 precedes any remaining buffered-tail flush, event 9 precedes COMPLETE
and terminal publication, and event 10 precedes physical WFI entry. The digital
5 V crossing is not analog power-good. SBF is historical since its last
clear/POR; attribution also depends on the recorded reset and power history.
Neither the edge analysis nor SBF verifies that run's PNG contents. See the
[complete timing table](phase/v61-cycle-01/timing.md),
[machine-readable analysis](phase/v61-cycle-01/ordered-analysis.json), and
[independent analysis method](phase/README.md).

This instrumented run separately measured 1.302543 J over 2.734223 s from current
onset to plateau. Do not pool it with the unchanged-v59 repeats or interpret
the difference as measured marker overhead. Saleae and Joulescope clocks are
not synchronized, so no phase-specific energy is inferred. See the
[instrumented energy record](instrumented-energy/v61-cycle-01/README.md).

## Instrumented v60: verified automatic image

The awake diagnostic saved `IMG00061.PNG`, 1,458,185 bytes, and its strict
maintenance proof confirmed completed file/card operations, caches off, and an
idle/deinitialized SD controller. The firmware COMPLETE interval was
2.214401 s, including 0.380690 s of uncached frame validation. The driver wrote
1,462,272 bytes in 0.573696 s, about 2.549 MB/s; these bytes include filesystem
traffic. Encoder wall time includes write callbacks, so those times must not
be added together as independent costs.

A later six-chunk readback verified all PNG chunk CRCs, `sBIT=10`, and all
1,527,680 pixels exactly against the retained RAW samples shifted left by six
bits. PNG SHA-256 is
`656a89149100e3e5789adeda9b48703357903358a869bd926e5f92ac4320ecb2`.
The original timing record's pending readback state is preserved; the later
[verification addendum](automatic-save-v60/verification-addendum.json) supplies
the outcome. See [metrics](automatic-save-v60/metrics.json) and
[maintenance proof](automatic-save-v60/maintenance-result.json). This verifies
that named image, not every earlier cold-cycle image, and is not an awake
cold-cycle energy measurement.

Three subsequent SAVE requests reused the same retained RAW frame and completed
successfully as `IMG00062.PNG`, `IMG00063.PNG`, and `IMG00064.PNG`, each
1,458,185 bytes. Firmware COMPLETE measured 2.102061, 2.104129, and 2.099228 s.
The separately inferred GPIO entry-to-validation intervals were 2.113330,
2.115049, and 2.109927 s. Different endpoints and time bases are preserved;
the approximately 11 ms difference is not corrected or attributed to a known
cause. All three strict pulse-width decodes still failed. The
[v60 phase addendum](phase/v60-README.md) links the six-pulse timing tables,
successful request/terminal proofs, and exact loaded-code checks. Subsequent full
readbacks of all three files passed every PNG CRC and pixel comparison; their
bytes are identical to IMG00061.PNG. The original pending records remain
unchanged, with the outcome in the [verification addendum](same-frame/verification-addendum.json).

Median same-frame COMPLETE was **2.102061 s**, including **0.380714 s** of final
uncached frame validation. Encoder time excluding output callbacks was
**0.931825 s**, and measured SD driver write throughput was **2.64996 MB/s**.
These warm-card repetitions are distinct from a cold boot. Conditional
COMPLETE-duration energy bounds have median lower/upper values of
**0.951779–1.023486 J**, assuming the reported 400 MHz clock and the explicitly
selected UTC uncertainty; they are not synchronized phase-energy measurements.
See [the repeated-save comparison, scopes and replay](same-frame/README.md).

At the same 25 MHz, a payload-only model of four-bit operation removes roughly
**0.374–0.376 s** from these saves, about **17.8%**, holding other work constant.
This is an optimistic comparison model, not a measured result or strict bound.
Compression, initialization, validation, command handling and card busy time
do not automatically scale with bus width.

## Controlled comparison after a four-bit breakout change

Use the same card, input pixels, PNG mode/encoder, CPU and cache settings,
filesystem configuration, and supply/debugger topology. Record at least three
same-frame SAVE operations on each bus configuration, with payload size/hash,
driver bytes and elapsed cycles, file completion, cache cleanup, and exact PNG
readback. Keep full cold-cycle energy separate from a retained-frame storage
benchmark. Card busy time, metadata, initialization, and CPU work remain costs
even when the bus gets wider; a fourfold bus rate is not a fourfold total-save
speed guarantee.

The physical swap may require removing power and therefore lose the retained
RAW frame. An identical-input comparison then needs a reviewed method to load
the same input while retaining valid maintenance ownership and proofs. Do not
fabricate a capture trace or weaken those guards. If identical input cannot be
established, label the result as a different-frame comparison. Preserve the
one-bit artifacts and old-photo hashes so the later result can be compared
without changing this record.

## Final restoration and archive replay

The original v59 sector was restored successfully. Both the programmer's full
64 KiB readback and a separate frozen read-only helper matched SHA-256
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
The following 4 KiB remained byte-identical to the pre-experiment copy. Warm
PE6 UART/BREAK recovery reached the exact v59 early park with nine accepted
pulses and zero bad pulses. One subsequent normal cold boot returned to the
low-current plateau. See [restoration evidence](final-restore/README.md).

At **2026-10-24 00:08:47 UTC** (October 23 locally), JS110 stopped cleanly,
restored its starting auto range 128 and left the target powered. Its last
measurement was **4.892616 V / 8.067146 mA**. COM8 is closed, BREAK released,
Logic 2 remains running, JP1/JP2 remain on pins 1–2, and no bench helper is
active. CN10/ST-LINK USB is connected; CN8 supplies JS IN+ via CN9.3 and JS OUT+
feeds CN9.2, with all CN9 shunts absent. D2 and R23 remain removed.

The final cold cycle is qualified only by its power signature: its new image
was not read back and SBF was not reread. The separately verified named images
are IMG00061.PNG through IMG00064.PNG. The PD12 phase overlays are archived but
are no longer installed. Probes can remain attached: CH1→CN15.21, CH4→CN3.18,
GND→CN3.19, CH0→CN3.14 and CH6→CN15.2. Recheck ownership and physical wiring
before the next bench operation.

From this archive directory, `python verify_build.py` checks the frozen build
inventory, and `python rebuild.py --help` describes portable reconstruction.
Each energy subtree has its own offline replay and hash manifest. The phase
subtree has a separate index and rejection tests; it does not modify the strict
decoder. Compact bins preserve recorded sums, extrema, and checked integrals,
but not raw within-bin sample order. The original local acquisition evidence
is under `tmp/bringup/sd-baseline-20261023`; source paths and omitted large-file
hashes are recorded in the corresponding subtree manifests.
