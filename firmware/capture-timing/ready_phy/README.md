# Receiver-readiness margin experiments

Bench status, October 17: guarded v41 mode 6 (ForceRx held on data lane 1 only,
100 µs stable-STOP gate) is the selected bench sequence. Two minimum-exposure
cold starts captured the first physical exposure with complete frames, no raw
protocol errors, and valid current readiness and shutdown proofs. Their
arm-marker-to-first-VSYNC margins
were 548.16 and 546.08 µs; START-return-to-first-STROBE was 5360.64 and 5361.92 µs.
The clock-active status was present before ForceRx release.

The default-exposure v41 image is installed and its complete 64 KiB sector was
read back and verified: SHA-256
`c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f`.
It captured a clean first frame, with a recognizable room/bench scene including
lights, equipment and text, in `phy-ready-v41-default-install-01`. Its exact
recovery prefix, SHA-256
`0886559c3e4b5ddd358eb25a4f0c4ad4b40f588839c089a0fe1320675e28abce`,
also passed the early-park check in `phy-ready-v41-final-recovery-01`: verified
code/park, safe CPU context, disabled caches and idle XSPI.

Final qualification is complete. The normal cold repeat
(`phy-ready-v41-final-normal-02`) captured the first physical exposure with a
complete frame, zero raw errors, and valid current readiness and shutdown
proofs. START-return-to-first-STROBE was 5303.36 µs; reset-release-to-first-STROBE
was 23.81920 ms, and the frame-complete marker was 45.68224 ms after reset.
The default image remains installed. Instrument API sessions were released,
and a three-second observation without stimulating the target verified powered
rails in `phy-ready-final-release-01/powered-state.json`.

The recorded margins are bench observations, not production worst-case bounds.
See the [qualification archive](../evidence/2026-10-17-receiver-ready).

The both-lane ForceRx 100 µs variant (v39, mode 5) failed to receive a frame even
though its raw protocol-error history was zero. That is a failed capture, not
successful error elimination. The separate both-lane STOP 0 µs discriminator (v42)
did capture the first physical exposure with zero raw errors and 651.68 µs of
arm-to-first-VSYNC margin. It released ForceRx while the clock still reported
STOP. This supports the clock-entry timing explanation, but the current
preferred path holds only lane 1 with the 100 µs observation guard. A larger
single diagnostic margin is not enough to select a production sequence.

The first offline series starts from the exact qualified v36 5-line image and
changes only the stable data-STOP dwell after START ACK and STREAMING. Sensor
START, exposure, all readiness I2C transactions, error handling, snapshots,
post-frame shutdown isolation and the recovery guard remain unchanged.

The controls are 100, 10 and 0 nominal microseconds. The 100 µs build must match
the entire original v36 sector byte-for-byte. At 0 µs both data STOP flags must
still be observed before VC arming; only the additional persistence interval is
removed. The compiler's unsigned-comparison-to-zero warning is expected for
this one-constant transformation. The enclosing STOP-state condition remains.

This tests receiver margin without delaying exposure or masking errors. It does
not by itself move data enable earlier, because data still enables only after
the original START-ACK and STREAMING polls. Hardware qualification must inspect
raw errors, first-STROBE association, complete frame integrity and the current
shutdown proof. A successful single trial is not a production worst-case bound.

`build.py` accepts only the exact reviewed v36 default/5-line sector hashes,
checks every frozen source, and writes a fresh output directory. It performs no
hardware operations. The streaming dwell series preserves the first `0x830`
prefix bytes. The later ACK and ForceRx series preserves the exact first
`0x658` bytes, independently reviewed to contain the complete recovery branch,
cache-disable routine, park and referenced literals. Their normal-path code can
change when compilation folds a different receiver size/CRC. Every new complete
prefix still needs its own exact hash allowlist entry. The recovery park must
remain `0x3418078c`, and all stage 1 source files remain byte-identical to v36.

The first outputs are under
`tmp/bringup/capture-phy-ready-v37-streaming-stop{100,10,0}-coarse5-20261017`.
All retain FAST schema 1 at `0x343f8000` (544 words) and shutdown proof schema 1
at `0x343f8900` (16 words), and remain readable by the existing fast-PHY decoder.
Read either high-SRAM region only after the established RCC_MEMENR guard.

Run `python firmware/capture-timing/ready_phy/test_ready_phy.py` for the isolated
offline control, threshold, guard and layout checks. Frozen build manifests say
`hardware_status: untested` because they record build-time status; subsequent
hardware qualification is recorded separately with the captures.

## ACK-only readiness

Mode 2 (`--readiness ack --stop-dwell-us 0`) keeps the clock receiver early,
enables data after the existing START-ACK poll, observes both STOP flags, and
arms VC capture before the existing STREAMING-state poll. The poll is moved,
not added or removed. Sensor START and exposure programming stay in the
unchanged prefix. Use this directory's `inspect.py`, which recognizes the
explicit readiness mode, instead of the original fast-PHY decoder.

The frozen short-exposure build is
`tmp/bringup/capture-phy-ready-v38a-ack-stop0-coarse5-20261017`;
the completed default build is
`tmp/bringup/capture-phy-ready-v38b-ack-stop0-default-20261017`.
The earlier `v38a-ack-stop0-default` directory is incomplete because Windows
could not create the linker process; it is not a flashable build.

## Independent early-data ForceRx pair

Modes 4/5 (`early_stop`/`force_stop`) use early data-lane enable with the same
100 µs stable-STOP observation gate in both variants. They establish PMCR = 3
(FRXMDL0/1) before PEN release in both variants, recording original PMCR and
write readback. Control 4 clears PMCR at the original HAL point immediately
after PEN. Treatment 5 retains the two ForceRx bits. Both wait for both data
STOP flags to remain observed for 100 µs, confirm STOP is still present, clear
only FRXMDL0/1, and then arm capture. The original ACK and STREAMING polls run
after arming. No error interrupt enables or flag-clearing behavior is changed.

The 100 µs interval is an experimental observation gate, not a claim that STOP
alone proves a specified D-PHY initialization interval. The experiment tests
whether ForceRx can safely recognize a useful earlier state. It is independent
of the ACK-only change: data lanes are already enabled when PEN is released.
FAST events 437/438 therefore record a later lane-configuration check, not the
physical data-enable time. Events 405/406 bracket PEN release.

Builds are under
`tmp/bringup/capture-phy-ready-v39-{early,force}-stop100-coarse5-20261017`.
The failure park is `0x343014de` for this pair; use each frozen manifest rather
than the older receiver's failure address.

A new 32-word proof at `0x343f8940` follows, without overlapping, the existing
16-word shutdown proof. It is cleared at receiver entry, after stage 1 has
already issued sensor START and before any PHY observation. Its timestamps
are software read observations; they are not exact electrical transitions.
Pre-PEN status is recorded but excluded from first-ready-state timestamps.

| Words | Meaning |
| --- | --- |
| 0–3 | RFR1 magic, schema 1, mode 4/5/6, progress stage 1–6 |
| 4–5 | Inherited sensor START-return cycle, proof initialization cycle |
| 6–8 | Before PEN and before explicit PMCR write: cycle, PMCR, raw SR1 |
| 9–11 | After PEN: cycle, PMCR, raw SR1 |
| 12–14 | Before STOP polling: cycle, PMCR, raw SR1 |
| 15–17 | After stable STOP: cycle, PMCR, raw SR1 |
| 18–20 | Before clearing ForceRx: cycle, PMCR, raw SR1 |
| 21–23 | After clearing ForceRx: cycle, PMCR, raw SR1 |
| 24–26 | First post-PEN observations of lane 0, lane 1, and both STOP flags |
| 27–28 | Start of successful continuous STOP interval, required dwell in cycles (40,000; 0 for v42) |
| 29–31 | Signed result; pre-PEN PMCR = 3 write readback; packed RCC guard bits |

The relevant RCC bits in word 31 are APB5ENR bits 6/2 in place, DIVENR bits 17/16
shifted to bits 9/8, and APB5RSTR bits 6/2 shifted to bits 22/18. Safe access gives
`0x344`. Every new CSI observation checks those clocks and resets first.

Read this fixed 128-byte region only after the existing high-SRAM RCC_MEMENR
guard. `decode_force(data, manifest, fast_result)` preserves all raw words and
requires a completed release, valid current STOP observations, and matching
current FAST event order/timestamps. Its `completed` flag qualifies this
sequencing proof only; inspect all raw errors, frame integrity and first-STROBE
association independently. The decoder's optional `--force-input` accepts a
file already read from this fixed region; it never accesses hardware.

## Follow-up discriminators

These use separate builders so the reviewed v39 source transformations remain
frozen. They retain the same 128-byte proof layout and the exact recovery slice.

| Variant | Builder | Narrow change |
| --- | --- | --- |
| v40 | `build_pen_delay.py` | Optional 200 µs wait before hook 405 observations/PMCR preparation; the zero-delay control matches v39 byte-for-byte |
| v41, mode 6 | `build_lane1.py` | Write PMCR = 2 immediately after PEN, retaining ForceRx only on data lane 1; still require both STOP flags for 100 µs |
| v42, mode 5 | `build_force_stop0.py` | Change the additional STOP dwell from 100 µs to 0; both STOP flags and current STOP at release remain required |
| v43, mode 6 | `build_lane1_pen_delay.py` | Add 200 µs before hook 405 in the working sequence that holds only lane 1; zero-delay control matches v41 byte-for-byte |

The v40 both-lane zero-delay control was built; its 200 µs variant was not built.
The v43 lane 1 discriminator was built at both 0 and 200 µs. It shifts digital
PHY release, not the earlier PCR data-enable write, and does not change sensor
START. The existing 4.5 ms preparation deadline remains active. The new wait is
bounded by 80,000 DWT cycles and a 1,000,000-iteration safety limit; the explicit
requested delay and placement are recorded in both frozen manifests.

The completed v43 minimum-exposure test captured the first physical exposure
with zero raw errors and 548.00 µs arm-to-first-VSYNC margin. Compared with the
v41 minimum-exposure repeat, its externally observed PEN-after-START marker
moved from 3721.28 to 3936.48 µs (+215.20 µs). The extra receiver code also adds NOR
load time, so the observed shift is larger than the requested 200 µs wait. The
first-both-STOP observation moved only from 4894.035 to 4896.0925 nominal DWT µs
after inherited START return. This supports readiness following the sensor's
line state rather than a fixed interval after receiver enable on this bench.
Those DWT values use nominal 400 MHz conversion, not calibrated external time.

The decoder expects PMCR = 2 for mode 6 and keeps mode 5's expected PMCR = 3. Proof
word 28 must match `stop_dwell_cycles` in the frozen manifest; only mode 5 currently
allows 0. A 0 µs observation gate does not claim any specified D-PHY initialization
time has elapsed. Subsequent bench results, including failed captures with no
reported protocol errors, must be evaluated separately from proof completion.
