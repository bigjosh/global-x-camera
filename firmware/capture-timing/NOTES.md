# Capture timing and recovery notes

## 2026-10-15  Require the newest supported sensor revision at factory commissioning

**Why:** the supported older cut-2 path uploads 17,092 patch bytes, requiring at least 153.828 ms for payload plus ACKs even at 1 MHz I2C. The user therefore required only the newest sensor revision, with actual identity/revision checked and recorded during factory commissioning. Cut 3 was the inspected fast-boot branch, not a permanent definition of newest silicon.
**Rejected:** accepting mismatched older units, skipping their required patches to manufacture a timing result, or treating a module part number as revision proof. This commissioning policy adds no prescribed per-shot revision scan or error code and does not itself qualify the 50 ms button-to-exposure target.
**Evidence:** commit `fc1f910c`; [D-44, patch calculation and commissioning scope](../../docs/decisions/50ms-cold-start-review.md#accepted-constraints--october-15).
**Provenance:** reconstructed on 2026-10-24 from the explicit main-chat instruction at 2026-10-15T20:19:36.940Z and its contemporaneous decision record.

## 2026-10-17  Preserve the sensor's natural cold startup instead of resetting it again

**Why:** the camera module's fitted pull-up lets the sensor begin booting while MCU ROM runs. The cold-only prefix preserves that progress, validates the initial host-pin configuration, and drives reset high without a deliberate low pulse. Accepted captures shortened the critical path while still requiring the expected sensor state.
**Rejected:** repeating the generic middleware reset/waits at ROM exit, or silently resetting and retrying when the no-reset assumptions fail. Successful cold images do not qualify warm reset or prove camera supply, CLKIN and XSHUTDOWN electrical sequencing.
**Evidence:** commits `4e765902`, `5176c540`; [circuit reasoning and cold trials](rom-and-reset-floor.md); [optimization results](optimization-results-2026-10-17.md).
**Provenance:** reconstructed from the October 17 documented sequence choice and its explicit electrical qualification limits on 2026-10-24.

## 2026-10-17  Load and check later code during sensor startup

**Why:** sensor configuration/START can run in the small prefix while receiver code is copied and CRC-checked during the sensor's roughly 5.3 ms internal transition. Word reads and inline CRC with prefix O2 reduced the same 11,532-byte copy to 2.887 nominal ms, essentially the 32 MHz single-line wire time. This gave useful readiness margin without advancing exposure by accelerating already-overlapped work.
**Rejected:** loading all later application work before sensor START, the CPU-limited per-byte/out-of-line CRC loop, and promoting 64 MHz NOR or hardware CRC merely because they might shorten the hidden copy. Their electrical/peripheral qualification remained separate and deferred.
**Evidence:** commits `4e765902`, `5176c540`; [loader bottleneck and v22 comparison](loader-optimization.md); [ROM transfer cost](../boot-timing/NOTES.md#2026-10-17--keep-the-rom-loaded-image-small-and-retain-the-required-header-alignment).
**Provenance:** reconstructed from the measured v19/v20/v22 sequence and contemporaneous deferral on 2026-10-24. Later RAW storage-load details belong with [capture-raw](../capture-raw/NOTES.md).

## 2026-10-17  Measure first exposure separately from reception and frame completion

**Why:** START acknowledgment and DCMIPP VSYNC do not mark integration onset. Zero-offset sensor STROBE, exposure-line sweeps and first-frame association established the useful timing path; a later settling frame cannot satisfy first-exposure timing. TIM5 independently bracketed the instrumented marker lag at microsecond scale.
**Rejected:** calling a command ACK, fourth-frame smoke image, nonconstant pixels alone or matching checksums alone proof of the first usable exposure. Nominal DWT frequency and a long-interval calibration disagreed with external timing; use locally checked timing and retain uncertainty. The apparent extra exposure line is empirical, not a universal correction.
**Evidence:** commit `5176c540`; [exposure method and sweep](exposure-measurement.md); [TIM5 cross-check and rejected calibration](timer-probe.md); [original smoke comparison](csi-startup-errors.md).
**Provenance:** reconstructed from the October 17 timing experiments and their stated interpretation limits on 2026-10-24.

## 2026-10-17  Retain normal dark calibration and stop chasing the tested START latency controls

**Why:** exposure/frame-period, PLL, settling, trigger-mode, dark-calibration and link-clock/rate experiments left the first START-to-STROBE delay near 5.3 ms. Disabling dark calibration raised the black pedestal without shortening startup; an immediate temperature read added about 1.837 ms without preactivating a faster path.
**Rejected:** trading image quality for those unobserved startup savings, or treating the fastest tested run as an absolute silicon floor. The stopping judgment was scoped to documented reversible software on this board/ROM/sensor configuration; new hardware or vendor information can reopen it.
**Evidence:** commit `5176c540`; [experiment ledger](experiments.md); [optimization results and scope](optimization-results-2026-10-17.md); [dark-calibration evidence](evidence/2026-10-17-v26-darkcal/README.md).
**Provenance:** reconstructed from the recorded negative experiments and explicit engineering stopping judgment on 2026-10-24.

## 2026-10-17  Preserve raw CSI error history instead of inferring health from callbacks

**Why:** the original ST-based smoke wrapper already recorded D-PHY control error `0x8000`. The pinned HAL's D-PHY disable macro wrote IER0 instead of IER1; after correcting that generated copy, a source is intentionally masked after its first callback. CRC/ECC monitoring also needs explicit enable/raw inspection. Raw pre-handler and completion/stop status distinguishes acknowledged or masked errors from a clean frame.
**Rejected:** blaming the error solely on fast startup, treating flag clearing as link repair, or accepting fewer callbacks as a fix. E2/E3 and configuration-clock corrections were useful controlled tests but did not remove the startup error. Preserve the vendor original and generated-source provenance.
**Evidence:** commits `40560dd9`, `5176c540`; [HAL analysis and smoke comparison](csi-startup-errors.md); [recorded experiments](experiments.md).
**Provenance:** reconstructed from retained smoke logs, pinned HAL analysis and targeted tests on 2026-10-24; the old wrapper did not preserve lane/time information, so only the error class can be equated retrospectively.

## 2026-10-17  Release lane 0 early and qualify lane 1 Stop before normal reception

**Why:** delaying the entire PHY until the sensor was streaming removed the warning but lost reception. The selected v41 sequence enables early, releases lane 0 ForceRx immediately after PEN, holds lane 1 until both data Stop flags persist for 40,000 nominal cycles, then releases/arms before ACK/STREAMING polling. Two minimum-exposure tests captured clean first frames with about 546–548 us arming margin. It supersedes the narrower-margin v35/v36 ACK/STREAMING-gated data-enable sequence.
**Rejected:** immediate release of both lanes, which retained the original error; holding both through the dwell, which produced no frame despite zero raw errors; or selecting the largest isolated margin as production proof. Disable idle data reception before sensor STOP to avoid the separate shutdown error.
**Evidence:** commits `d09de885`, `3457f1c9`, `140cdcdf`; [late-PHY failed reception](evidence/2026-10-17-v30d-phy-sequence/README.md); [selected sequence and discriminators](ready_phy/README.md); [shutdown sequencing](fast_phy/README.md).
**Provenance:** reconstructed from the October 17 matched trials and selected lane-specific workaround on 2026-10-24.

## 2026-10-17  Keep the ForceRx readiness bound empirical until STM32 semantics are known

**Why:** shifting PEN by about 208–215 us moved observed both-lane Stop by only about 1–4 us, supporting a sensor-related boundary near START + 4.93 ms on this hardware. Published Stop/ForceRx definitions do not establish an STM32 `T_INIT` completion guarantee. Clock-active corroborated the working lane-1 sequence but is not an implemented gate.
**Rejected:** assuming the sensor powers up in LP-11, treating the 100 us dwell as a normative MIPI guarantee, or polling clock-active before data enable when prior clock-only trials never observed it. The exact offending electrical transition and production PVT bound remain open.
**Evidence:** commit `140cdcdf`; [sensor/receiver source comparison and measured interpretation](ready_phy/readiness-sources.md); [receiver readiness evidence](evidence/2026-10-17-receiver-ready/README.md).
**Provenance:** reconstructed from primary-source limits and the PEN-shift discriminator on 2026-10-24; the physical explanation is explicitly an inference.

## 2026-10-17  Check clocks and reset before reading CSI registers

**Why:** a diagnostic read while CSI was held in reset stalled the v30b test and obstructed debugger recovery. Revised snapshots inspect RCC clocks/reset first and mark unsafe fields as skipped, preserving the distinction between an unread value and hardware data. A bounded software loop cannot bound a CPU access that never returns.
**Rejected:** blindly dumping clock-gated/reset peripheral banks or interpreting sentinel `0xFFFFFFFF` as a measured PHY register. A later successful restricted-prefix recovery is not permission to reset active capture/storage.
**Evidence:** commit `d09de885`; [failed v30 trial](evidence/2026-10-17-v30-phy-sequence/README.md); [guarded v30d access and recovery](evidence/2026-10-17-v30d-phy-sequence/README.md).
**Provenance:** reconstructed from the stalled access and revised diagnostic guards on 2026-10-24.

## 2026-10-17  Early recovery must prove a safe maintenance context

**Why:** repeated later-firmware failures required manual BOOT1 changes, so a small pull-settled GPIO guard was placed before risky setup. A selected park alone was insufficient: v34b retained ROM I-cache and failed the maintenance gate; v34c disabled/invalidated it and passed an actual verified NOR round trip. Early recovery precedes expanded SRAM, so it uses the low-SRAM helper and exact allowlisted live code/park, CPU, cache and idle-XSPI proof.
**Rejected:** an unverified generic debug stop, the high-SRAM post-capture helper in early recovery, assuming modified RAM equals cached instructions, or relaxing the gate to accept FP/lazy context. Post-capture normalization is only for an abandoned, verified idle application with no lazy FP save. RAM request bytes were cleared by ROM; debugger presence was not an explicit recovery request.
**Evidence:** commits `7b2d6019`, `1affc642`; [guard qualification and limits](recovery_gpio/README.md); [post-capture context review](maintenance-review.md); [cache preparation](../boot-timing/experiments/cache-prep/README.md).
**Provenance:** reconstructed from the October 17 recovery failures, v34c qualification and reviewed maintenance alternatives on 2026-10-24. The guard cannot recover corruption or failure before it executes.

## 2026-10-20  Use a measured PE6 pulse signature for ST-LINK-selected recovery

**Why:** the external PE1 control wire no longer reached, and the user requested an ST-LINK-controlled replacement. The existing VCP TX route reaches PE6; repeated `0xC0` at 1 Mbaud gives more HIGH sampling margin than zero bytes. Three complete qualified pulses within the existing nominal 100 us window request the exact early park. Measured BREAK asserts NRST on this ST-LINK, allowing UART traffic across reset.
**Rejected:** treating BREAK as PE6 LOW, assuming RTS/DTR expose usable GPIO, or selecting recovery from a static level/lone edge. USB gaps and uneven sampling can miss a request; use bounded retries only from a safe state, followed by exact park proof. Successes do not establish all-state reliability, and unchanged observation-window length does not imply unchanged boot cost.
**Evidence:** commits `3fd42313`, `6224f912`; [VCP design, failures and successful stimulus](recovery_vcp/README.md); [waveform evidence](evidence/2026-10-19-vcp-recovery/README.md); [qualified parks](evidence/2026-10-20-vcp-sd-smoke/README.md).
**Provenance:** reconstructed from the user's route preference, measured ST-LINK behavior and initial qualification on 2026-10-24; PE1 remains a supported historical branch, not an assumed connected wire.

## 2026-10-24  Verify the physical UART stimulus before blaming the recovery detector

**Why:** during the SanDisk baseline preparation, host writes at 1 Mbaud reported success but Saleae PE6 showed only two level transitions, not the repeated C0 pulse train. Warm and explicitly authorized cold recovery therefore did not provide the intended stimulus. Reopening/configuring a bytes-only 115200-baud test restored thousands of measured edges; returning to 1 Mbaud and retrying across reset reached the exact v18 early park (nine good pulses, zero bad). The three subsequent measured cycles each recovered on the first warm attempt.
**Rejected:** inferring a broken wire, missed boot window or firmware failure merely from host transmit success and unavailable AP1; immediately requiring a manual boot jumper when the physical request has not been verified. From a safe state (or an explicitly authorized interruption), inspect PE6, try bounded serial reconfiguration, and require the exact early park. Baud change correlated with recovery; its underlying cause and all-state reliability remain unproven. Bytes-only diagnostics do not authorize resetting active storage.
**Evidence:** [SanDisk preparation and recovery records](../capture-raw/evidence/2026-10-24-sandisk-extreme32/README.md#recovery-finding); archived `recovery/finding.json` and original config/events/park proofs. No firmware/NOR change was needed.
**Provenance:** recorded contemporaneously after the user's explicit unknown-state reset/erase approval and confirmation that the old breakout remained connected.
