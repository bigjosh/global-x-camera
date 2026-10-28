# CLK-only slew comparison at 25 MHz — October 27, 2026 UTC

**Slowing CLK alone did not restore reliable communication.** All nine formal
attempts failed the first slot-header read, before any image-sector write.
Consequently the requested complete-image write/read verification could not
be reached at any setting, and no slew setting was promoted.

| CLK GPIO speed | Attempts | First slot-header read | Complete image writes/readbacks verified |
| --- | ---: | --- | ---: |
| 3, very high | 3 | 3 CRC failures on CMD17 | 0 |
| 2, high | 3 | 3 CRC failures on CMD17 | 0 |
| 1, medium | 3 | 3 CRC failures on CMD17 | 0 |

These are GPIO drive/slew selections, not measured edge rise/fall times.
The order was 3→2→1, repeated three times, with warm UART recovery/reset
between attempts and no target power cycle. [Machine-readable summary](inputs/experiment-summary.json),
[all trial records](results.json), and [independent failure audit](inputs/host-independent-failure-audit.json)
retain the failures and the limits of the measurements.

## What was held constant

- Four-bit SDMMC2 at25MHz, with falling-edge host launch during identification
  and transfer, unchanged local-pad feedback RX and inherited compensation.
- CMD and all four DAT pins at GPIO speed3; only PC2/CLK changed.
- The same reviewed startup/no-tail, awake RAM capture program, cycle logger,
  FIFO/IDMA choices, CRC checks, ownership checks and image format.
- The same64GB-class card:122,507,264 sectors;
  CID words `[83,1146433824,269787418,1979815748]`.
- No physical changes. The user reported all LP8 probes removed and the
  existing27Ω series resistor closer to the card after extending CLK wire.
  Actual wire lengths, resistor position and analog waveforms were not inspected.

All three formal V3 programs are29,944bytes and differ at **one data byte**,
offset29936/address`0x343074F0`, containing the selected speed. Every instruction
is identical. The runtime GPIO record confirms PC2's setting and unchanged
CMD/DAT settings: GPIOC masked OSPEEDR is`0xFF3/0xFE3/0xFD3` for3/2/1;
GPIOE DAT3 stays`0x300`. [Binary isolation](inputs/v3-binary-isolation.json)
and [independent build audit](inputs/clk-v3-independent-audit.json) record this.

| Build | SHA256 of `capture.bin` |
| --- | --- |
| `ram-clk3-v3` | `9201baa94c4314202370461f9e033ed05254170165551a145f65c6f7553f18a2` |
| `ram-clk2-v3` | `7ce51adadb449caf43e9c88b199737ce8482d728b95fe42a4f26cebe4e304ecf` |
| `ram-clk1-v3` | `f611bc9614247bcad7898430f417d330d64702b81894cb46015c9429386be8a7` |

One preliminary V1 speed3 attempt failed identically and is separately retained.
V1/V2 compiler specialization changed instructions between settings, so those
builds were rejected as matched controls. V2 was not run. Neither is included
in the nine formal attempts. The disabled/default firmware remained byte-identical
to the installed build; [default identity](inputs/v3-default-binary-identity.json).

## Failure details and verification boundary

Every formal attempt initialized the card and reached allocation stage3, then
failed the initial CMD17 at LBA0: RAW result804 (`0x324`), SD error14/stage5,
STA`0x2` (`DCRCFAIL`). The FIFO delivered128words/512bytes, but CRC validation
failed: zero sectors were counted as successfully read, zero headers accepted,
and **zero image sectors written**. The immutable RAM code still matched;
CFSR and HFSR were zero. Round2/3 snapshots directly retained width proof
CLKCR`0x34003`; round1 used the same code but did not snapshot that extra record.

Cleanup retained `media_idle=1`, `initialized=0`, `controller_owned=0` **and
`cleanup_error=10`**. These were failed operations, never successful-idle proofs.
Further resets used the user's explicit experimental-board reset authorization.
No failed payload was accepted, no CRC check bypassed, and no allocation header
skipped to force an image write. There was no card erase or NOR programming.

The prepared trial runner would have read all3730sectors back at the same clock
and slew, checked the entire object against camera RAM (including front metadata
and trailing marker), and independently decoded PNG samples. That path was
never reached. There are no new saved-image, energy, Standby or cold-boot results.

## Retained data points toward a symbol-count disagreement

The final CLK1 attempt's CRC-failed512-byte buffer was preserved and compared
with a previously verified LBA0 from the same card. Both start with legacy
`GXRS`; the old sector contains a synthetic sensor pattern, not a personal scene.
The first71bytes match, but306of512bytes differ overall.

An exact model reproduces **all512 failed bytes**: remove eight four-bit symbols
from the historical1024-symbol payload, then append the first eight symbols
of that payload's computed four-lane CRC16. The1016 remaining data symbols
match exactly, and the received final four bytes`55 4A 5C AB` equal the computed
CRC prefix. Per-lane CRC was cross-checked using an independent implementation.
See [source comparison](pattern-header-comparison/clk1-trial03-v3/comparison.json)
and [alignment model](pattern-header-comparison/clk1-trial03-v3/alignment-analysis.json).
The self-contained [offline replay](pattern-header-comparison/clk1-trial03-v3/replay_alignment.py)
reproduces the match from the two archived512-byte inputs without hardware access.

This supports investigating a clock-count disagreement rather than treating
the failure as a harmless CRC indication. It **does not prove reflections**,
which endpoint saw extra/missing edges, or where in the receive path symbols
were lost. Repeated symbols make exact deletion locations locally ambiguous.
This is one host-RAM buffer against historical data, not a wire capture or a
fresh proof that the stored sector is unchanged.

## Limits and next useful control

No setting passed, so these trials cannot rank reliable alternatives or rule
out reflections. Shared conditions include RAM-awake execution, diagnostic
instrumentation, a continuously powered card and the current wire geometry.
There was no successful normal/cold control on this geometry during this task.
Restoring a known-working physical control, such as the user-reported CMD/CLK
probe arrangement, would make the next isolated comparison more informative.
No such physical change or extra experiment was performed here.

## Software checks and final bench state

The opt-in `--sd-clk-gpio-speed {1,2,3}` path is restricted to the reviewed
RAM experiment.29SD-driver tests,188capture tests and12trial-runner tests passed.
The [driver transcript](inputs/driver-v3-full-tests.log) and independent runner
audit are archived. The188-test capture result was reported by the implementing
agent from session tool output (20.139s); no separate transcript was retained.
The archive retains exact programs, build inputs, status records, recovery
proofs and logs; full scene payloads are excluded. Two512-byte synthetic-pattern
excerpts are included to reproduce the failed-header analysis.

Final UART recovery passed with nine good pulses/zero bad and exact installed
early park`0x3418078C`. **Target power remains on at that awake park, not Standby.**
Joulescope stopped cleanly at04:19:46.762UTC and restoredrange128; its final
4.879524V/84.514037mA is awake park current. COM8 is closed, BREAK released,
and no bench helper remains active. [Final park](inputs/final-park/result.json)
and [final telemetry](inputs/experiment-summary.json) preserve the terminal state.

Installed NOR remains `error-relocate-20261026/flash-normal-v2`, sector
`232af9173262473021453f40ea944dfa4cafc2657443cd0b83ea9c8c8bb3b02c`, prefix
`99dbb0f9ecdd56a9313e4e62bbbfec22ec8e5e5901c852d956315844cd066eba`.
The prefix was checked live; no new full physical NOR readback is claimed.

For offline archive verification, run:

```text
python firmware/capture-raw/evidence/2026-10-27-clk-slew/archive_results.py verify --out firmware/capture-raw/evidence/2026-10-27-clk-slew
```

`SHA256SUMS.json` seals every archived file except itself. Verification performs
no instrument operation. The frozen trial runner defaults to plan-only mode;
its presence is not authorization to rerun it against an unknown live state.
