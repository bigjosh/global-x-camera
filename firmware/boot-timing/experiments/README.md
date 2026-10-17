# Boot optimization experiments

These experiments measure the cost of the ROM-loaded image size and prepare a smaller first-GPIO payload. They keep the measured [original baseline](../first_gpio.S) unchanged. Build scripts operate on local files only; they do not connect to instruments or program the board.

## Bench state on October 17 2026

The revision 1 debug baseline produced both marker edges about 15.529 ms after NRST rose. Its raw payload is 368 bytes and its wrapped boot image is 1,408 bytes. It enables BSEC debug authorization after both markers, then executes WFI. Subsequent HOTPLUG status reads failed, including explicit AP1 and AP2 selections. This run establishes that the marker path executed; it does not establish that the debug stub completed.

The bench controller subsequently confirmed **revision 2 normal flash boot** in `opt-awake-baseline-02`, with both marker edges 15.2624 ms after NRST. Default HOTPLUG and subsequent AP0/AP2 attempts did not establish access. The preceding `opt-awake-baseline-01` was a development-mode boot and is not normal-flash timing evidence. Revision 2 configures RCC/DBGMCU debug clocks, then stays awake after the markers. Two later [PD0 diagnostic captures](pd0-dump/README.md), `opt-gpio-trace-01` and `-02`, successfully exported both ROM traces and the debug readbacks. Explicit HOTPLUG `ap=1` then worked. An explicit AP1 connection had not been tested after revision 2 normal boot, so the earlier connection failure does not establish a firmware defect. Do not infer the target's present power state from this file.

| Variant | Local artifact directory | Wrapped image bytes | Status |
| --- | --- | ---: | --- |
| Original measured baseline | `firmware/boot-timing/build` | 1,280 | Preserved; restoration target |
| Debug revision 1 with WFI | `tmp/bringup/debug-payload-size-20261017` | 1,408 | Previously tested; HOTPLUG failed |
| Debug revision 2 kept awake | `tmp/bringup/debug-awake-payload-size-20261017` | 1,472 | Normal boot confirmed; HOTPLUG failed |
| Revision 2 plus 8,192 bytes | Same revision 2 directory | 9,664 | Staged; untested |
| Revision 2 plus 32,768 bytes | Same revision 2 directory | 34,240 | Staged; untested |
| Smaller marker payload | `tmp/bringup/minimal-marker-20261017` | 1,248 | Staged; untested; has no debug hook |
| Smaller marker plus identical revision 2 hook | `tmp/bringup/tiny-debug-awake-20261017` | 1,408 | Staged; untested |

The revision 1 padded images are also retained, but are superseded by the awake revision for the next experiment. Historical non-debug padding images from `payload-size/generate.py` are not the intended HOTPLUG test set. Earlier files under the ignored `experiments/build` directory, including a larger proposal crossing sector boundaries, are superseded and must not be used for this sector-0-only experiment.

## Awake debug revision

[payload-size/build_debug.py](payload-size/build_debug.py) generates a derivative of the original assembly, replacing only the six-byte post-marker idle sequence with a branch and NOP. The new stub is appended after the original literal pool and fault handler. The builder compares the generated binary with the original: offsets `0x000..0x0D3` and `0x0DA..0x0FF` must remain identical. PD0 and PE0 stores remain at `0x34180492` and `0x341804C0`.

All additional operations occur after those stores:

1. Enable the BSEC peripheral clock, then write `BSEC_DBGCR = 0xB451B400` and `BSEC_AP_UNLOCK = 0xB4` as documented by ST.
2. Set `RCC_MISCENSR.DBGENS` and `RCC_MISCLPENSR.DBGLPENS` using their set registers.
3. Read-modify-write `DBGMCU_CR` to set `DBGCLKEN` and `DBG_SLEEP`, preserving its other bits.
4. Read diagnostic registers into RAM, clean that cache line, then remain in a NOP/branch loop.

The stub contains **no OTP, lifecycle, flash, or RCC_RDCR writes**. The debug authorization is volatile; ST's errata state that BSEC debug-control writes are effective once per cold reset and persist until the next cold power-on reset. An NRST pulse is therefore not a substitute for removing target power. The awake loop and debug clocks change post-marker power consumption, so this revision is a boot-latency test, not an idle-power baseline.

Seven 32-bit status words start at `0x34182000`:

| Offset | Value |
| --- | --- |
| `+0x00` | BSEC_DBGCR readback |
| `+0x04` | BSEC_AP_UNLOCK readback |
| `+0x08` | RCC_RDCR, read only |
| `+0x0C` | Completion marker `0x44424732` (`DBG2`) |
| `+0x10` | DBGMCU_CR readback |
| `+0x14` | RCC_MISCENR readback |
| `+0x18` | RCC_MISCLPENR readback |

Revision 1 has only the first four words and completion marker `0x44424731`. Status RAM falls inside inert padding in the larger images; it is overwritten only after ROM loading/checking and both GPIO edges. The unchanged stack is also within inert padding in larger variants.

The pinned CMSIS checkout is `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`. C static assertions verify every additional register address/offset and bit against that checkout. Generated source, ELF, disassembly, symbol map, and hashes remain with each build in its ignored output directory.

## Size comparison and smaller code

The matched awake images append exactly 0, 8,192, or 32,768 bytes of `0xA5` to the same 432-byte raw payload. Only the image length/checksum and inert tail differ between these three variants. Comparing them estimates the combined size-dependent cost of ROM loading and checking; it does not isolate flash transfer time from checksum time. Measure the awake baseline before and after the padded variants to reveal drift or state dependence.

The [existing header helper](../add_boot_header.py) creates the previously verified unsigned STM32 version 2.3 FSBL header, retains the vector address `0x34180400` and reset entry `0x34180441`, and includes alignment in the declared length and checksum. Each resulting boot image fits in the first 64 KiB NOR sector.

[minimal-marker/first_gpio_tiny.S](minimal-marker/first_gpio_tiny.S) and its build script stage a separate 196-byte raw payload. It retains stack-limit, vector and fault-handler setup, but assumes the pins retain their hardware-reset type, speed and pull settings. It explicitly sets output data and mode. Its 1,248-byte boot image has SHA-256 `6323a54bd830b501a28b412302b7d9ff762fbf08de555d2f96bc4394cc5f0ae5`. It has no debug-opening hook and must not be substituted into the current repeated-programming workflow without first addressing that limitation.

[minimal-marker/build_debug.py](minimal-marker/build_debug.py) now appends the **identical 176-byte revision 2 awake hook** to that tiny marker path. It rebuilds and hashes the original 196-byte variant, verifies all its bytes except the six-byte post-marker branch, and compares the appended hook byte-for-byte against the saved revision 2 payload. The result is 372 raw bytes and a 1,408-byte boot image, 64 bytes shorter than the matched revision 2 boot image. PD0 and PE0 stores are at `0x34180476` and `0x34180486`; status remains at `0x34182000` with `DBG2` magic. This comparison intentionally changes early GPIO instructions as well as image size; it cannot isolate instruction savings from the 64-byte loading/checking difference.

The staged full-sector buffer is `tmp/bringup/tiny-debug-awake-20261017/first_gpio_tiny_debug_sector_0.bin`, SHA-256 `0e9715f846fe0ccecb740928c1397e9669484aa9568de036f2b25689b2d6818d`. Its tail and restoration copy match the saved original sector. Build with `python firmware/boot-timing/experiments/minimal-marker/build_debug.py --snapshot hardware/local-backups/nor-before-optimization-20261017/sector-0-first.bin --output NEW_DIRECTORY`. Hardware validation remains pending.

## Exact restoration

Before the optimization experiments, the bench controller read the current first NOR sector twice in development mode. Offline comparison confirms that these files are identical, 65,536 bytes long, and begin with the original 1,280-byte baseline image:

- `hardware/local-backups/nor-before-optimization-20261017/sector-0-first.bin`
- `hardware/local-backups/nor-before-optimization-20261017/sector-0-second.bin`

Their SHA-256 is **`9fde1c8206eb450b06b74a56cb6e36b220ed2e0d1188fb6a55031171eae3409a`**. The same bytes are copied to:

`tmp/bringup/debug-awake-payload-size-20261017/restore_original_sector_0.bin`

Restore this **entire 65,536-byte sector at `0x70000000`**, then verify it against the saved snapshot. Restoring only the short boot image would not restore the complete sector. The earlier 64 MiB pre-baseline backup is a different recovery point, not the intended end state for these experiments.

Each revision 2 programming buffer is exactly 65,536 bytes. Its prefix is the selected boot image and every following byte is copied unchanged from the verified pre-optimization sector snapshot. Local readback verified those tails and the full restoration copy for both revisions. This preserves bytes following the selected image; bytes occupied by a larger experimental image are temporarily replaced and are recovered by the full-sector restore.

| Revision 2 programming buffer | SHA-256 |
| --- | --- |
| `first_gpio_debug_plus_0_sector_0.bin` | `4f22cc11e9819dd499489abb1f3c6a884098c70fcf0e16960b30705c098fa758` |
| `first_gpio_debug_plus_8192_sector_0.bin` | `408d6988f194687ed27c277ed2f5989b0fb1e591d04021fc8163e70bf8cb9a95` |
| `first_gpio_debug_plus_32768_sector_0.bin` | `42ebb41fbff31ca6c7e5616e2e770d63efe121897b4e6fde6166ec98961128b8` |

These buffers and local verification do not themselves demonstrate successful device programming. The bench controller must perform and save the device-side verification for every programmed image and restoration.

## Build and connection references

From the repository root, using the installed Python runtime:

```powershell
& 'C:/Users/joshd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' `
  firmware/boot-timing/experiments/payload-size/build_debug.py `
  --output tmp/bringup/debug-awake-new-build `
  --snapshot hardware/local-backups/nor-before-optimization-20261017/sector-0-first.bin
```

The output directory must be new. The builder refuses a changed original payload, unexpected vendor checkout, wrong snapshot size/prefix, changed original marker bytes, or a variant exceeding one NOR sector. It does not independently authenticate the snapshot's acquisition from hardware.

[STM32CubeProgrammer connection modes](https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html) distinguish HOTPLUG, which does not reset or halt on connection, from NORMAL, which resets then halts. A NORMAL connection cannot preserve an autonomous-boot timing interval. RM0486 section 78.10 distinguishes AP0 access to DBGMCU, AP1 access to the Cortex-M55 debug interface, and AP2 access to the system AXI bus. Explicit AP1/AP2 HOTPLUG selections did not recover revision 1 access; the default and subsequent AP0/AP2 HOTPLUG attempts also failed after revision 2 normal boot. Explicit AP1 access subsequently worked after the GPIO diagnostic payload; this does not identify the cause of the earlier failures.

[ST's STM32N6 security guidance](https://wiki.st.com/stm32mcu/wiki/Security:Security_features_on_STM32N6_MCUs) supplies the BSEC values. Local RM0486 Rev 4, DBGMCU_CR description, documents `DBG_SLEEP` and `DBGCLKEN`; the pinned HAL also supplies `__HAL_RCC_DBG_CLK_ENABLE` and `__HAL_RCC_DBG_CLK_SLEEP_ENABLE`. In the locally saved ES0620 revision, the BSEC write-once limitation is section 2.2.17 and the separate NRST reset problem is section 2.2.18; section numbers differ from older web references.
