# Unsigned STM32N6 boot-header evidence

Checked 2026-10-16. This is a narrow local-file wrapper for the first-GPIO timing
experiment, not an implementation of authenticated boot. It performs no hardware,
OTP, key-provisioning, or device security-state operations. The normal Nucleo
development lifecycle accepts an unsigned OEM FSBL; no security changes are needed.

## Primary references

- [ST UM3234, revision 5, sections 3.9 and 4.1](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf):
  ROM download area and image header fields. The decimal offsets in table 35 put
  `binary_type` at 140 (`0x8c`) and reserved padding at 144 (`0x90`); the printed
  hexadecimal offsets for these two rows are inconsistent. ST's source and
  generated binary independently confirm the decimal offsets.
- [ST UM2543, revision 7, `--align`](https://www.st.com/resource/en/user_manual/um2543-stm32-signing-tool-software-description-stmicroelectronics.pdf):
  STM32N6 header 2.3 requires payload alignment to offset `0x400`, implemented by
  adding bytes at the start of the payload.
- [ST's Python header generator, pinned source](https://github.com/STMicroelectronics/STM32DDRFW-UTIL/blob/b47d5e504f737c4cdba8d8deb94d03f1b6fdce90/Scripts/imageheader/Python3/Stm32ImageAddHeader.py):
  v2.3 layout, a 96-byte empty signature, 160-byte base header, 416-byte padding
  extension, little-endian integers, zero extension padding, and checksum equal
  to the byte sum of the payload modulo `2^32`.
- [ST Nucleo standalone template](https://github.com/STMicroelectronics/STM32CubeN6/blob/main/Projects/NUCLEO-N657X0-Q/Templates/Template/README.md):
  unsigned FSBL command, external NOR address `0x70000000`, and both BOOT jumpers
  at pins 1–2 for autonomous flash boot. CubeProgrammer 2.21 and newer need
  `-align` on the signing command.
- [ST-generated Nucleo image, pinned binary reference](https://github.com/STMicroelectronics/STM32N6-GettingStarted-ImageClassification/blob/420336424f05e1320ea46a5ec8ac6b1d23c8464e/Binary/NUCLEO-N657X0-Q/SPI-Display/NUCLEO-N657X0-Q_GettingStarted_ImageClassification-spi.hex):
  independently inspected as Intel HEX data only. **The reference firmware was
  not executed or programmed.** Its application may have unrelated behavior and
  is not our timing-test firmware.

## Independent reference check

The original Intel HEX text SHA-256 was
`48ac818acc3a3548b8eb686446c2a9a91d0906b2c8455e39881ea68ba5a34c75`.
Each Intel HEX record checksum was checked before extracting its boot image.
At `0x70000000`, the first FSBL had:

| Field | Value |
| --- | --- |
| Magic bytes | `53 54 4d 32` (`STM2`) |
| Signature | 96 zero bytes |
| Header version | `0x00020300` |
| Payload checksum | `0x006ad80a` |
| Payload length | `0x0000f2e0` |
| Entry point | `0x3418f2fd` |
| Load address | `0xffffffff` (default ROM loading location) |
| Image version | `0` |
| Extension flags | `0x80000000` (padding only) |
| Post-header length | `0x1a0` |
| Binary type | `0x10` (FSBL) |
| Extension at offset `0xa0` | bytes `53 54 ff ff`, length `0x1a0` |

The 576-byte header ends at `0x240`. Its payload begins with 448 zero bytes,
placing the stack and reset vectors at file offset `0x400` (RAM `0x34180400`).
The reset vector matches the header entry point. The sum of all payload bytes,
starting at `0x240` and continuing for `0xf2e0` bytes, matches the header checksum.
Thus payload length and checksum include the leading alignment bytes. The ST
reference also ends its image on a 32-byte boundary; our wrapper zero-pads the
tail to that boundary.

ST's generated reference uses nonzero padding-extension bytes, while ST's Python
source uses zeros. Our wrapper uses zeros, keeps the reserved base fields zero,
and does not add authentication or encryption extensions.

The wrapper accepted that 62,752-byte reference image. Regenerating it from the
payload after file offset `0x400` reproduced **every byte except the optional
padding-extension bytes at `0xa8..0x23f`**. There were 406 differences, all inside
that allowed padding region. This verifies the header fields and alignment
against independently produced ST output rather than only against our own parser.
Seven corrupted images (checksum, payload, version, entry, load address, extension
signature, and vector-alignment padding) and four malformed vector inputs were
all rejected.

The initial 256-byte `first_gpio.bin` payload has SHA-256
`14d4c8ff2fc72c9df04dafa4a1a910a5f9fec39f09cc9e2d3e10e91105e34c44`.
Its generated `build/first_gpio_boot.bin` is 1,280 bytes, with stack pointer
`0x34181000`, entry `0x34180441`, payload checksum `0x58c7`, and SHA-256
`1c1aeff1a482f5edd6509cbcdef52da976cc5cc07e4b92bcfedebd0d08820cca`.
The generated file was read back and validated; this is a packaging check, not
proof of autonomous hardware boot.

## Intended use and limits

`add_boot_header.py input.bin output.bin` wraps a raw vector-first binary linked
at `0x34180400`. It validates the stack pointer, Thumb reset address, entry-point
range, 512 KiB ROM image limit, checksum, alignment, and saved-file readback.
`add_boot_header.py --inspect output.bin` independently checks the restricted
unsigned image structure. Neither command communicates with hardware.

This wrapper is an independently implemented substitute for the unavailable
SigningTool binary, based on ST's format and cross-checked against ST output.
It is **not** an ST-supplied executable. Autonomous boot on the actual board is
still the final compatibility test. A header does not validate the application's
safety: source/disassembly must separately confirm no OTP/security writes.

The installed Nucleo loader is `MX25UM51245G_STM32N6570-NUCLEO.stldr`, whose
StorageInfo describes 64 MiB at `0x70000000`, in 1,024 erase sectors of 64 KiB.
Back up and verify flash before programming. Even a tiny image changes a complete
64 KiB erase sector. Do not use the DK loader, OTP loader, or a mass erase.
