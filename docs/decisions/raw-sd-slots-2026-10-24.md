# Packed RAW SD slots — October 24, 2026

The user selected direct packed RAW10 storage in consecutive SD logical sectors,
replacing PNG/FAT32 for the next prototype. The goals are shorter capture/save
cycles and lower energy, with image conversion deferred to the host. Existing
card contents may be replaced. Four-bit SDMMC and a faster card are planned,
but the current native one-bit, 25 MHz wiring remains in use.

## Format and allocation

Each fixed slot contains one CRC-protected header and 3730 payload sectors.
The 1120 × 1364 image occupies 1,909,600 packed bytes; only its final 352 bytes
need copying into a zero-padded sector. A valid FREE header is claimed as PARTIAL
before payload writes, then marked FULL only after complete capture validation,
sensor STOP and successful card-ready checks. Allocation scans one header per
slot, skipping FULL and PARTIAL. Photos are never silently overwritten.

Explicit FREE records replace the proposed all-blank heuristic. An SD card is a
managed block device: an apparently blank or torn sector is not proof of a clean,
unused image slot. Formatting writes a new generation and all FREE headers,
publishing the READY volume only after that operation completes. Unknown,
inconsistent or damaged headers fail closed. This is not secure erasure or a
guarantee against sudden power loss inside the card's translation layer.

The complete format is specified in [raw-slots](../../firmware/raw-slots/README.md).
The read-only host utility lists slots and reconstructs either packed RAW files
or 16-bit grayscale PNGs with each sample shifted left six bits. PTP/USB export,
per-photo deletion and interrupted-write reclamation remain future firmware work.

## Transfer and power choices

The camera fills a linear RAM buffer once. SDMMC IDMA reads immutable published
prefixes directly; transmitted storage is not reused while capture is active.
The full frame buffer remains necessary because camera delivery is substantially
faster than the current card interface. Transfers use large multiblock commands,
with a smaller first request when only a prefix is available.

The optional LINE producer holds back one full 64-line group. Its hardware test
poisons RAM before capture and snapshots each newly published tail immediately,
so a slow SD reader cannot hide premature publication. This is an engineering
margin with bench evidence, not an explicit cross-master AXI visibility guarantee
in the reference manual. Full-frame validation and sensor STOP precede FULL.

Normal saving performs no image compression, conversion or full-frame software
checksum. Link CRC and header CRC remain, but they do not independently detect
all retained pixel corruption. This prototype supersedes the prior PNG path's
end-to-end pixel checks during every save; full readback comparison is used for
qualification. Durable pixel checksums remain a separate future design decision.

Storage code is loaded from NOR after receiver arming so the larger implementation
does not consume the camera's critical startup budget. The exact early UART
recovery guard remains mandatory. Card deinitialization and the established
peripheral teardown precede MCU Standby; regulator-controlled battery power-off
and complete power isolation remain unqualified.

## Discovery: SDMMC DMA security

An initial IDMA test reported successful SD writes but stored zeros. Full image
readback caught the discrepancy. RIFSC's SDMMC2 configuration-port security
setting overrides the DMA master's security attribute; the configuration port
was nonsecure despite a secure/privileged CID1 master setting. SRAM protection
therefore rejected the reads. Both attributes are now explicitly checked and
configured without relaxing SRAM protection. The corrected deterministic image
matched all 1,909,600 camera bytes after SD readback.

See the [implementation and qualification record](../../firmware/capture-raw/README.md)
for tested builds, measurements, limitations and the final bench state.

## Selected implementation and deferred optimizations

The selected flash image is RAW v15 with hardware IDMA, conservative LINE
publication, asynchronous sensor STOP and final Standby. Three complete cold
cycles of the preceding v12 implementation provide the baseline. Those
cycles measured median 0.793888 s / 0.441400 J on the JS-fed Nucleo branch,
against 2.057802 s / 1.061503 J for the preceding PNG v66c baseline using the
same threshold criteria. Card/image variability and unmeasured supply bypasses
remain; this is not production battery energy or a controlled isolation of each
optimization. Full source-frame comparisons passed in the separate pattern and
awake cold-scene trials. Standby destroys the frame, so later slot readback is
not falsely described as comparison against that lost original.

Shallow CPU sleep during IDMA is **disabled in the selected build**. The first
trial refused missing sleep clocks before entering WFI. A revised trial with
explicit memory/security/interconnect/SD clocks and debug sleep emulation
removed stalled and lost debug access. Warm reset did not recover it. A single
authorized interruption and power restoration returned to the unchanged
working flash image. Two attempted slots remained PARTIAL and were skipped.
The exact cause is unresolved; BSEC sleep-clock retention and Cortex-M55 local
power controls are hypotheses, not established fixes. Future work should first
qualify one WFI with the card idle, then resume active-transfer experiments.

The cold card's 111–118 ms initialization finishes after the ~22 ms frame
acquisition. Consequently the selected cold runs do not overlap payload writes
with acquisition, despite the tested producer supporting that overlap when SD
is ready sooner. The separate preinitialized-card experiment proves actual
before-FRAME writes. The current full frame buffer acts as a bounded producer/
consumer queue; it is retained because the camera is faster than one-bit SD.

Four-bit SDMMC and faster cards can reuse the slot format and producer/transport
interface. Their wiring, negotiation and throughput are not enabled or qualified
by this change. Allocation currently scans from slot zero and therefore grows
with occupancy; an allocation hint and deletion/reclamation are future work.
PNG/PTP export remains host-side/future firmware work. The read-only extraction
utility already reconstructs 16-bit PNGs with the agreed `sample << 6` mapping.

Final review found a retained-RAM freshness bug in early failure handling:
the previous boot's late-loader success marker could survive a warm reset.
V15 clears that marker before initialization, keeping the early load size and
UART recovery instructions unchanged. Executable regression checks cover stale
marker values. A separate cold v15 smoke run passed SBF, UART recovery and full
slot-8 readback/PNG reconstruction, measuring 0.778143 s / 0.424945 J. This is a
single follow-up measurement, not a replacement for the three-run v12 baseline.
