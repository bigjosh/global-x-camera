# Native SD analyzer for Saleae Logic 2

`Global X Native SD` decodes the camera's **native SDMMC one-/four-bit SDR bus**.
This link is not SPI or QSPI. The analyzer is passive: it never operates the
card, target power, debugger or capture hardware.

The Windows x64 DLL is built for Logic 2 and the Logic Pro 8. It provides:

- CMD/ACMD names, arguments, command and response CRC7, R1/R1b card states and
  READY_FOR_DATA, plus R2/R3/R6/R7 response interpretation.
- ACMD6 bus-width tracking; CMD17/18 reads and CMD24/25 writes; ACMD23 pre-erase
  hints distinguished from CMD23's explicit block count.
- Per-block byte count, first 16 payload bytes, CRC16 for every active lane,
  and the card's DAT0 write-acceptance/CRC-error token.
- **DAT0 busy intervals measured from the raw falling edge to the raw rising
  edge**, including the final CMD12/R1b busy wait and releases while CLK is
  stopped. Busy and command decoding run independently.
- Waveform bubbles, a filterable Logic data table, and an all-events CSV that
  preserves overlapping intervals and multi-block transfer summaries.

## Install the built DLL

The prepared local binary is `dist/windows-x64/GlobalXNativeSD.dll`; build
artifacts are ignored by Git. Source, tests and fixtures are tracked.

1. In Logic 2, open **Settings → Custom Low Level Analyzers** and choose
   `D:\Github\global-x-camera\tools\saleae-sd-native\dist\windows-x64`.
   If you already have a custom analyzer directory, copy this DLL into that
   directory instead of replacing its setting. Do not copy the SDK's
   `Analyzer.dll`: Logic provides that runtime.
2. Save any recordings you want to keep and restart Logic 2. This is Saleae's
   documented one-time native-analyzer installation step; its Automation API
   can add an installed analyzer but cannot set this directory or load a DLL.
3. Add **Global X Native SD** twice: one instance with **Waveform view =
   Commands**, the other with **Waveform view = Data and busy**. Give both
   instances the same input channels and other settings.

Two views are deliberate. Logic's analyzer frames must be sequential, while a
CMD12 response can overlap DAT0 busy. One view shows CMD bubbles; the other
shows DAT0 bubbles, with neither interval shifted to hide that overlap.

### Input channels

The following is the map in our archived eight-channel SD recordings. The six
SD probes were subsequently removed; these are **recorded channel assignments,
not a claim about the present physical wiring**.

| Analyzer input | Recorded Saleae channel | Signal |
|---|---:|---|
| CLK | 2 | SD clock |
| CMD | 3 | Bidirectional command/response |
| DAT0 | 7 | Data lane 0, card status and busy |
| DAT1 | 4 | Data lane 1 |
| DAT2 | 5 | Data lane 2 |
| DAT3 | 1 | Data lane 3 |

Use **Rising**, offset **0**, initial block bytes **512**. Use **Auto (start
1-bit)** when the recording includes initialization/ACMD6, or force **4-bit**
for a clip that starts after negotiation. Automatic/four-bit mode requires
all four data channels. One-bit mode needs CLK, CMD and DAT0.

For new acquisitions leave **Capture mode = Live capture**. For a recording
that has fully finished processing or was loaded from disk, select
**Complete capture**. Live mode waits for additional input; complete mode
finalizes a truncated tail at the last observed CLK/DAT0 edge. That endpoint
is a lower bound, not an invented capture-end time. The SDK does not expose a
reliable final sample boundary to this decoder.

The optional **Data-only mode** can infer read or write packets when CMD was
not recorded. Select an explicit width and the Data and busy view. These
events are labeled inferred: commands, addresses and command-owned final
busy cannot be recovered without CMD.

## Read a CMD25 write

The CMD view shows CMD55/ACMD23, CMD25 and its response, then CMD12 and status
polls. The data view shows the repeated sequence:

```text
512-byte data + four lane CRC16s → card CRC-status → DAT0 LOW (busy) → next block
                                                               ... repeats ...
CMD12 stop → final DAT0 busy → DAT0 HIGH; CMD13 confirms TRAN + READY_FOR_DATA
```

Command traffic may overlap busy. A clock pause is included in the busy
duration; it is not mistaken for a release. No low interval is called busy
merely because DAT0 is carrying a zero data bit. The analyzer associates busy
with the write-status or R1b command phase. Native SD positive CRC status is
`010`, negative CRC status is `101`; other values are flagged as reserved.
DAT1–DAT3 are ignored during status/busy, as required by the native protocol.

Filter the data table by `busy`, `write_status`, `data_block`, `command` or
`response`. Busy rows contain `duration_us`. Response rows expose
`card_state` and `ready_for_data`. The analyzer's **All SD events** CSV export
also includes transfer totals and malformed/overlapping diagnostics omitted
from the sequential waveform table. Exporting it from either instance gives
all events; there is no need to concatenate the two identical full exports.

Busy release and a READY response describe the wire protocol. They do not
prove arbitrary power-loss safety, retention, or equality to the source image.

## Replay an existing capture through the Logic API

After the one-time installation, this script loads a saved recording, adds
both views and saves the annotated `.sal`, data-table CSV and all-events CSV.
It **never starts a recording**. Output must be a new/empty directory. Logic
2 must be running with its Automation API enabled.

```powershell
python tools/saleae-sd-native/replay_in_logic.py `
  tmp/bringup/sd25-crc-20261025/phase01/signals/signals.sal `
  tmp/sd-analyzer-replay --width auto
```

The script uses an installed `logic2-automation` package or this repository's
existing `tmp/bringup/saleae-deps`. Add `--close` to close only its newly opened
recording after saving; otherwise it stays open for inspection. Channel
arguments can override the recorded map above. A missing analyzer means the
DLL has not yet been loaded by Logic; it is not a reason to operate the DUT.

## Build and offline validation

Windows prerequisites: Visual Studio 2022 C++ Build Tools, CMake, Git and
Python 3. The SDK is fetched from Saleae at pinned revision
`e3c4b4ffda1c162c024a5913520aed17c6edb238`, or supply an existing checkout:

```powershell
tools/saleae-sd-native/build.ps1 -SdkRoot D:/Github/global-x-camera/tmp/saleae-analyzer-sdk
```

The DLL is under `build/Analyzers/Release/`. Copy it into your configured
custom analyzer directory and restart Logic after replacing a loaded DLL.
Use `-CoreOnly` to build/test the decoder without the Saleae SDK. CTest runs
the C++ protocol tests and, when Python is found, the recorded waveform
regressions. No instrument connection is used by either test.

The native replay tool also accepts a transition CSV with the exact header
`sample,clk,cmd,d0,d1,d2,d3`. Each row contains levels **after all transitions
at that sample**; sample numbers must strictly increase. Pass the acquisition
sample rate, not the SD clock rate:

```powershell
build/Release/sd_native_replay.exe recording.csv --width 4 --rate 250000000 --output events.jsonl
```

Only the first 16 bytes of each payload are retained in decoded events; CRCs
cover the whole block. This keeps the analyzer's event memory bounded per
block instead of retaining every image byte.

## Scope and evidence

The [validation record](VALIDATION.md) identifies the prepared DLL and clearly
separates completed offline/adapter checks from pending in-app integration.

The [recorded fixtures](tests/fixtures/README.md) preserve raw transitions from
our bench capture. They verify a 512-byte write with all four CRCs, a
**244.104 µs** per-block busy, and a **854.604 µs** final busy that starts before
the CMD12 response and overlaps a CMD13 PRG response. The next CMD13 reports
TRAN/READY. These are examples from a diagnostic recording, not new cycle
performance measurements or a reliability qualification.

Synthetic tests cover initialization, width changes, command/data CRC
failures, native write tokens, malformed/truncated input, explicit versus
hinted block counts and a busy release without further clock edges. This
implementation targets SD memory SDR, not SPI, SDIO, MMC, DDR/UHS-II or
voltage-switching analysis. A capture beginning mid-packet may need a later
valid command to resynchronize. Rolling/live-export behavior is not qualified;
use a completed recording for reproducible export. At 25 MHz, the archived
250 MS/s capture has 4 ns edge resolution; it cannot establish analog signal
integrity or sub-sample setup/hold margins.

References: [Saleae native analyzer SDK](https://github.com/saleae/AnalyzerSDK),
[installation](https://www.saleae.com/support/extensions-api/protocol-analyzer-sdk/setting-up-developer-directory),
[SD Association physical layer specification](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf).
