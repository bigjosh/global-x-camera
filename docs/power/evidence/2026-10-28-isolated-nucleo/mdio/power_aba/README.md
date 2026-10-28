# PHY power-down A/B/A probe

Offline-built helper; root alone operates the board. No result is asserted here
before root's retained operation evidence. Camera/SD are physically disconnected.

Exact binary:3312bytes,
SHA256`d55a735bacfebfb9bd6efd1a35b7af2b0794c239794b42e79a84af95494ec828`.
Load`0x343C4000`, entry`0x343C4CC5`, awake self-branch park`0x343C4546`,
proof`0x343C6000`/2048bytes, stack`0x343AF000..0x343B0000`.
This does not overlap the main isolated-probe code or proof.

The three windows use identical 400MHz busy loops and unchanged clocks:

| Phase | Setup | Settle | Measured hold | PD12 marker IDs |
|---|---|---|---|---|
| A | IDs0007/C131 and BMCR3000 read twice |100ms|300ms|11begin,12end|
| B | Write BMCR3800 once, then verify twice |100ms|300ms|13begin,14end|
| A restored | Write BMCR3000 once; bounded read-only polling for two exact reads and correct IDs |100ms|300ms|15begin,16end|

Pulse widths are2µs per event ID. Host commands must stay outside these windows.
No LED, MCU clock, MAC, camera, SD, NOR, reset or supply setting is changed.
MDC/MDIO are configured once and stay quiescent during every window. PD12 and
owned PF4/PG11 configurations are restored exactly, along with added GPIO clocks.

A power-down write attempt always triggers a restoration attempt, even after a
read/verify/hold failure. Restore sends one BMCR3000 write, then at most100 polls;
there is no retry write. Any restoration failure is retained separately from
the original error and excludes success. The probe ends awake; no automatic
reset, power cycle, storage action or previous-PC restoration occurs.

`run.py` is inert on import/direct invocation except offline hash checks.
Root uses `prepare(output, prior_verified_json)` from a successful exact
main `probe-v5`/`run_v5` result, with fresh SRAM/park/code/proof/fault validation.
An alternative exact hashed `cpu400a` v3 guard-refusal route remains available
as `prepare_from_refused_v3`; its failed workload is never relabeled successful.
Call `launch`, wait at least3seconds, then `observe`. Observation refuses to halt
a nonterminal state. The root may return to the preserved main park only after
successful restoration/code/fault validation and fresh main-proof checking.

Proof uses the diagnostic header/pin arrays documented in `../run.py` plus:

| Word(s) | Meaning |
|---|---|
|0,1,2|Magic0x33414241, version3, state8success/15failure|
|3,4|Original error, GPIO/clock cleanup error|
|64–67|Initial IDs and repeated BMCR|
|68–70|Requested3800 and repeated readback|
|71–73|Repeated restored BMCR, restore-poll count|
|74–78|Power-down writes, restore writes, verified-restored flag, failure stage, restore error|
|80–85|Astart/end, Bstart/end, restored-Astart/end DWT timestamps|
|86–90|Settlecycles40M, holdcycles120M, loop counts per phase|
|91–94|Restored IDs, marker error, PD12 configured flag|
|96–107|PD12 before/after mode/type/speed/pull/AF/ODR|

`test_protocol.py` compiles the actual clock/read/write/stability/restore C with
simulated GPIO edges and delays. It checks successful exact restoration,
ID/configuration refusals, rejected write values, and a100-poll failed restore
with exactly one restore write. Its model retains the corrected MDIO sample
edge; it is not an electrical test. `protocol-model-result.json` binds the test
to the source hash.
