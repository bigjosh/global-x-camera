# Red error signals and shutdown qualification

The new four-bit 25 MHz Standby image has been programmed and independently
read back. [The qualification addendum](QUALIFICATION.md) records its normal
cold-image test and the exact production-prefix synthetic error test. The
initial snapshot below remains unchanged, including the checks that were
pending when it was frozen. [The closure snapshot](snapshots/closure/summary.json)
records the completed in-error recovery test, final NOR check, final cold boot
and clean instrument closure.
Do not infer the current bench state from this historical record.

The behavior is specified in [ERROR_SIGNALS.md](../../ERROR_SIGNALS.md): five
sets of the selected red code; 100 ms on, 400 ms off within each set; 2,000 ms
total dark between sets; 400 ms dark after the last blink; then failure-only
shutdown. Codes 1 and 6 are reserved without detectors. Code 8 is the new
internal/guard-failure category. Failed storage is never relabeled successful
or idle, and shutdown does not qualify SD power-loss preservation.

## Recorded evidence

| Check | Initial snapshot result and scope |
| --- | --- |
| Selected flash receiver | `471fddf2c71b7d8bba8e47debf8379a8fd72c7f3daae59dcdf10dc8eed1198af` |
| Programmed 64 KiB sector | `5ad1bc968606b17e513680bcdf6abf9c73ca3ccf24a236a37b8ecc89d4e9c661` |
| ROM-loaded prefix | `7f8017fd70bd9b77cfabcf212d072201ec8e134c3a44a0555a2108d7cc454c32` |
| Independent prefix review | 5,140 → 6,500 bytes; only six old failure-loop bytes and two CRC words changed in the original span; 20 recovery literals and 1,782 other disassembly rows preserved |
| Early receiver | Unchanged extent of 15,804 bytes; this does not claim unchanged cold-start latency |
| Exact recovery admission | Old/new exact pairs passed; seven altered, truncated or crossed pairs rejected by both gates; 14 existing readback tests passed |
| NOR installation | Complete independent 65,536-byte equality; following 4,096 bytes unchanged |
| RAM code-2 test | Synthetic error retained a nonzero result and did not claim media idle; later guarded flags showed SBF=1, PDDS=1, STOPF=0 |
| RAM code-7 first trace | Partial: 25 pulses in groups 7/7/7/4; recording ended too soon to qualify five sets |
| RAM code-7 repeat | Complete observed pattern: 35 pulses in five groups of seven; intervals consistent with the specified schedule within the recorded bin/filter uncertainty |
| Post-pattern current | Repeat reached about 8.067 mA; a current plateau alone is not Standby attribution |
| UART recovery | Exact early parks passed after RAM faults and after installation; Standby flag reader retains `trial_entry_proven:false` |

The two 40-second current files retain native sample identifiers and 5 ms
summary bins. LED state is inferred from the deliberately injected firmware
and characteristic current steps; no optical or LED GPIO probe was attached.
Startup nonfinite current samples remain in both records, so whole-session
coverage is explicitly false even though the fault windows are finite and
continuous. This is not energy, precision clock, analog-margin or general
fault-coverage qualification. Synthetic code injection does not demonstrate a
real full card, disconnected camera, missing card or failed write.

The initial snapshot excludes the parent's live Joulescope control/session
files and unfinished normal-capture tests. It retains the stopped full and
partial waveform files, exact generated sources and firmware, fresh prefix
objdump/objcopy outputs, operation/recovery/register records, and installation
logs. Camera images and SD/photo payloads remain private. Build manifests keep
their creation-time `hardware_status: untested`; later proof records establish
the narrower results above.

## Offline replay and later evidence

Run with Python and NumPy; no instrument APIs or subprocesses are used:

```text
python -B archive.py verify
python -B archive.py inspect --name initial
python -B archive.py inspect --name qualification
python -B archive.py inspect --name closure
```

`verify` rejects missing, changed or extra public files, rechecks the exact
firmware/profile/source identities, compares independent NOR readback bytes,
checks recovery and retained power flags, and recomputes both waveform
analyses from their frozen bins. It deliberately returns
`qualification_complete:false` for the earlier snapshots, and `true` for the
final closure snapshot. A hash match does not retroactively complete a test
that was pending in an earlier snapshot.

Each snapshot is immutable. Add a later named snapshot instead of overwriting
these records. Explicit additional directories retain JSON/log proof records
only, so image payloads are not accidentally published:

```text
python -B archive.py snapshot --source <private error-blinks folder> --review <private independent-review folder> --name <new-name> --extra-dir <completed-proof-directory>
```

The new snapshot will still report the initial check set as pending until its
additional qualification is explicitly reviewed and documented. After updating
top-level prose or adding a reviewed final report, `python -B archive.py seal`
refreshes only the outer manifest and first verifies every immutable snapshot.
It does not change snapshot conclusions. Keep final qualification in a dated
addendum and link its exact proofs.

Copied bench scripts are historical source records; running them is **not**
part of offline replay and would operate hardware. Use only `archive.py` for
the commands above. The manifest uses exact bytes with local `* -text` so Git
does not normalize the frozen records.
