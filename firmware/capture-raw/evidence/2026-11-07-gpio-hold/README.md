# PD7 HOLD firmware — offline qualification, November 7

**Implemented and built, not installed or hardware-qualified.** The user
disconnected the board while assembling the power latch and controls. No
instrument was opened, no target memory was read/written, and no reset,
power cycle, NOR programming or SD command was issued in this work.
The last qualified installed image remains October 28 single-frame firmware.

## Behavior

`--gpio-hold` selects an explicit candidate profile using **PD7, Arduino D9 /
CN14 pin 2**. It requires the normal single-frame, Ethernet-power-down,
four-bit 25 MHz FLASH profile with error signaling. DMA sleep and diagnostic
mixes are excluded. Omitting the option retains the existing binaries.

1. ROM enters a new 76-byte stackless hook at `0x34181E40`. It enables the
   GPIOD clock, preloads PD7 HIGH, selects low-speed push-pull/no-pull output,
   then branches to the original reset handler. Assertion precedes stack/VTOR
   setup, UART sampling and receiver loading, but necessarily follows ROM.
2. PD7 stays HIGH through UART recovery park, capture, save and error flashes.
   Existing PD0/PD12 marker writes preserve PD7. Awake inspection builds keep
   HOLD HIGH after successful completion.
3. After all existing shutdown checks, the success and error Standby paths
   explicitly make PD7 an input without pulls immediately before barriers and
   WFI. They leave its output latch HIGH. No drive-LOW interval is added.
4. If WFI returns, the next instruction group reasserts HIGH before error
   handling. A refused Standby path retains HOLD in its shallow fallback:
   removing input power there would not establish safe AUX shutdown.

The new reset vector is the sole change before the old startup code. Original
startup, UART guard, twenty recovery literals, sensor loader and error bridge
remain byte-identical, apart from the two checked receiver CRC words. The
early receiver load stays **15,804 bytes**. The copied error engine remains
position independent at its existing SRAM location and fits its 1,536-byte
reservation, with 120 bytes spare. The prefix grows from 6,720 to 6,796 bytes.

## Checks and identities

- Full capture regression suite: **318 tests, 317 passed and one optional
  artifact test skipped**. That optional test was then enabled against the
  final Standby candidate; all **14 shutdown-transform tests passed**, with
  no skips. Logs are included here.
- Independent host checks passed for both packaged candidates, including
  source hashes, reset vector/boot header, pinned boot and error code,
  receiver/sector identities, both early-image CRC literals, and the exact
  release/WFI/reassert machine instructions. The awake candidate also passed
  the existing complete awake-inspection admission check.
- Default rebuilt receiver, prefix and sector exactly reproduce the installed
  October 28 identities. This verifies the disabled option; it is not a new
  physical NOR readback.
- Compiler: GNU Arm Embedded GCC 12.3.1 from the project's frozen CubeIDE
  toolchain. The compiler required execution outside the restricted process
  environment because of Windows DLL relocation errors; it accessed no DUT.

| Artifact | Standby candidate | Awake inspection candidate |
|---|---|---|
| Receiver SHA-256 | `d7a8202318d95183d7b09b97b728dd50d2e986e5a0ef668cc24f2e4dc320d3d1` | `298a65b0ab2a00a6256826604bf0ebb0656922ee84c3ebe1237c35666ddf3f60` |
| Prefix SHA-256 | `8614089a69fb0ca49d4a4d608159129079458a71b0be21f178574869377672f5` | `ab908088afd6a1a33fcb4ade8358bba130294a4b4a431c7aa4fc9137e00af30d` |
| 64 KiB sector SHA-256 | `909bc2f5e272a0216940e80f61dc8511c0ff4555df9e4e08c5b59af6b2c83f8c` | `ae1ed6bac82b1ba39b31f81578726689065209a744e33523c9aa4ff19a4696cc` |

[results.json](results.json) records the recomputed package audits and rollback
identities. `hold-standby/` and `hold-awake/` contain complete generated source,
linked images, disassembly and manifests; `support/` preserves the changed
builder/auditors/tests. `SHA256SUMS` binds the archive files other than this
README and itself; `.gitattributes` preserves exact evidence bytes.

Rebuild from the repository, selecting a fresh output directory:

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/hold-new `
  --flash --standby --error-blinks --magic-format --line-stream --async-stop `
  --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge `
  --sd-clock-negedge-init --sd-review-profile --sd-startup-opt `
  --ethernet-powerdown --sensor-single-frame --gpio-hold
```

Omit `--standby` for the awake inspection candidate; omit `--gpio-hold` to
reproduce the old profile. This command only builds files.

## Hardware qualification still required

After the user finishes assembly, re-establish actual supply/wiring, bench
ownership and current firmware identity before operating the target. Start
with a stable supply or held-button/bypass arrangement to preserve access
while programming and testing. Existing recovery identity allowlists were
not expanded to label the new image hardware-qualified.

Measure PD7 assertion from power-on; verify capture and complete image save,
error flashes followed by shutdown, UART recovery, and release before actual
power removal. Scope main/AUX rails to confirm the external RC holds main
power valid until AUX discharge completes. The selected diode/RC delay is a
hardware requirement, not a timing guarantee provided by this firmware.

Hardware reset also returns PD7 to its reset state. Firmware cannot hold it
HIGH during NRST or the preceding ROM execution. The current UART/reset
recovery procedure must therefore be tested with the real latch and its
delay, keeping a held-button/bypass recovery route available during bring-up.
No exposure-time, energy, physical pin-level, or rail-sequencing result is
claimed from these offline checks. Control-pot ADC sampling is a separate
implementation task and was not added by the HOLD option.
