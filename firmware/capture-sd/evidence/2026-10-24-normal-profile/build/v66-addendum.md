# Corrective v66c Standby build

The earlier v65 build saved IMG00068.PNG, then refused late completion with
`LPL1 state=3, reason=2`. Its loader still required SAVE report schema 1 while the
new SAVE module published schema 2. The refusal occurred before any late NOR
read or peripheral teardown. This disproves v65 shutdown readiness; uninitialized
low-power proof bytes are not evidence of Standby. The original build and review
remain preserved alongside the explicit [review correction](reviews/late-schema-review-correction.json).

v66c changes that gate to `SAVE_REPORT_SCHEMA` and requires the exact compiled
diagnostics profile and performed-check mask. Context, automatic-operation
nonce, terminal success, card idle, SAVE-loader identity, XSPI checks, deadlines,
transfer status and code CRC checks remain required. The actual-C test covers
132 combinations across both profiles and small/maximum late modules, including
rejection of schema/profile/check-mask mismatches before any XSPI read.

The [fresh peer review](reviews/v66c-normal-standby.json) passed. The exact sector
SHA-256 is
`8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61`.
The 28,960-byte SAVE module is byte-identical to qualified v64 awake:
`0a1a116fea60ba1b60c8974853e69f29edf8a38faf3b934d1811f816f77396d6`.
The 15,804-byte receiver and all early recovery bytes/literals passed the same
strict identity checks. Explicit overlay padding is zero words; the base retains
its two inert words. Intermediate v66/v66b builds failed those checks and were
never released as candidates.

Sources and small payloads are in [v66c-normal-standby](v66c-normal-standby/).
The separate [portable recipe](../archive-v66.json) adds this build without
rewriting the earlier v64/v65 archive. Run from the archive root:

```powershell
python verify_v66.py
python rebuild_v66.py --toolchain <matching-tools-root> --out <new-directory> --execute
```

These are offline build checks. Hardware Standby, SBF, image readback and energy
qualification must be recorded as separate results; the frozen manifests retain
their original `untested` label.
