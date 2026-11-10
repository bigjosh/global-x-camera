# Root-only SD DMA sleep qualification workflow

This file is an offline preparation artifact. Nothing here has been executed
against hardware. The new sleep option's exact flag/proof names remain owned by
the implementation; do not replace a failed proof with a relaxed admission.

## Existing exact normal image and current bench boundary

Installed build: `tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1`.
Receiver SHA256: `560a8734306436fe95bc1407031e70f1bc5b448949366e1bd007779c1736f646`.
Prefix SHA256: `6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874`.
Sector SHA256: `79a379470927135bc03841098fe070912cad8275e91c5d5985cc066c294cf64e`.

Last known live state is a RAM READ terminal followed by a cancelled next-read
preflight, not a fresh successful normal boot or fresh idle proof. Establish
ownership, actual power wiring and current state before any state-changing
operation; the old slot145 proof is not a live reset authorization. Root has
standing user authority to clobber the experimental DUT, but must preserve the
actual diagnostic boundary rather than relabeling it successful.

## Build scope

Common options for both polling control and sleep candidate:

```
--sensor-single-frame --error-blinks --ethernet-powerdown --magic-format
--line-stream --async-stop --transport idma --sd-bus-width 4
--sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge
--sd-clock-negedge-init --sd-review-profile --sd-startup-opt
```

Use `firmware/capture-raw/build.py --out BUILD` with these options. RAM awake
qualification omits `--flash`; cold awake adds `--flash`; normal adds
`--flash --standby`. Add `--dma-sleep` only for candidates. Preserve
disabled-profile reproduction of the known normal receiver/prefix/sector.
Check early/late split, vector placement, UART recovery and relocated error
engine before hardware. Sleep counters and safe timer wake must not overlap
the frame, slot-read destination, proof tables or error-engine region.

The separate idle-card wake prerequisite adds `--dma-sleep --dma-sleep-probe`,
omits `--error-blinks`, and stays RAM/awake. Its deliberate failed capture must
retain SRAM at the ordinary error terminal rather than shut down while blinking.
Use the dedicated runner, never the normal capture command:

```
python firmware/capture-raw/dma_sleep_probe.py --build PROBE --expected-sha PROBE_SHA --recovery-build NORMAL/staged --out OUT/probe --execute
```

This preserves exact recovery/bootstrap, executable/request readback and nonce
checks. It only uploads evidence after launch; it never sends a post-launch halt,
reset, recovery or retry. A passing `result.json` means the bounded 20 ms idle-WFI
diagnostic returned with no card commands or writes during the probe. It remains
an intentional capture failure, emits no `verified.json` reuse token, and grants
no idle, normal-DMA, image-integrity or actual sleep-residency permission.

## Recovery and cold recording commands

After root establishes the appropriate live-state boundary, the existing
root-owned UART helper is:

```
python tmp/bringup/sd125-negedge-20261026/uart_recover.py OUT/recovery
python firmware/capture-timing/recovery_gpio/check_park.py --build NORMAL/staged --out OUT/park
```

Cold logger (one cycle, finite recording, state restoration):

```
python tmp/bringup/ethernet-normal-20261028/cold_logger.py --out OUT/trace --cycle --park-proof OUT/park/result.json --expected-prefix-sha EXACT_PREFIX_SHA
```

The park must be freshly bound to the exact currently installed build. The
logger proves an approximately15s off-current interval and one power-on; it
does not independently prove every target rail was zero, a saved image, or
Standby. After each completed measured run, check UART recovery/park again.
Stop on failed phase decoding, unexpected current/state, or recovery failure.

Collect three baseline and three candidate cycles, preferably with a final
restored control or other matched bracketing if flash work remains acceptable.
Keep card, lit scene, exposure, supply and wiring fixed. Record slot numbers;
increasing slot scan and variable SD latency are confounders. Do not optimize
them in this same comparison.

## RAM original-image proof and SD equality

`bench.py` admits RAM awake only and obtains its own guarded bridge entry:

```
python firmware/capture-raw/bench.py capture --build RAM --expected-sha EXACT_RECEIVER_SHA --out OUT/capture --recovery-build NORMAL/staged --execute --download-frame
```

Require successful full-frame proof, controller/media idle, zero SD/capture/
cleanup errors and strict single-frame AST proof. Require nonzero sleep calls
and valid IRQ/timer/restoration counters in the new sleep proof. Then read the
saved slot without resetting the successful RAM terminal:

```
python tmp/bringup/sd-fourbit-20261024/magic_readback.py read-slots --build RAM --prior OUT/capture/verified.json --scr-proof OUT/capture/verified.json --slot SLOT --reference OUT/capture/frame.bin --reference-kind sensor-ram --out OUT/readback --execute
```

This reads all3730sectors in bounded512sector chunks, compares to the original
camera RAM, decodes PNG independently and records successful media-idle proofs.
Inspect the resulting recognizable image. Confirm no extra capture or card
write occurred in readback. The last returned prior proof belongs to the last
read chunk and should be used by any next terminal-gated operation.

## NOR promotion and cold image verification

Before installing, qualify sleep/error timeout wake and UART recovery in RAM.
Review the packaged FLASH binary with `single_frame_prefix.py` plus the existing
single-frame audit pattern at
`tmp/bringup/sensor-autostop-promote-20261028/audit_candidate_offline.py`.
That audit has historical source/layout assumptions: extend deliberately for
the new sleep feature, never bypass a mismatch.

The existing installer performs full independent physical64KiB before/after
readback and checks the following4KiB unchanged:

```
python tmp/bringup/error-blinks-20261026/install.py OLD_BUILD NEW_BUILD OUT/install
```

Run from the repository root and enter it at the exact OLD_BUILD UART park.
Check `complete.json`, new readback hash and following sector. It does not
itself finish a normal cold boot; establish exact new recovery after installation.

Cold Standby loses the source frame, so verify full saved slots independently:

```
python firmware/capture-raw/bench.py read --build READ_RAM --expected-sha READ_SHA --out OUT/read-entry --recovery-build NORMAL/staged --lba SLOT_TIMES_3730 --count 1 --execute
python tmp/bringup/sd-fourbit-20261024/magic_readback.py read-slots --build READ_RAM --prior OUT/read-entry/verified.json --scr-proof FRESH_MATCHING_CARD_SCR_PROOF --slot SLOT1 --slot SLOT2 --slot SLOT3 --out OUT/cold-readback --execute
```

Use a matching card-identity/SCR proof. This is full media readback plus independent
PNG decoding, not original-sensor-RAM equality. The guarded Standby-flag reader
retains its `trial_entry_proven:false` limitation unless a new pre-entry clear
is independently proved. Do not strengthen its claim merely from a low plateau.

## Power/timing analysis

`host-prep/analyze_sleep.py MANIFEST --out NEW_ANALYSIS_FOLDER` is offline-only.
Each manifest item has run, variant (`poll` or `sleep`), absolute trace path,
and optional evidence (exact build, sleep proof, slot). Both variants are
eleven-marker single-frame builds. The wrapper compares JS-native wall time,
transport average power, transport energy and post-first5ms cycle energy.

Do not reuse old `analyze_flash_awake.py` without adaptation: it assumes a
single linear DWT-to-JS time mapping. CPU CYCCNT may stop in WFI. Existing
in-firmware cycle counters may therefore measure active cycles instead of
elapsed wall time, including timeouts unless the sleep implementation supplies
an independent live wake/timebase. Preserve ST-LINK BREAK/reset and the early
polled UART recovery guard; there is no runtime UART-interrupt wake listener.

A useful success result needs lower transport power with no data corruption,
timeouts, latency regression, lost producer wake, or recovery failure. Total
energy alone cannot isolate WFI savings when the card's busy time varies.

## Finish

Leave only a qualified normal candidate installed; otherwise restore the exact
prior normal sector. Record exact installed identities, tests and limitations,
latest physical wiring, power state, last operation/PC proof, JS setting
restoration and COM8/BREAK release. No stale historical final-state helper may
claim a new final normal boot. Root decides whether to retain a final low-current
normal cycle or exact park; describe what was actually proved.
