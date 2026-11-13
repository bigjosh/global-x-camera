# D3 HOLD capture candidate — November 13

Offline source/build qualification only. No instrument, NOR, SD or live
recovery permission was changed by this work. The parent campaign owns the
combined USB package, installation, actual D3 voltage and UART smoke test.

The user moved HOLD from A3 to **Arduino D3 / CN13 pin 4 / PE9** after the A3
output failed the standalone physical toggle test. Official MB1940 C02
schematic sheet 10 identifies ARD_D3 as PE9; DS14791 Rev10 Table18 places PE9
on main VDD. CN15 pin31 is an alternate same-net measurement point. PE9 is
separate from PE1/PE6 recovery and PE4 SD signals, whose existing updates are
masked. No whole-port GPIOE reset was added.

Schema 4 binds GPIOE9. Exact schemas 1/2 remain PD7 and schema 3 remains PA2;
all six archived awake/Standby packages pass current strict inspection.
The current 76-byte stackless hook starts at `0x34181DF0`, ends at
`0x34181E3C`, and leaves four zero bytes before the USB selector. The larger
PE9 preload instruction consumes old alignment padding without moving the
literal pool or increasing the total hook length. It preloads HIGH before
selecting push-pull/no-pull low-speed output and resumes the original reset
handler. Twenty UART literals and original startup/recovery/loader/bridge
bytes remain unchanged except the reset vector and two bound receiver CRCs.

Success and error shutdown groups are 70 bytes with WFI at offset40. They
float only PE9 immediately before WFI, preserve its HIGH output latch, and
reassert on unexpected return. Recovery, active work, awake completion and
refused Standby retain HIGH. The fixed error engine ends at `0x34181DC8`;
branches/literal reads into boot-only padding are rejected. Auxiliary rail
ordering and external latch timing remain unqualified.

`hold-standby/` freezes the candidate, generated sources, linker outputs and
manifests. `support/` freezes the changed generator/auditor/test sources.
`capture-audit.json` records complete source, opcode and prefix audits.
All **324** capture tests passed without skips, including real linked
instructions and corruption cases. `compatibility-results.json` records the
six historical package checks and three unchanged October28 no-HOLD binaries.
`no-hold-control/` retains those comparison binaries.

| Artifact | SHA256 |
|---|---|
| Receiver | `50d9e8bdfd8cbf59860885b0d2b07328a17fb2aefce53c455bc5ef53fe25f524` |
| Capture prefix | `0b700733636492f866c3be0b64a27c05c4e39f9a4b43c7783b53a5ba608c9ade` |
| 64KiB capture sector | `8760fc72cf9dd572b050d2d37ace393ea6f64d1fbcd946eab667298bada664f4` |
| 76-byte early hook | `b8b06e4a891d56c1be4cb8f3d7862b6c3040848c9c0f17340fc57d5b935bd6c1` |

Rebuild from the repository root into a fresh output directory:

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/d3-hold-new `
  --flash --standby --error-blinks --magic-format --line-stream --async-stop `
  --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge `
  --sd-clock-negedge-init --sd-review-profile --sd-startup-opt `
  --ethernet-powerdown --sensor-single-frame --gpio-hold
```

Omit `--gpio-hold` to reproduce the unchanged October28 baseline. Set
`GPIO_HOLD_BUILD` to the absolute candidate directory when running capture
unit tests so the linked-artifact cases run. Run `verify_offline.py` here to
check archived bytes and the exact package without any hardware access.
