# Offline ROM trace decoder

[decode_trace.py](decode_trace.py) reads saved STM32N6 binary trace buffers without a device connection or network access. It scans aligned records beginning with `0xFFDDBB00`, retains numeric codes and arguments, and reports malformed/truncated candidates. Unknown event codes remain visible. The standard library is sufficient.

From the repository root, reproduce numeric decoding of the recorded DEV trace:

```powershell
python firmware/boot-timing/experiments/rom-trace/decode_trace.py firmware/boot-timing/evidence/optimization-20261017/opt-awake-baseline-01/rom-secure.bin firmware/boot-timing/evidence/optimization-20261017/opt-awake-baseline-01/rom-nonsecure.bin
```

Use `--output PATH` to save JSON. The output includes input hashes, per-buffer record counts, numeric-code counts, record offsets and raw timestamps. It sorts by the raw 32-bit timestamp, **without correcting wrap or resets**. This ordering does not establish synchronization between buffers. The timestamps are not measured power-on or NRST times; their clock rate, origin and continuity must be qualified before assigning durations. A decoder success does not establish trace completeness or a successful boot.

## Optional ST event names and provenance

The record format and optional name mapping were checked against ST's [ROM trace example](https://github.com/stm32-hotspot/STM32N6-Boot-ROM-Traces), linked by its [STM32N6 installation article](https://wiki.st.com/stm32mcu/wiki/Security:How_to_install_a_trusted_application_on_STM32N6_MCUs). [reference-provenance.json](reference-provenance.json) pins commit `4fb875d59aafa08edd8293912e7d2cbddf533ed0`, exact source URLs, hashes and the expected 230-name mapping.

The parser is `Template_BootRom_traces/FSBL/Src/rom_trace_parser.c`, SHA-256 **`94fe2deed5d6cc7b2f7f34622d4b7295f00b4a026f43d6297c19730aedbc0db0`**. The example `main.c` establishes the two 2,048-byte buffer locations, secure `0x341037F0` and nonsecure `0x241077F0`; its pinned hash is also recorded.

The upstream [license file](https://github.com/stm32-hotspot/STM32N6-Boot-ROM-Traces/blob/4fb875d59aafa08edd8293912e7d2cbddf533ed0/LICENSE.md) lists STM32 Projects under SLA0044, while the parser carries a proprietary/confidential notice. **No vendor parser or complete lookup table is bundled here.** Optional retrieval preserves its original bytes and notices in ignored local storage; upstream terms apply to that file.

```powershell
python firmware/boot-timing/experiments/rom-trace/fetch_reference.py
python firmware/boot-timing/experiments/rom-trace/decode_trace.py firmware/boot-timing/evidence/optimization-20261017/opt-awake-baseline-01/rom-secure.bin firmware/boot-timing/evidence/optimization-20261017/opt-awake-baseline-01/rom-nonsecure.bin --reference tmp/boot-rom-reference/rom_trace_parser.c
```

Retrieval uses HTTPS certificate verification and checks the pinned hash before saving. Decoding also verifies the reference hash and refuses a different source. Without `--reference`, codes are decoded numerically and all event-name fields are `UNKNOWN`.

## Observed DEV trace, October 17, 2026

The saved [evidence](../../evidence/optimization-20261017/opt-awake-baseline-01/) contains **24 records in the secure buffer, zero in the nonsecure buffer, and zero rejected candidates**. There are **21 distinct numeric codes**. The pinned mapping names eight records; sixteen records remain unknown. All levels are INFO. Raw timestamps span `2612` through `6803`.

| Numeric code(s) | Count per code |
| --- | ---: |
| `0x00000034`, `0x0000016a`, `0x000000ab` | 2 |
| `0x2a000001`, `0x00000155`, `0x00000158`, `0x00002500`, `0x00002909`, `0x0000002b`, `0x0000003b`, `0x00000025`, `0x00000010`, `0x000000a1`, `0x000000a2`, `0x000000a0`, `0x000000bd`, `0x00002b00`, `0x00002713`, `0x00000095`, `0x000000e3`, `0x2a000003` | 1 |

Code `0x34` identifies DEV boot action, twice. Code `0x155` carries ROM version `0x00000501`; `0x2500` identifies POR. These are **DEV-mode traces**, not the autonomous flash-boot path, and cannot explain the measured cold flash-boot interval by themselves.

Both input files are 2,048 bytes. Secure SHA-256: `f6552d0e108effac280e88b149b1eb29f1a0ec57f7f5467f8f8414fc921da420`. Nonsecure SHA-256: `e5a00aa9991ac8a5ee3109844d84a55583bd20572ad3ffcd42792f3c36b183ad`.
