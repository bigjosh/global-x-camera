# Phase LED firmware: offline evidence, October 18

This checkpoint preserves the exact v44 LED/sleep build derived from the
qualified default-exposure v41 image. It was subsequently **programmed with full
readback verification**, and the user reported the LEDs working. The separate
[bench record](bench/README.md) preserves those results and the incomplete
instrumented attempts. Capture integrity, actual CPU sleep, timing and GPIO
recovery qualification remain pending for v44. Original offline manifests retain
their build-time untested status.

V44 adds red at the start of application code, blue on the first exposure STROBE,
all off at the first complete frame, and all-off shallow CPU WFI sleep after the
existing successful completion checks. Green is reserved for future NAND writes.
Fatal capture failures remain awake and show red. The qualified PE1 recovery
source is unchanged. Application red does not cover the preceding ROM boot.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| First NOR sector | 65536 | `a325b36ed6d3f893ebe0d1153f476fd06fc51c648a1fe55aac15d353c959b4d8` |
| Prefix payload | 4652 | `875d665e050aa2c20e59843c382130d2029035a478230a39f15892ce543c90c6` |
| Receiver payload | 14344 | `478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac` |

Recovery park is `0x3418078c` (`fee7`); failure park `0x34301546`; completion
loop `0x343022d8` (`30bf fde7`, WFI then branch back). Exact manifests and binaries
are in `build/`. All manifests retain the original hardware-untested status.

The offline test log records eight passing negative/invariant tests. Generated
source hash checks also passed, including exact recovery source identity and LED
proof access only after expanded SRAM initialization. The LED proof deliberately
reports sleep **prepared**, never physical sleep observed; live CPU evidence is
still required. Proof snapshots likewise do not prove continuous pin voltages.

## Preserved inputs

- `source-provenance.json` maps every frozen C/assembly/linker/header source and
  generator/validation helper to exact SHA-256-addressed bytes. Unchanged bytes
  reference earlier evidence directories, verified when this archive was made.
- `headers.zip` and `headers-index.json` contain 53 repository-owned dependency files
  discovered by running GCC `-M` on every C translation unit. This includes the
  exact local configuration and CMSIS/HAL/board/sensor header closure.
- `toolchain.json` records the GNU Arm version, executable hashes and pinned ST
  repository commit. System headers and runtime libraries remain part of that
  external toolchain, not this archive.
- `license-index.json` points to the preserved vendor license texts.
- `offline-validation.json` and `offline-tests.txt` record validation separately
  from hardware qualification.

Original manifests retain their original absolute paths for provenance. No ELF,
object files, frame pixels or instrument recordings are included.

## Restore without the original tmp directory

Run the archived restore helper with a **new, nonexistent** destination. It
validates the archive first, restores source/header/binary bytes under their
original repository-relative paths and never operates hardware:

```powershell
& 'C:/Users/joshd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' `
  firmware/capture-timing/evidence/2026-10-18-phase-leds/restore.py `
  --destination D:/Github/global-x-camera/tmp/v44-restored
```

Add `--rebuild` to compile those frozen translation units and compare prefix,
receiver, boot header and reconstructed sector byte-for-byte with this archive.
The matching external GNU Arm toolchain is required; `--toolchain-bin` accepts a
different location but still verifies recorded executable hashes. Include paths
are relocated to the new restored tree; the original tmp tree is not consulted.
This recompiles the exact frozen output sources and does not rerun historical
v41/v44 source transformations.

An archive-only restore/rebuild passed: prefix, receiver, boot header and sector
were byte-identical. See `restore-rebuild-final.txt` and
`restore-rebuild-result.json`. The first restore attempt found that GCC `-MM`
omits one CMSIS header marked as a system header by pragma; its failure log is
retained. Collection was corrected to `-M`, with only toolchain-owned files
excluded, before the successful complete rebuild. Existing vendor warnings are
preserved in the rebuild log.

Run `firmware/capture-timing/verify_evidence.py` to verify the archive hash index.
The index includes references to reused source objects and licenses in earlier
evidence folders, so keep those folders with this archive.
