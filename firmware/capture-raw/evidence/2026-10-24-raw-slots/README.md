# RAW-slot storage evidence — October 24, 2026

This archive preserves the completed RAM experiments that established packed
RAW10 capture, fixed-size SD slots and the first camera-to-SD overlap, followed
by the v9 NOR installation and a cold capture ending in an awake park. It keeps
the failed initial IDMA readback, failed v9/v14b DMA-WFI experiments, and the
subsequent v12 polling Standby-image installation. It does not
infer the current bench state. Three subsequent v12 cycles now have separately
attributed SBF observations and complete-cycle board-branch energy measurements.
Separate SD readbacks preserve the original photo and validate the later slot-6
read/decode, with the original slot-6 sensor frame unavailable after Standby.

**Selected firmware is now v15**, which clears the retained late-loader success
token at each boot. Its separate qualified smoke cycle measured **0.778143 s /
0.424945 J** and passed warm recovery, SBF and full slot-8 read/decode. The v12
three-cycle measurements below remain the v12 baseline.

| Record | Preserved result |
|---|---|
| `format128-01` | Host refused before a completed RAW-format proof; retained as a refusal, not a format success. |
| `format128-02` | Explicit logical format initialized 128 slots. |
| `pio-pattern01` / `read-slot0` | All 1,909,600 captured bytes match the SD payload; padding and headers pass. |
| `idma-pattern01` / `read-slot1` | Controller reported success, but all 1,909,600 SD payload bytes were zero and differed from camera RAM. This build failed image integrity. |
| `rif-diagnostic01/02`, `rif-port-diagnostic01` | Preserve the incomplete first diagnostic, subsequent RIF violation records, and observed nonsecure SDMMC2 configuration-port attributes. |
| `idma-secure-pattern01` / `read-slot2` | Corrected secure configuration-port build matches every captured byte on SD. |
| `line-pattern01` / `read-slot3` | With SD initialized before capture, the first 175-sector write starts before FRAME. All 20 immediate 512-byte producer snapshots and the full SD payload match the final pattern. |
| `format-full01` | Logical format completed all 32,834 available fixed-size slots. This checks header initialization, not physical full-card capacity or power-loss behavior. |
| `nor-before01`, `nor-following-before01`, `flash-awake-write01`, its diagnostic, `nor-following-after01` | Complete v9 NOR readback matches the intended sector; the following 4 KiB is unchanged. |
| `awake-cycle01`, `awake-inspect02`, `awake-profile01` | Cold normal boot reaches a complete RAW save and an awake terminal with idle/deinitialized SD. Its strict Saleae phase decoder failed and remains failed; this is not a Standby run. |
| `read-scene-slot0` | Historical full SD comparison matches all 1,909,600 scene bytes and 160 zero padding bytes. The comparison, metadata and hashes remain; scene pixels are omitted. |
| `wfi-pattern01`, `wfi-failure-diagnostic02` | DMA-WFI v9 fails with SD error 21 after 1,024 payload sectors, without committing the slot. Separate diagnostics observe camera reset asserted and SD idle/deinitialized. |
| `wfi-pattern02`, `wfi-pattern02-observe01`, `wfi-stalled-js`, `recovery-vcp09`, `early-park09` | DMA-WFI v14b loses core/SRAM access. A measured UART/reset attempt does not restore it. No completion or storage-idle proof is available. |
| `wfi-abort-cold-recovery01`, `wfi-abort-restored-observe01`, `abort-restored-inspect01` | The user-authorized interruption explicitly records unknown storage state. A host-call error causes helper cleanup to restore its starting power range; normal v9 subsequently commits slot 3 and passes exact terminal inspection. This is not a qualified recovery or power-loss test. |
| `nor-before02`, `flash-standby-write01`, its diagnostic, `nor-following-after02` | Polling v12 image installation passes exact 64 KiB readback and unchanged following 4 KiB. Installation alone does not establish Standby behavior. |
| `standby-cycle01/02/03`, corresponding warm recovery/park/SBF records | Each cold cycle is followed by exact warm PE6 recovery and SBF=1. Root attests the preceding flag clear and absence of intervening power-off. |
| `standby-three-cycle-analysis` | Uses the same native-sample energy method and current-boundary criteria as v66c. Strictly decodes events 1–9; the final pulse remains unknown. |
| `standby-three-cycle-compacts` | Exact native-sample sum bins reproduce all twelve selected energy intervals without retaining the large raw waveforms. |
| `final-headers01` | CRC-valid slot headers show `FULL, PARTIAL, PARTIAL, FULL, FULL, FULL, FULL, FREE` for slots 0–7. |
| `read-standby-slot6` | Complete payload read, zero tail padding, valid header and independently decoded PNG matching the retrieved RAW samples; no comparison to the lost original sensor frame. |
| `reread-scene-slot0` | Original payload remains byte-identical to its original camera frame after failed WFI trials and later captures. Pixels are omitted; reports, hashes and read-only completion proofs remain. |
| `standby-cycle04` and its `final-state.json` attachment | Final normal boot returns to the low-current plateau. Expected slot 7 and SBF were not reread; this remains a power signature only. |
| `v15-install`, its diagnostic, `v15-following-after`, frozen `offline-review.json` | Corrected v15 installation passes full 64 KiB readback and unchanged following 4 KiB. Frozen source and prefix differences bind the guard fix to its exact build. |
| `v15-cycle01`, `v15-recovery01`, `v15-park01`, `v15-sbf01` | One corrected-firmware smoke cycle passes exact warm recovery and separately attributed SBF. |
| `v15-read-slot8`, `v15-read-slot8b` | First attempt fails in host preflight before hardware access; retry reads the full slot and verifies CRC/padding/PNG conversion. Original sensor RAM comparison is unavailable after Standby. |
| `v15-smoke-analysis`, `v15-smoke-compacts` | One-run measurements and four replayable signed energy intervals, kept separate from the v12 baseline. |
| `v15-cycle02-final` and its `final-state.json` attachment | Latest normal boot ends at the observed plateau. Expected slot 9 and SBF were not reread. |

The nine frozen builds are `ram-pio-v3`, `ram-idma-v3`,
`ram-idma-secure-v6`, `line-pattern-v2`, `ram-line-wfi-v9`, and
`flash-awake-line-v9`, plus failed `ram-line-wfi-v14b` and polling
`flash-standby-line-v12`, and corrected `flash-standby-line-v15`. Their original generated C/headers,
linker/startup sources, manifests, symbol tables and binary bytes are preserved
exactly. The archive verifies source hashes, binary hashes, initial vectors,
terminal loops, executed-code readbacks and binary/JSON completion proofs.
External vendor headers and compiler installation are not duplicated, so this
is a durable source/evidence archive rather than a portable toolchain bundle.

The replay checks 97 terminal proofs across 76 record groups, three successful complete SD
payload comparisons, and the failed zero-filled payload. It independently
decodes all 1,527,680 pixels in each pattern frame and compares them against the
native16 test-pattern reference preserved in the earlier
[packed RAW10 archive](../../../capture-packed/evidence/2026-10-24-packed-raw10/README.md).
The scalar decoder also runs 4,096 position/value vectors. The LINE replay
checks each source range against the watermark recorded **before** submission,
and checks every immediate ISR snapshot. These observations qualify this tested
configuration; they do not provide a PVT-wide DMA visibility guarantee.

The historical v9 installation used sector
`dd4db5228d3a4fe9c352630201bacfe1dfd08888725e6f5a63be2a4fb82392bc`.
The retained scene comparison reports payload SHA-256
`60bb1a242a8edbd7afc8bc1d3582af5cba3191fe48f2b6b1bc70ead448e1657f`;
replay verifies its bindings to capture/readback records and the omitted-file
hashes. It cannot independently recompare pixels that are intentionally absent.
The cold measurement's large raw Joulescope arrays are also omitted with their
identities retained; its chunk manifest, recording summaries and profile remain.
No energy value is inferred from an awake terminal or a failed phase decode.

The later v12 install sector is
`03cbd89553944838922bbcd7e2b21813297f3466db64730c5e3e2903a7942424`.
The failed v14b RAM image remains archived under its own identity,
`a7a35d1cee7bce3602af60ad4a6aa0512c0861e31eae9651ea5db994f4426a68`;
it is not selected firmware. The restored v9 capture uses the same volume
generation and performs no format. Its slot-3 success does not prove the
contents of either interrupted slot or revalidate previously saved photos.

## Qualified v12 Standby cycles

| Cycle | Current onset → stable Standby plateau | Signed energy over that interval | Plateau current |
|---|---:|---:|---:|
| 01 | 0.807867 s | 0.441400 J | 8.080 mA |
| 02 | 0.789634 s | 0.431091 J | 8.188 mA |
| 03 | 0.793888 s | 0.441541 J | 8.192 mA |
| Median | **0.793888 s** | **0.441400 J** | — |

The measured median time and energy are 61.4% and 58.4% below the prior v66c
PNG/FAT32 baseline. These are observations across different scenes, formats and
card latencies, not an isolated attribution to one optimization. One second of
plateau confirmation contributes another 0.0395–0.0401 J and is reported
separately from the headline energy.

This is the JS-fed Nucleo branch, with board overhead and unmeasured bypass paths;
it is not isolated battery energy. The raw approximately 7.4 A startup samples
are included in the signed integral under the unchanged 9.5 A validity criterion.
Their physical origin is unqualified: no clipping, range-change correction,
inrush interpretation or analog calibration is inferred. The three large native
waveforms are omitted with hashes; compact reports retain their native sample
boundaries and exact input identities. The compact waveform sums reproduce all
twelve selected interval energies, without rerunning the original sample-order
onset/plateau classification. JS and Saleae have independent clocks,
so no phase energy is assigned.

Replay checks SBF register bytes, immutable recovery-prefix bytes, owner
attribution and the phase transitions themselves. The last approximately
20.49 µs pulse exceeds its configured width tolerance and stays unknown; it is
not used to infer a pre-WFI time. SBF provides the separate Standby evidence.

The two failed WFI trials leave slots 1 and 2 `PARTIAL`; later captures skip them.
Slots 4–6 are `FULL`. The slot-6 readback is 1,909,600 bytes with SHA-256
`c9accb0737093bbdff1d102faf463e83b53b975411d007fb63554b4bebb5f95a`.
Its PNG conversion reproduces the retrieved samples, but the original sensor
frame was lost in Standby, so this does not establish original-frame equality.
The original slot-0 reread retains its earlier `60bb…1657f` SHA-256 and exact
camera-frame comparison. This limited preservation observation does not qualify
arbitrary SD power loss.

## Historical v12 handoff

At **2026-10-24 06:42:34 UTC**, v12 remains installed with the sector hash above.
The target is powered, JS110 restored range 128, and no bench helpers are active.
The last measured input is **4.892563 V / 8.184977 mA**. COM8 is closed, BREAK is
released, Logic 2 remains running, and JP1/JP2 remain on pins 1–2. Power routing
is CN8 → CN9.3 → JS110 IN+ → OUT+ → CN9.2, with no CN9 shunts; CN10 is connected,
D2/R23 are removed, and banks remain at 3.3 V.

This final fourth cycle was left at the plateau without another recovery or SD
read. Its expected slot 7 and SBF are **not verified**. The three qualified cycles
and final readbacks precede it. The exact final-state attachment binds those
records by hash. This timestamped handoff is preserved unchanged and is
superseded by the v15 handoff below.

## Selected v15 and latest handoff

Final review found that retained SRAM could leave a previous boot's `RLOK`
late-loader success token visible to a later boot. v15 clears it before any
failure path can rely on late code being valid for the current boot. The source
audit and exact prefix changes are preserved in its frozen `offline-review.json`;
the early recovery code remains unchanged. The selected sector is
`efb3c440e008e448a1682285034fe30b77bdbb5834024da9de787f3f51f42629`,
with prefix
`db234498a9b347f6cb9f41daf22da1fb0f9266dba264b9ca203ef33d1b1711df`.

The qualified v15 smoke cycle measured **0.7781425 s / 0.4249452233 J** from
current onset to the stable Standby plateau. First-attempt warm PE6 recovery and
SBF passed. Slot 8 passed complete payload read, header CRC, zero padding and PNG
sample comparison against the retrieved RAW. Its payload SHA-256 is
`0b0fe7e105f14353628f5fccbc547a760a3133b05f4517853b76c0999ec542c1`.
The original sensor frame was lost in Standby; this is not original-frame
equality. This is one run, not a replacement three-run baseline. Compact replay
reproduces its four energy intervals, in addition to the twelve v12 intervals.

At **2026-10-24 06:57:36 UTC**, the final v15 cycle left power on at
**4.892899 V / 8.179419 mA**. JS110 restored range 128; helpers are stopped,
COM8 is closed, BREAK is released and Logic 2 remains running. Wiring and boot
jumpers are unchanged from the historical handoff above. The final expected
slot 9 and SBF were **not reread**; its plateau and events 1–9 are a signature
only, and the final pulse remains unidentified. Recheck bench ownership before
future hardware work.

## Replay or extract

From the repository root:

```powershell
python firmware/capture-raw/evidence/2026-10-24-raw-slots/replay.py
python -m unittest discover -s firmware/capture-raw/evidence/2026-10-24-raw-slots -p 'test_*.py' -v
python firmware/capture-raw/evidence/2026-10-24-raw-slots/materialize.py --build line-pattern-v2 --out tmp/raw-line-frozen
python firmware/capture-raw/evidence/2026-10-24-raw-slots/materialize.py --record line-pattern01 --out tmp/raw-line-record
python firmware/capture-raw/evidence/2026-10-24-raw-slots/materialize.py --record standby-three-cycle-compacts --out tmp/raw-energy-compacts
python firmware/capture-raw/energy_compacts.py replay --folder tmp/raw-energy-compacts
python firmware/capture-raw/evidence/2026-10-24-raw-slots/materialize.py --record v15-smoke-compacts --out tmp/raw-v15-energy-compacts
python firmware/capture-raw/energy_compacts.py replay --folder tmp/raw-v15-energy-compacts
```

All commands above are offline. Extraction requires a new destination and
refuses path traversal or overwriting an existing directory. `qualification.json`
records the latest successful replay. `index.json` maps every retained artifact
to a content-addressed object, with SHA-256 and exact uncompressed/stored lengths.
Text line endings are preserved. `.gitattributes` prevents Git text conversion
from changing hashed bytes. Pattern frames use lossless compression and dedup;
no actual scene-photo pixels are included.

Repeated debugger text and intermediate proof polls are omitted where final
proofs and structured call logs suffice; each omission retains its filename,
size, hash and reason. Small diagnostic/refusal CLI logs remain. Complete SD
payloads and their original read transactions remain replayable, including the
failed payload. Hardware tools are archived as archive-time source snapshots;
replay never imports or executes them.

## Extend with later completed evidence

Add explicit record entries to `selection.json`; do not select active runs.
Use `pixels: "omit"` for all scene captures. The `pattern` policy requires a
passed capture record with pattern=1 and matching frame hash; a readback points
to that capture using `capture`. The script discovers exact builds from selected
`plan.json` files. Additional frozen builds can be listed in `extra_builds`.
Explicit `attachments` preserve small text logs saved outside a record folder.
Explicit `metadata_sectors` permit only 512-byte RAW metadata sectors with valid
magic and CRC; scene payload sectors remain excluded.
All source locations must stay inside the repository.

```powershell
python firmware/capture-raw/evidence/2026-10-24-raw-slots/archive.py
python firmware/capture-raw/evidence/2026-10-24-raw-slots/replay.py --out firmware/capture-raw/evidence/2026-10-24-raw-slots/qualification.json
```

Objects are immutable. Before updating the main index, the prior exact index
is saved under `indexes/<sha256>.json`; its referenced objects remain available.
Later cold-cycle records need additional replay assertions for their own
power/Standby evidence. Merely archiving a record does not qualify it or change
the historical failed IDMA result.
