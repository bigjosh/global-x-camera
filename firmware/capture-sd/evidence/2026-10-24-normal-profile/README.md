# Normal capture profile: timing, energy and image qualification

The normal profile disables expensive diagnostic scans while retaining the
capture, format, canary, code, SD and shutdown checks described in the
[firmware README](../../README.md). Finer counters separate encoder CPU work
from synchronous SD callbacks. DMA and concurrent double buffering are unchanged.

The selected **v66c normal Standby** sector is
`8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61`.
Full 64 KiB programmer readback matched and the following 4 KiB was unchanged.
The SAVE module is byte-identical to the separately qualified v64 awake image.
See [exact build and correction](build/v66-addendum.md) and
[installation evidence](results/installation-v66/README.md).

## Complete cold cycles

Three consecutive final-firmware trials completed the ten source-ordered
phase checkpoints and reached the low-current plateau. Each was then recovered
on the first warm PE6 UART request, with the exact early park verified and
hardware SBF set. No SWD access occurred during capture or the measured plateau;
no target power-off intervened between each plateau and its SBF observation.
The original SBF reader reports history only; separate owner attestations bind
that history to the cycle and the verified firmware's pre-entry flag clear.

| Final trial | Current onset → plateau | Energy to plateau | Plateau current |
|---|---:|---:|---:|
| standby02 | 1.933433 s | 0.992903 J | 8.172 mA |
| standby03 | 2.057802 s | 1.061503 J | 8.070 mA |
| standby04 | 2.082825 s | 1.080464 J | 8.057 mA |
| **Median** | **2.057802 s** | **1.061503 J** | **8.070 mA** |

The previous v59 baseline medians were 2.714624 s and 1.288948 J. Applying the
same native-sample onset and quiet-tail criteria gives observed median
reductions of **24.2% in time** and **17.6% in energy**. The old runs were
signature-qualified and used different captures; this is not a controlled
same-frame test of diagnostic removal alone. Card latency, scene contents,
instrumentation and code layout can affect the comparison.

Energy uses synchronized JS110 power samples without host-time or Saleae
alignment. The separate one-second plateau confirmation costs about 0.039–0.040 J
and is excluded from the cycle figures above. The endpoint includes any settling
before the stable current plateau; it is not an exact WFI timestamp. All three
recordings passed identity, sample-coverage and finite-data checks within their
analysis windows. Initial nonfinite samples are outside those windows.
The measurements cover the JS-fed Nucleo branch, with the existing CN8/debug
bypass limitations; they do not establish isolated MCU or production battery
energy. Raw sample files remain local. See [energy records](analysis/energy/summary.json)
and [analysis/replay procedure](analysis/README.md).

## External phase timing

These are representative source-ordered Saleae intervals: the prior v61b
diagnostic trace versus the median-duration final v66c run, standby03. The
strict pulse-width decoder failed on both and remains failed. Labels are
inferred from the exact firmware's call order, ten complete ordered pulses
and independent successful execution evidence. CH4 marks a digital threshold,
not qualified analog power-good. Interrupt observations include interrupt latency.

| Phase | Prior diagnostic trace | Normal v66c |
|---|---:|---:|
| Target 5 V threshold → reset release | 1.632 ms | 1.617 ms |
| Reset release → receiver entry | 21.511 ms | 21.385 ms |
| Receiver entry → first STROBE IRQ | 1.306 ms | 1.299 ms |
| STROBE IRQ → complete-frame IRQ | 21.861 ms | 21.861 ms |
| Frame IRQ → SAVE entry | 457.105 ms | 72.988 ms |
| SD initialization | 117.091 ms | 98.100 ms |
| FAT32 mount | 1.681 ms | 1.519 ms |
| Pre-write checks, file open, PNG encode and synchronous output | 1629.171 ms | 1799.104 ms |
| Final buffer flush and file commit/close | 22.034 ms | 24.317 ms |
| Post-save checks, SD deinit and cache cleanup | 447.148 ms | 0.128 ms |
| Final bookkeeping and shutdown → pre-WFI marker | 13.260 ms | 13.602 ms |
| **5 V threshold → pre-WFI marker** | **2733.800 ms** | **2055.920 ms** |

The long frame diagnostic pass and final uncached hash are removed. The
remaining roughly 73 ms before SAVE includes essential checks, sensor STOP,
save-module loading/CRC and entry initialization. The larger encode/output
interval here is observed rather than attributed to one cause. This comparison
does not isolate scene/card variation or all instrumentation/layout costs.

## Fine timing inside SAVE

The awake v64 trial retains the same final SAVE module and its RAM counters.
Its 1,452,183-byte IMG67 was read back and compared with every retained RAW
sample. These times assume nominal 400 MHz and include timer overhead; they
are a different run and clock domain from the external table above.

| Disjoint SAVE work | Nominal CPU time |
|---|---:|
| SD initialization | 109.758 ms |
| FAT32 mount | 1.685 ms |
| Free-space check, filename search and file open | 60.287 ms |
| Sample conversion, range validation and filter work | 131.504 ms |
| DEFLATE including Adler checksum, excluding output | 786.468 ms |
| PNG framing/CRC/headers, excluding callbacks | 33.871 ms |
| Synchronous output callbacks, including buffering and SD | 552.292 ms |
| Final partial-buffer flush | 5.643 ms |
| File commit and close after flush | 18.075 ms |
| Remaining checks, bookkeeping and timer residuals | 1.614 ms |
| **SAVE COMPLETE interval** | **1701.197 ms** |

The [integer-cycle partition](analysis/records/awake02/fine-analysis.json)
sums exactly. `FINISH` includes the flush, and inclusive DEFLATE/framing/driver
counters overlap the rows above; do not add them again. Encoding currently
pauses during output callbacks. DMA could allow overlap, but this measurement
does not predict the achievable overlap or energy saving.

Receiver counters separately measured about 34.901 ms in sensor STOP,
7.247 ms in NOR load/CRC and 27.801 ms between that CRC and SAVE timing entry.
The last interval includes loader tail, entry setup, BSS clearing and report
initialization. The uncached BSS loop's changed alignment is a candidate for
a later experiment, not a proven explanation. The external versus nominal-DWT
SAVE duration differs by about 0.7%; neither clock was calibrated against the other.

## Image verification and remaining scope

The corrected awake v64 IMG67 passed every PNG chunk CRC and all 1,527,680
pixels matched the retained RAW10 samples shifted left six bits. Earlier
provisional IMG66 also passed exact pixel comparison, but its overwritten
receiver proof disqualifies it as the final profile reference. See
[awake records](results/README.md) and the separate verification addendum.

Full readback after Standby passed for all three measured files and the image
saved before v65 refused shutdown:

| Trial | File | Bytes | SHA-256 |
|---|---|---:|---|
| v65 shutdown refusal | IMG00068.PNG | 1,453,010 | `9e3cd8f0ac601bea9c261b714e5677d294fab6d332a38355672a408e79a85844` |
| standby02 | IMG00069.PNG | 1,466,450 | `239773be96c41f01b926bbf700db7f2d9dd66db858865ce5687193149673e8f1` |
| standby03 | IMG00070.PNG | 1,455,077 | `3e25da67d86b6ce29cce539a5e1e00c5930bf3b25230bf476e5b6bb796b21a11` |
| standby04 | IMG00071.PNG | 1,455,989 | `2ba9d8f873cbc2eb6d5ead707680965dbb9ed87fa450675a22c7ca3084ea58a2` |

Every PNG chunk CRC passed, each file decoded completely as 1120 × 1364
grayscale16 with `sBIT=10`, every sample had zero low six bits, and each had
discernible dynamic range. Visual inspection of IMG71 showed a recognizable
room scene. Original IMG00001.PNG remained byte-identical to its October 20
hash, `466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330`.
The read-only bridge reported zero written sectors throughout; independent
full NOR readback afterward still matched the installed v66c sector.
The [compact readback archive](results/standby-png-readback/README.md)
retains all 27 requests and their terminal proofs without the image payloads.

Standby loses the RAW frame, so these are full-file integrity and format
checks, not comparison against lost capture pixels. The separate awake v64
test supplies the exact pixel comparison for the same SAVE module. Image
bytes remain local, outside this archive.

## Final bench state

After all readback, the first 64 KiB of NOR independently matched v66c again.
One final normal cold boot produced ten complete ordered phase pulses and
returned to the low-current plateau. JS110 stopped cleanly at
**2026-10-24 02:39:05.697 UTC**, restored its original range 128 and left target
power on. Last measurement: **4.892853 V / 8.069970 mA**. No further UART reset,
SBF inspection or PNG readback followed; **IMG00072.PNG is only the expected
next filename**, not a verified file. This final return-to-service cycle is
not included among the three qualified energy trials.

COM8 is closed, BREAK released, Logic 2 remains running and no bench helper
is active. CN10 remains connected. Power is CN8 → CN9.3 → JS110 IN+ → OUT+ →
CN9.2, without CN9 shunts. D2/R23 are removed, GPIO banks remain 3.3 V and both
boot jumpers remain on pins 1–2. The native one-bit SD wiring is unchanged.
Saleae probes remain CH1=PD12/CN15.21, CH4=target5V/CN3.18, GND=CN3.19,
CH0=NRST/CN3.14 and CH6=PE6/CN15.2. The PE1 external wire remains disconnected.
Recheck ownership/wiring before the next hardware experiment.
The [final checkpoint](results/final-checkpoint/README.md) binds the original
NOR, current-signature, cleanup and phase records without upgrading their scope.

## Corrections, tests and reproducibility

- The first RCP2 address overlapped LED1. It was moved to `0x343F8A80`; the
  full region map now rejects that overlap. Its failed proof is preserved.
- v65 saved IMG68 but a stale schema gate refused shutdown before late XSPI
  activity. v66c fixes schema/profile checking. [v65 evidence](results/v65-refusal/README.md)
  remains a failed-shutdown result and is excluded from the energy baseline.
- Two guarded NOR programming attempts encountered WEL completion errors.
  Readback preserved the partial contents before repair. A separate v2 helper
  polls fresh status through both WIP and WEL completion with bounded deadlines;
  its successful use does not establish the original fault's cause. See
  [NOR evidence and qualification](nor-maintenance/README.md).
- Focused coverage includes 112 SAVE, 108 peripheral and 132 late-loader
  actual-C cases, 24 receiver cases, region-overlap regressions, 22 PNG cases,
  10 READ-bridge tests, exact recovery review and byte-identical ARM rebuilds.
  Diagnostic-profile hardware behavior and arbitrary SD power loss remain unqualified.

`verify_build.py`, `verify_v66.py`, the result-specific verifiers and
`analysis/replay.py` validate the compact archive. Portable build recipes retain
exact source/tool identities. Compact evidence verification does not re-read
the physical card or re-decode image bytes omitted from this public archive.
