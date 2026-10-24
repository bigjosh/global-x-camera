# Packed RAW capture to fixed SD slots

This integration captures the sensor's unchanged ten-bit samples as packed MIPI
RAW10 bytes, writes them directly to the native SDMMC2 interface, and retains
the existing UART recovery mechanism. It uses the container in
[raw-slots](../raw-slots/README.md); there is no FAT filesystem, image conversion,
compression or full-frame CPU checksum in the normal save path.

The selected prototype is **RAW v15, polling IDMA with LINE publication and
asynchronous sensor STOP, followed by Standby**. Its programmed 64 KiB sector is
`efb3c440e008e448a1682285034fe30b77bdbb5834024da9de787f3f51f42629`.
The preceding v12 three-run baseline reached hardware-confirmed Standby and passed first-attempt
warm PE6 UART recovery. Separate deterministic and cold scene captures passed
complete SD-to-RAM byte comparisons. The forced-overlap LINE test also checked
each immediately published tail before SD could conceal premature publication.
See the [durable evidence](evidence/2026-10-24-raw-slots/README.md) for exact
builds, positive and failed experiments, and readback limits.

Final review found that fixed SRAM could retain the late-loader success marker
across a warm reset. V15 clears that marker before camera initialization; only
the current boot's verified loader can authorize late-code failure cleanup.
Its early load stays 15,804 bytes and its recovery instructions are unchanged.
A separate v15 cold smoke run passed Standby/SBF, first-attempt UART recovery,
and complete slot-8 readback with independent PNG decoding. It measured
0.778143 s / 0.424945 J using the same criteria. This single run is not a new
three-run baseline; its original sensor RAM was lost on entering Standby.

| Same measured boundary: current onset → stable Standby plateau | Previous PNG v66c | RAW v12 |
| --- | ---: | ---: |
| Median of three cold runs | 2.057802 s | 0.793888 s |
| Measured JS branch energy | 1.061503 J | 0.441400 J |

The observed reductions are 61.4% in duration and 58.4% in measured energy.
These are Nucleo branch measurements, with the existing USB/debug bypass and
instrument-calibration limitations. Scene, format and card-state differences
prevent attributing the whole improvement to one change. RAW cycle duration
ranged 0.789634–0.807867 s and energy 0.431091–0.441541 J. The card and board
remain physically supplied; Standby plateau current was 8.08–8.19 mA.

The strict timing decoder directly identifies events 1–9 in these runs. Its
last pulse fails the pre-WFI width tolerance and remains unidentified; Standby
is established independently by the warm-recovery SBF checks. Payload transfer
through final padded-sector readiness took 632.2–634.2 ms. Reset release to the
first observed exposure strobe took 22.60–22.82 ms.

An early IDMA trial reported SD protocol success but saved zero payload bytes.
Full readback caught the failure. STM32N6's SDMMC2 configuration-port security
attribute overrides the DMA master's security setting: the port and master must
both be secure before reading the secure camera SRAM. The runtime now verifies
both attributes, without weakening SRAM protection. A successful controller
status is therefore insufficient evidence of a correct image.

## Build and ownership

`build.py` is an offline builder. It verifies the frozen v66c receiver and prefix
sources before applying explicit transformations, then writes all transformed
sources, binaries, listings and hashes into a new output directory. Vendor
sources and the installed STM32 GNU toolchain remain the same pinned dependencies
used by `capture-sd` and `capture-packed`.

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/raw-example --transport idma --pattern diagonal
```

The default output is a RAM test image. It must be entered through a verified
early recovery and SRAM bridge; the build command never connects to hardware.
Only the bench owner operates instruments. The existing one-bit 3.3 V wiring
is retained, and the driver never negotiates four-bit or 1.8 V operation.

The image's privileged top-level entry owns its CPU/FPU context and never returns
to a C caller. Its completion branch records and clears only its inactive owned
FP context after all work has finished. This is not a reusable context cleanup
routine for a returning function. Success requires a fresh terminal proof,
idle/deinitialized card, disabled caches, exact immutable code and the expected
park address. A failure report alone does not authorize a power cycle.

## Capture and storage sequence

The camera retains the previously qualified ForceRx/lane sequencing and the
idle-checked receiver-data disable before sensor STOP. Sensor output datatype
is `0x30`, while its sample depth remains ten bits; CSI treats it as opaque
eight-bit transport data. The frame is 1,909,600 bytes at `0x34000000` with an
independent 32-byte guard immediately after the true image boundary.

After arming capture, the remaining storage code loads from NOR and SD
initialization runs while camera DMA and its interrupts continue. The selected
LINE producer publishes conservative completed prefixes; the complete-frame
producer remains available as a fallback. The current card finishes acquisition
before cold SD initialization completes, so the overlap improves readiness but
cannot make this card accept the first sector during that cold frame.

The slot layer scans valid headers for the first FREE slot, writes PARTIAL,
then transfers published packed bytes in large multiblock chunks. The final
352 image bytes are copied into a separate aligned sector with 160 zero padding
bytes. Padding never overwrites the frame guard. A FULL header is published only
after the payload and fresh card-ready checks complete. The SD driver then
deinitializes before terminal completion or the separately qualified Standby path.

The selected `--line-stream` producer can publish conservative prefixes before
FRAME. Its separate [LINE qualification procedure](LINE.md) explains the
64-line holdback, immediate ISR snapshots and forced-overlap diagnostic. The
linear frame buffer is retained in full; transmitted memory is never overwritten
or recycled while camera capture is active.

The optional `--async-stop` experiment starts the same STOP command after the
qualified data-disable sequence, but polls its acknowledgement and standby state
once per nominal millisecond while IDMA writes run. It does not change the sensor
command order. A failed or timed-out poll is deferred until the active SD call
returns; it never parks the CPU in the middle of a healthy IDMA transaction.
The slot is not marked FULL until sensor STOP completes. This option requires
IDMA because CPU-serviced FIFO transfers cannot tolerate an I2C polling delay.

The separate `--dma-sleep` experiment permits shallow WFI inside the IDMA data
wait only for transfers begun after full camera validation and sensor STOP.
Earlier transfers retain polling. The driver requires an active 1 ms SysTick,
enabled interrupts, shallow sleep and retained SRAM/SD/security clocks; it
changes none of those conditions. The owner explicitly enables the required
AXISRAM1–6, ACLK/ACLKNC, RIFSC/RISAF and SDMMC2 sleep clocks using set aliases
that preserve unrelated bits. It clears only the debugger's `DBG_SLEEP`
emulation bit after checking debug-register clock/reset access. Before/after
values are exposed through the manifest's `dma_sleep_clocks` record. The driver
independently checks the result before launch and before sleeping.

The first sleep diagnostic failed closed before its second payload transfer:
the measured SRAM, RIF and SD sleep-clock enables were absent, and no WFI had
occurred. Its PARTIAL slot and original failure evidence remain unchanged.
Enabling those clocks is an explicit owner setup step; relaxing the guard would
have hidden the missing bus/memory retention configuration.

The follow-up RAM v14b enabled those clocks, the NoC sleep clocks, and cleared
debug sleep emulation. It then failed to reach its terminal proof, with high
SRAM inaccessible during the recorded observation. Its actual sleep/wake state
and cause remain under investigation; do not promote this experiment to an
autonomous flash build or treat its current plateau as successful completion.
The polling IDMA path remains the fallback. All original failure evidence is
preserved in the linked durable evidence archive, with large raw waveforms and
private scene pixels kept only under `tmp/bringup/raw-slots-20261024/bench/`.

Cumulative wait statistics are exposed through
the manifest's `dma_wait` address, with the exact HAL tick callback identity.
The option is off by default. When enabled, DWT durations that span WFI measure
active cycles, not elapsed wall time; use the independent millisecond counter
and external instruments for elapsed-time comparisons.

SD protocol READY, DAT0 high and an idle host controller establish completion
under the present powered conditions. Sudden-power-loss protection in the card's
internal translation layer remains unqualified. An unknown card is never
automatically formatted.

## RAM requests and results

Each request is sixteen little-endian 32-bit words at `0x343FD000`. Words 0–2
are magic `0x52535131`, a nonzero request nonce and operation:

| Operation | Number | Arguments in words 3 onward |
| --- | ---: | --- |
| Capture and save | 1 | None |
| Explicit destructive format | 2 | Generation low, generation high, slot limit; zero limit uses all capacity |
| Read sectors only | 3 | First LBA, count from 1 to 512 |

READ writes only the dedicated RAM buffer at `0x34200000`, at most 256 KiB,
and issues no card writes. It can retrieve a retained image in chunks without
changing its packed frame in SRAM. A fresh request must still be bound to the
exact terminal state before restarting the entry point.

The 96-word proof at `0x343FD100` is defined by `runtime.h`. It records operation,
nonce, geometry, camera state, slot allocation, SD ownership, counts, timing,
final CPU context and terminal word. The build manifest identifies all code,
frame, proof and structured-card addresses. Per-chunk rows at `0x343FE000`
record call start/end, payload-sector offset, count, published producer bytes,
last READY response, return result and driver transfer cycles. Only the published
row count is current; unused rows deliberately retain prior contents.

Exposure metadata uses the read-back coarse exposure and line length with the
fixed sensor's nominal 160.8 MHz pixel clock, rounded only after multiplication.
This avoids the shipped driver's integer-microsecond line-time truncation.
Timestamp and orientation remain explicitly unavailable. Metadata validity flags
distinguish unknown values from the configured unity analog/digital gains.

## Cold-start constraint

The camera receiver must be ready within the existing 4.5 ms START-to-receiver
budget. Loading an entire combined receiver/storage binary before arming capture
can exceed that deadline on the one-bit boot NOR interface. A `--flash` build
therefore places storage code in a separate contiguous load range after the
early receiver. The prefix loads and checks only the early range. After capture
is armed, a bounded NOR reader loads and checks the late range while camera
interrupts remain enabled. The manifest identifies both immutable ranges and
the `RLD1` loader proof at `0x343F9E00`; `RLOK` is published only after the CRC
and transfer-idle checks pass.

The current source also clears `RLD1`'s `RLOK` word at receiver dispatch,
before any camera preparation or arm failure can consult it. This fixed-address
diagnostic area lies outside `.bss` and can retain a previous boot's success
marker across reset. Clearing it prevents early failure cleanup from trusting
late code that the current boot has not yet loaded and verified. This review
fix is **not present in the frozen, measured v12 image**. The selected v15
contains it and passed the separate cold save/Standby/recovery/readback smoke
test described above. The early-failure case itself is covered offline.

The linker audit requires the vectors and camera interrupt handlers to remain
in the early range, checks direct crossings into late code, and caps early
loading at the qualified v66c receiver's 15,804 bytes. These are offline layout
checks, not a new measured timing guarantee. A failed late load may leave
capture or a NOR read active; its failure park is not a maintenance permission.

The early load is padded to exactly 15,804 bytes. GCC otherwise changes prefix
register allocation and literal-pool placement for some receiver lengths or CRC
values, causing the conservative byte-identity guard to fail. To keep this
deterministic, the prefix compiles with v66c's original CRC constant, then the
builder relocates only the two reviewed CRC data words at offsets `0xC9C` and
`0x1354`. It verifies their exact original bytes, disassembled data-literal form,
and unique ELF mapping. The ELF, raw binary and listing are updated together;
all instructions stay unchanged. The manifest records both CRCs, exact offsets
and hashes, and preserves the unrelocated artifacts. The unchanged recovery
identity checks run again after relocation. This is not permission to patch
arbitrary code or admit a changed recovery branch.

Flash builds support the scene configuration only. The diagonal-pattern prefix
changes literal addresses before the existing conservative recovery boundary,
so it is rejected rather than weakening that check. Deterministic pixel tests
use the RAM build. Both flash completion variants retain the exact PE1/PE6 early
recovery guard; adding their reviewed prefix and sector identities to the
maintenance allowlist is a separate explicit bench preparation step.

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/raw-flash-awake `
  --flash --transport idma --async-stop --line-stream
```

Only after awake hardware qualification should `--standby` be added. It retains
the previously qualified peripheral teardown and accepts it only after complete
camera validation, sensor STOP, full slot commit, and idle/deinitialized SD.

## Cold-cycle measurements

`cold_cycle.py` records one root-owned cold cycle through JS110 and the existing
Saleae API. It is dry-run by default and never sends debugger/UART commands,
changes firmware, or retries a cycle. Execution requires a fresh root-authored
safe-start record that binds the exact flash sector and hashed evidence of idle
NOR/storage ownership. A current plateau by itself never grants permission to
remove power.

The helper retains the earlier qualified owner and power state machine. Its
byte-identical owner source is pinned under `support/single_cycle.py`; only the
`Owner` and fresh-statistics functions are imported. The copied owner's old v59
standalone entry point is not used for RAW measurements.

```powershell
python firmware/capture-raw/cold_cycle.py --out tmp/bringup/raw-cold-01 `
  --build tmp/bringup/raw-flash-standby --safe-start-proof tmp/safe-start.json
```

Future RAW builds use phase protocol v2: each event adds 800 nominal CPU cycles
(2 microseconds), with a 0.4 microsecond decoding tolerance. The first awake
cold run showed about 0.24 microseconds of GPIO/call overhead; that exceeded the
legacy protocol's 0.15 microsecond tolerance. Wider spacing separates the IDs
without changing the old recording's result. The legacy 0.5 microsecond protocol
and its original strict tolerance remain selectable only through its exact
bound build manifest. The shared PNG phase implementation is unchanged.

Camera and SD phases may overlap, so the decoder checks their required
precedence rather than numeric event order. Failed widths remain failed; it
does not assign labels from the expected source sequence. Recordings still need independent image integrity,
actual Standby/SBF and UART recovery qualification. Energy belongs to the
measured JS-fed board branch, not an isolated MCU or production battery path.

For the initial awake flash qualification, add `--expected-end awake`. This
requires a matching awake build and records ten powered seconds after startup.
It makes no terminal-state claim and cannot authorize a follow-up cycle: inspect
the exact RAW terminal/idle proof first. Awake captures have nine markers; only
Standby builds emit marker ten before WFI.

`summarize_cycles.py` is an offline report generator. It replays the exact frozen
v66c native-sample energy analyzer and threshold criteria, so the primary
current-onset → stable-plateau boundary is comparable. The extra one second used
to confirm the plateau is reported separately. Run it after recorders stop:

```powershell
python firmware/capture-raw/summarize_cycles.py --spec tmp/raw-summary-spec.json `
  --out tmp/raw-summary --recorders-stopped
```

The specification has `schema: 1`, a `build` directory, and a `cycles` array.
Each cycle contains `name`, `recording`, and an optional `qualification` JSON
path. Paths are relative to the specification. Without qualification the tool
explicitly reports a current signature, not a completed capture/save cycle.
A qualification binds the cycle name, exact sector, recording-result hash and
hashed SBF reader result. It requires root attestations that SBF was cleared
before this trial and no power-off intervened between the cycle and its warm
recovery/SBF read. The fresh exact-prefix park and unchanged CPUCR/reset state
are checked from that evidence. A separately hashed image report and explicit
full-slot readback attestation can qualify image integrity; SBF alone cannot.

The report emits directly width-decoded phase intervals even when another pulse
fails, but never fills a missing endpoint. In v12's first Standby trial, events
1–9 passed; the last pulse measured 20.49 microseconds and failed the original
20 ±0.4 microsecond rule. Its pre-WFI time remains unidentified. Native JS
energy can still be qualified by independent SBF evidence. Saleae and JS clocks
are independent, so this tool does not assign energy to individual phases.

`energy_compacts.py export` packages small native-sample energy artifacts with
the unchanged v66c exporter. Its sums include every sample and split bins at
the exact integration boundaries; partial boundary bins are never approximated.
The resulting folder retains compressed sums/extrema, raw manifests and chunk
identities, without copying the multi-gigabyte sample arrays. Run
`energy_compacts.py replay --folder PATH` to reproduce all four selected energy
intervals and the primary time/energy medians from that folder alone. This
replays numerical integration, not raw onset/plateau classification or analog
calibration. The existing 9.5 A validity criterion is unchanged.
