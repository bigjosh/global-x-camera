# Native USB PTP qualification — November 8, 2026

**Result: installed and working on the local Windows host.** The camera boots
from NOR into native PTP when CN8 VBUS is present. Windows browsed the photos,
retrieved thumbnails, downloaded PNGs, canceled active transfers, and explicitly
deleted individual photos. No replacement USB driver or SD filesystem was used.
The original capture payload and early UART recovery remain intact.

Before committing, a fresh read-only ST-LINK check again matched all34,462
running USB executable bytes to the final build. USB service remained healthy
with189 photos, SD idle, no active transaction and no SD/CPU fault. No reset,
halt, power switch or storage command was needed. See
[the confirmation](validation/commit-confirmation.json).

The target is left powered in USB service, with **189 recognized photos**, no
active transfer, idle SD, no reported SD/CPU fault, and USB high-speed 480 Mbps.
The final passive JS snapshot was **93.19 mA at 4.977 V**. That is this board's
USB-mode input measurement, not isolated MCU consumption or battery energy.
COM8 is closed/BREAK released, JS is closed with range128/settings restored,
and no RAM helper or host download remains running. No new physical wiring or
OTP change was made. The external JS supply remains necessary with CN9 shunts
removed; the CN8 data cable alone is not the full target supply in this setup.

## Installed identities

| Artifact | SHA256 |
|---|---|
| USB executable, 34,462 bytes | `74c91b77062e899944941006e075ab76039055f5175bee5f497b8d1a242e3679` |
| ROM-loaded prefix, 7,160 bytes | `4976a9e956095e3176ef4863b6c49225df271b231305e51069152baf731e4dd0` |
| NOR bytes 0–65,535 | `dd69bc33981a35bebefaca4c1939b6334304a6ad72dcfb57492e539f0d1a0dad` |
| NOR bytes 65,536–131,071 | `27cf627bb447cdd53ae82413e3bc4d504a84f242d182b9890dd958a0163480df` |

`package08/` and `ram08/` preserve the exact generated binaries, source copies,
maps and manifests. Both 64 KiB NOR regions were independently reread and
matched. The following 4 KiB matched its pre-change backup. An independent
USB rebuild matched every byte. The original capture region from NOR offset
0x2000 onward in the first sector is unchanged. The 440-byte post-memory hook
and selector are the additions; the original early UART guard is unchanged.

## Hardware results

| Check | Observed result |
|---|---|
| Native enumeration and browse | Global X RAW Camera; flat RAW photo collection; 190 photos before the final explicit delete |
| Existing-photo fidelity | All 1,527,680 exported samples matched an independently saved historical RAW10 slot as `sample << 6` |
| New captures | Two powered-reset capture-control cycles created readable new photos in zero-based slots175 and189 |
| Deleted-slot reuse | Slot175 was deleted in the earlier USB test, then reused by normal capture |
| Final deletion | Native WPD deletion of `oB0` / slot175 / `GX_0000176.png` returned overall and per-object success |
| Persistence | After normal reset and SD reinitialization, 189 objects remained; only `oB0` was removed |
| Preserved data | Slot174's PNG remained byte-for-byte identical before/after deletion, capture, cancellation and the synthetic read-error trial |
| Surviving new photo | `oBE` / slot189 / `GX_0000190.png` downloaded identically before and after final reboot |
| Thumbnails | Native WPD retrieved the 128×156 BMP resource, 59,958 bytes |
| Cancellation before data | At100ms, pending GetStream returned cancellation; next complete download succeeded |
| Cancellation during data | At1500ms, pending Read canceled after524,288 delivered bytes; next download succeeded |
| Firmware cancel evidence | Two class Cancel requests accepted; zero endpoint-cleanup failures; no remaining active transaction |
| UART recovery | Final prefix verified exactly at the early park, nine accepted UART pulses/zero bad, no jumper change |

Final-build PNGs are 1120×1364, gray16 with sBIT10, 3,064,188 bytes. Each
download took about6.9 seconds including host setup, a fresh full SD read and
encoding. PNG uses stored DEFLATE; compression optimization is deferred.
Every new PNG chunk CRC and zlib stream passed independent parsing; Pillow
agreed on every sample and all low six bits were zero. EXIF reported a present
completion marker, no read errors and no zero-filled sectors. Both new previews
show recognizable desk/monitor/keyboard/window content; highlights are clipped.
Original new capture RAM was lost on shutdown, so new-frame source equality is
not claimed. The earlier historical RAW comparison supplies the exact-scaling
check, separately from these new capture/readback tests.

Useful photo hashes:

| File / purpose | SHA256 |
|---|---|
| New slot175, subsequently explicitly deleted | `e6a157c718f241c0d378e1c31b24613273949aad332f3a51d13c19b981002ee1` |
| New slot189, retained | `21f47f3c25d6e7e0e2bc3ea9de5b0dc71a337b02bb41dd110fea9f968fa06f1e` |
| Preserved slot174 | `a0fb448e7bd4f003015ffa98855403633fff1c8a7b89fb7916ea836baac84bb6` |

## Recovery and implementation findings

The first persistent USB candidate correctly stopped at its enabled-cache
guard: original stage1 enables instruction cache after early recovery, unlike
the RAM launcher. UART recovered it. The final hook disables/invalidates that
cache before copying code and restores it only when returning to capture.
Data-cache-enabled entry remains rejected. Linked tests check preservation of
registers/flags, stack alignment, barriers, exact capture bytes and bounded NOR
copies. The USB branch's selector-to-entry interval was36.913ms, including
loading the USB program; this is **not capture latency**.

For the commit, an additional independent build used the already committed
SD driver/header and RAW-slot definitions from `00ebc83b`. Its executable
matched the installed USB image exactly. The separate, default-disabled
DMA-sleep edits are therefore not required by this USB release. The shutdown
test's instruction oracle is local to the USB tests, avoiding a dependency on
the separately prepared capture-HOLD tooling. See
[the clean-dependency proof](validation/commit-scope/head-sd-proof.json).

A real cancellation test exposed endpoint PID desynchronization caused by
closing/reopening bulk endpoints. Cleanup now stops/flushes IN while preserving
endpoint toggles and a queued OUT command. Host cancellation completes via
GetDeviceStatus without a spurious bulk response. A later offline review found
response-phase cancel/reset and failed-abort buffer-ownership races. A persistent
cleanup gate now keeps Busy asserted until ownership is released; the response
buffer is static. Final hardware cancellation and subsequent full-file hashes
passed. The 21 native protocol cases include those otherwise hard-to-provoke
cleanup failures; they are fault injection, not claims of actual hardware abort
failure during the passing final runs.

A temporary RAM06 build simulated failure at one sector while serving slot174.
It did not corrupt the SD. The exported PNG remained valid, zero-filled that
sector, recorded two failed attempts/one zero-filled sector in EXIF, and later
advertised `_RECOVERED`. All1,527,680 pixels matched an independent reconstruction
with that exact512-byte sector zeroed;412 pixels changed. Restoring normal
firmware returned the original photo hash. This qualifies synthetic best-effort
export, not real failing-card recovery, ECC, retention or persistent retirement.

The final package passed24 boot/layout tests and an independent33-test protocol,
transport and shutdown audit. Separate storage17, NOR7, native-host10 and
thumbnail4 test suites passed during the implementation. Shutdown tests cover
34 guarded cases/417 checks; no physical cable-removal result is implied.

## Limits and deferred work

- Normal powered resets were tested. CN8 stayed attached throughout final
  qualification; no fully discharged combined-image cold start was established.
  The physical cable-absent ADC decision and cable-removal Standby tail remain
  unqualified. USB boot selection was tested present; a temporary forced-capture
  selector tested returning to capture with the cable attached.
- The capture-control recording had both JS GPIO inputs constantly LOW. Its
  final current was3.521mA, a sleep-like signature, but it provides no exposure
  count, phase timing or fresh Standby flag proof. The first passive recording
  ended before reset and was excluded. The50ms exposure target was not
  requalified for the combined selector.
- Attaching USB after existing capture Standby does not wake it. Start a new
  cycle with CN8 attached. A powered charger also selects USB mode.
- Physical SPDT/HOLD qualification and the offline normal-capture HOLD/DMA-sleep
  candidates remain separate. USB asserts PD7 while running; this does not
  install the prepared early-HOLD modification in the unchanged capture prefix.
- Windows WPD high-speed interoperability passed. Explorer's individual UI
  presentation, Photos import, macOS, Linux and full-speed USB are not separately
  qualified. The development VID/PID is not a production allocation.
- Initial catalogue scan reads every slot header and fails initialization on
  an unreadable header. Unknown/torn markers remain occupied and hidden; PTP
  does not repair or delete them. The catalogue supports up to65,536 recognized
  objects; this card contains32,843 possible slots.
- Existing RAW objects have no pixel checksum or commissioned timestamp/
  orientation schema. PNG integrity checks protect the generated representation,
  not unknown prior RAW corruption. Warning names are session-local; EXIF is
  authoritative for a download whose old filename was already cached.
- Explicit delete writes only the requested slot, tail first/header last.
  Atomic power-loss behavior remains unqualified; interruption can damage that
  requested photo. No automatic deletion, remote capture, mass-storage drive,
  persistent SD retirement table, or GetPartialObject is advertised.

## Evidence and replay

[archive-index.json](archive-index.json) maps each exact copy to its original
campaign path. [SHA256SUMS](SHA256SUMS) binds the frozen files; local attributes
disable Git normalization. Hardware operation logs are under `hardware/`,
native WPD logs under `host/`, build/audit reports under `validation/`, and
earlier pixel/recovery evidence under `earlier/`. Source and helper snapshots
make the implementation and review decisions inspectable without this chat.

The full local campaign is `tmp/bringup/usb-ptp-20261108/`. Scene photos,
thumbnails, partial transfer bytes and raw JS sample streams remain local
there; they are deliberately excluded from this public-repository archive.
The recorded hashes and compact validation reports identify them. Some frozen
manifests retain original absolute build paths; use archive-index mappings when
working from another checkout. Follow the live AGENTS checkpoint before any
future hardware operation; saved park proofs are historical evidence.
