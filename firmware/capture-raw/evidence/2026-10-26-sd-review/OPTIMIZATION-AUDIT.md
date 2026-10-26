# Optimization shortlist after the physical link is stable

October 26, 2026. This shortlist records offline estimates and their conditions. The bounded DMA-eligibility wait and a separate startup profile are implemented as explicit RAM experiments with executable tests. Hardware outcomes belong in the [experiment record](README.md); this document does not qualify the 50 MHz link. Keep electrical comparisons separate from timing changes.

## Ranked candidates

| Order | Change to test separately | Expected benefit and boundary |
|---|---|---|
| 1 | Give an already validated frame up to10 ms to finish sensor STOP before choosing PIO versus IDMA. | Potentially about119 ms in the root-reported warm pattern case. Long-exposure/frame-incomplete captures retain immediate progressive PIO. |
| 2 | Reduce the initial clock train from10 ms to a documented1 ms interval after valid supply. | About9 ms fixed savings. At100 kHz this still supplies100 clocks; at400 kHz it supplies400. Require at least74 clocks and the power-up timing conditions. |
| 3 | Remove the generic1 ms wait after raising the identification clock to25 MHz. | About1 ms. Keep idle checks, readback/barriers and a short explicit clock allowance; do not remove the distinct eight-clock CMD6 switch requirement. |
| 4 | Raise identification from100 kHz to at most400 kHz. | Roughly7 ms less fixed command serialization in the retained trace, plus smaller polling quantization. The approximately200 ms card-internal initialization must not be divided by four in estimates. |
| 5 | Reduce successful-write readiness quantization. | Usually0–0.9 ms per terminal busy interval, rather than deleting the final readiness proof. |
| 6 | Reuse the already validated SCR from initialization. | The measured duplicate query was0.172 ms at25 MHz. Low complexity if its lifetime is explicitly one initialization. |
| 7 | Remove only proven back-to-back readiness redundancy. | Tens of microseconds at the final deinit, or a few tenths of a millisecond over a short slot scan. Small return compared with the items above. |
| Later | Begin SD clock training asynchronously after receiver arm, during late code loading. | About1–2 ms remaining overlap after the delay reductions. Earlier ACMD41 launch requires a more substantial early-code state machine and renewed boot/recovery qualification. |

These estimates are not additive guarantees. Faster initialization can expose the pending-STOP transport-selection issue more often. Card readiness, scan position, exposure and transport choice can dominate an individual run.

## 1. The newly observed PIO selection penalty

The root reported a complete frame at about21.9 ms after arm, first write at about51.8 ms, and sensor STOP completion another6.4 ms later. The roughly1.9 MB transfer took about205 ms, rather than the roughly76.4 ms minimum payload time of a four-bit50 MHz bus.

`magic_publish()` deliberately withholds the final sector until FRAME is validated, the sensor has stopped, and the overlapping guards pass. This is correct: the final `GXRE` word cannot be published early. However, `sd_write_blocks_stream_preerase()` chooses its transport once, before initial readiness/preannouncement. If only that final sector is unavailable, the entire otherwise complete image goes through PIO. It does not switch to IDMA when STOP finishes a few milliseconds later.

The smallest change belongs in the camera coordinator, before starting the storage transaction: if FRAME is validated, all but the final512-byte sector are published, and no camera error exists, poll normal STOP/publication for at most10 ms. Complete publication takes the existing IDMA path; expiration takes the existing PIO path without claiming an error or publishing the trailer early. If FRAME is not validated, do not wait: preserve early progressive writes for long exposure.

This adds no duplicate SD commands. Keep the existing final-sector, guard, CRC and shutdown checks. Record eligibility-wait start/end, timeout versus completion, selected transport and first actual command timing. Place the first-write marker after this wait so it does not falsely label waiting as active transfer. Test three cases: already complete; STOP completes inside the allowance; STOP exceeds it and PIO fallback succeeds. Also recheck the long-exposure path.

Moving the transport decision until after ready/ACMD23 would hide only tens of microseconds in the measured command setup, not the observed6.4 ms. Refactoring that boundary also risks duplicating preannouncement when delegating to the existing IDMA wrapper. A mid-CMD25 PIO-to-IDMA transition is a larger controller/FIFO ownership change and is not justified for this first improvement.

If the next matched measurements show IDMA around80 ms and STOP eligibility takes6.4 ms, the observed205 ms PIO case has about119 ms of potential net savings. The80 ms figure remains a projection until a comparable IDMA slot is measured. The benefit can be zero on a cold card whose initialization already finishes after STOP.

The optional `RAW_DMA_TAIL_WAIT=1` coordinator implements this policy before slot-write/first-write markers or SD write commands. Its deadline is 4,000,000 DWT cycles at the qualified 400 MHz, with unsigned wrap-safe subtraction. It introduces no HAL timeout. One bounded normal publication callback can straddle the deadline, and the recorded elapsed duration includes that callback. A fault returns to existing outer cleanup instead of becoming a PIO timeout. The final-sector publication and transport code remain unchanged.

The opt-in `raw_dma_tail_wait_proof` is 16 unsigned 32-bit words (64 bytes): magic `0x31575444` (`DTW1`), version1, outcome, start, end, elapsed, limit, available-before, available-after, poll count, result, FRAME-before, STOP-before, and three reserved zeros. Outcomes are 1 already fully published, 2 FRAME pending, 3 prefix too short, 4 publication completed during the wait, 5 allowance expired and PIO remains eligible, and 6 camera/publication fault. This is diagnostic telemetry, not an SD-idle or final-transport proof. Cycle events48/49 bracket actual waiting; skipped waits do not set them. Existing SD transport events identify which path was really selected.

`test_dma_tail_wait.py` executes the actual helper with modeled DWT/publication, covering both sides of the eligibility thresholds, completion, fallback, wraparound, initial and in-wait camera/guard errors, and an error appearing at the deadline. The existing actual generated capture/publication/overlapping-guard tests also pass. Default-off executable identity and hardware qualification belong to the build/bench owner's separate evidence.

## 2. Clock training, frequency and bounded waits

The [official SD specification](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver5.10.pdf), section6.4.1, requires the supply/initialization interval and at least74 clocks before the first command. It describes the initial allowance as the maximum of1 ms,74 clocks and supply ramp time. CMD must remain high during the initial clocks. A1 ms clock train after valid VDD satisfies the clock/time conditions at100–400 kHz; it is not a substitute for checking the physical power-up assumption. The software's VDDIO5SV write declares a supply valid; it is not a voltage measurement.

The existing separate GPIO-settle delay is another measured1.021 ms. It can potentially overlap the initial train, but the pre-AF line-high checks must still catch missing pull-ups or a stuck line. Avoid replacing it with an arbitrary tiny RC assumption while flying leads and internal pull-ups remain under investigation. This is lower priority than removing the unsupported extra9 ms of clock training.

Identification at400 kHz is within the SD100–400 kHz range. With the new100 MHz kernel, CLKDIV125 is exact. With the historical150 MHz kernel, use ceiling division: CLKDIV188 gives about398,936 Hz; truncation to187 gives about401,070 Hz and exceeds the limit. Keep a separate identification-frequency constant so the existing100 kHz long-erase mode does not change accidentally.

Set `c->clock_hz` and DTIMER consistently: a two-second hardware allowance is800,000 clocks at400 kHz. The250 ms command and two-second readiness DWT limits remain time-based and can stay bounded as before. Update the High Speed host guard's allowed rates and expected CLKCR, initialization proofs, tests and manifests together. Successful command timing also needs wire verification; faster identification is not a request to shorten the card's allowed initialization deadline.

The retained25 MHz cycle spent0.551 ms in CMD0,1.150 ms in CMD8,5.271 ms in CID/RCA/CSD, and2.401 ms in select/readiness. Scaling only their dominant command serialization suggests about7 ms savings at400 kHz, subject to software and card response overhead. Its62 ACMD41 attempts consumed203.689 ms with1 ms retry gaps. Faster commands can simply cause more retries during the same card initialization; do not promise a150 ms gain from that loop.

There is no generic1 ms SD requirement after an idle host changes its clock divider to a compliant rate. The current1.071 ms run-clock-selection envelope is mostly the explicit delay. A short bounded allowance, readback and fresh readiness can replace it in an isolated test. Keep the separate CMD6 requirement of at least eight clocks after switch status before increasing the frequency.

## 3. Readiness and duplicate queries

`ready()` currently issues CMD13, checks ready/TRAN, physical DAT0 high, inactive command/data machines and disabled IDMA, and delays1 ms after an unsuccessful attempt. The retained final-write readiness interval was2.165 ms, including polling quantization. An adaptive interval such as100 microseconds for the first few milliseconds, then1 ms, can reduce overshoot while preserving the total bound and camera progress callbacks. More polls also cost CPU/bus energy; benchmark complete-cycle energy rather than assuming lower latency means lower energy.

A more targeted version waits on the hardware/physical busy condition, then issues one fresh CMD13. It must respect the possible delayed R1b busy assertion and check sticky errors before clearing them. This is a correctness-sensitive replacement, not permission to infer media idle from an earlier DATAEND or a single pin sample.

Four-bit initialization already reads SCR for bus-width capability, and `raw_magic_execute()` reads it again to determine the erased-byte value. Preserve those validated eight bytes in the card/session object and expose a copied result to the storage layer. Invalidate on a new initialization, reset, card change or failure. This is static card information within one session; no second bus transaction is needed merely to use another field. Keep explicit read-SCR operations available for diagnostic tests.

Normal magic-slot completion performs a final checked write readiness and later `sd_deinit()` calls `sd_sync()` again. That extra check measured only0.043 ms including release. Consecutive header reads likewise repeat a before/after readiness boundary. A future no-new-command path could reuse an immediately preceding proof only with exclusive ownership, no intervening card command, no error, exact clock/width, physical DAT0 and inactive host/DMA checks. A boolean left from an earlier operation is insufficient. These small savings should wait until the larger changes are qualified.

## 4. Exposure-safe overlap

In the retained cold trace, sensor START write finished2.313 ms after prefix DWT zero, receiver arm finished7.350 ms, and late NOR loading took about4.004 ms before SD initialization began around11.5 ms. All SD driver code deliberately lives in that late segment; the early path and recovery prefix were kept small to protect capture startup.

Calling today's blocking `sd_init()` before sensor parameters would insert the entire card negotiation into the exposure path. `RAW_PREINIT` already demonstrates that arrangement but is explicitly a diagnostic for streaming, not the normal cold-start solution. It would violate the50 ms goal on the measured cold card.

A small nonblocking clock/pin preparation step immediately **after receiver arm** can train the card while the checked late load runs. The receiver is already armed and the sensor START is already in progress, so this need not delay exposure. The full SD transaction engine can still remain late. After the delay reductions above, only roughly1–2 ms remains to hide this way.

Launching ACMD41 before sensor parameters is possible only with a separately designed asynchronous early stage: issue a bounded command, allow the sensor sequence to run, and return later to its status. It must not call unloaded late code, share mutable ownership incorrectly, or monopolize the CPU during sensor boot/PHY qualification. It also adds early code/load cost and changes the carefully reviewed boot/recovery prefix. The existing timeline offers roughly10 ms of head start before those costs, not hundreds of milliseconds. Defer that larger change until the simpler improvements have measured results.

## Evidence and next order

Measured baseline values come from [the retained cycle trace](../2026-10-25-cycle-trace/README.md) and [its full phase table](../../CYCLE_TRACE.md). The new50 MHz pattern timings above were reported by the root bench owner and should be bound to that experiment's final frozen record before being treated as a benchmark. Relevant code is `sd_card.c`, `magic_runtime.inc`, `late_build.py`, and the generated `capture.c` used by the qualified image. The [protocol review](PROTOCOL-REVIEW.md) records the correctness and electrical constraints.

The bench owner chose a separate reviewed 12.5 MHz trial combining the already tested tail-wait policy with the startup changes below, while leaving unsuccessful 50 MHz electrical trials reproducible. Qualification still requires full image verification and recovery/cleanup proof. Identification at 400 kHz, readiness-polling changes and earlier SD initialization remain deferred.

## Implemented startup profile and its evidence

`SD_STARTUP_OPT=1` requires the reviewed four-bit driver and is initially admitted only as an explicit RAM build. It retains the 1 ms GPIO settling and line-high checks, uses 1 ms of continuous 100 kHz clocks before CMD0, and replaces the 1 ms divider-only wait with 1 us plus fresh CMD13. Expected fixed savings are 9.999 ms, plus the formerly duplicated SCR query. The measured delay can exceed its minimum because the normal camera progress callback still runs. No identification-frequency, final-readiness, width, phase or compensation change is implicit.

This profile assumes the card shares the prototype's already valid 3.3 V rail before GPIO settling. That condition must be checked again if card power becomes independently switched. The firmware's VDDIO5SV declaration is not evidence of rail voltage. Minimum clock/time tests alone cannot establish the physical supply ramp.

The validated SCR is cached against the owning `sd_card_t` pointer only within one initialization. Any driver fault, fresh initialization or deinit invalidates it. A cache hit supplies capability and erased-byte data; it does not create a new idle proof. `sd_read_scr_fresh()` explicitly invalidates the cache and performs a new CRC-checked query. Card replacement requires a new initialization.

The separate 64-byte `sd_startup_proof` contains sixteen unsigned 32-bit fields, in order: magic `0x31504F53` (`SOP1`), version1, GPIO-settle cycles, clock-train cycles, train Hz, minimum train cycles, run-settle cycles, run Hz, SCR wire-read attempts, SCR cache hits, cache-valid, cache-owner address, first error, and three reserved zeros. At 400 MHz the GPIO and train intervals each require at least400,000 cycles; the divider allowance requires at least400 cycles. Train frequency is100,000 Hz; run frequency is12.5 or25 MHz, including the intermediate25 MHz phase of a High Speed build. Successful normal magic capture expects one wire read and one cache hit; deinit clears cache-valid/owner but retains the proof. The record is telemetry, not authorization for reset or shutdown.

`test_sd_startup.cpp` executes the actual driver using microsecond-resolution modeled time and independently checks the interval from SDMMC POWER enable to CMD0. It covers both ordinary clock rates, High Speed, DWT wrap, cached/fresh byte differences, invalid SCR and read CRC, width negotiation failure, owner mismatch, deinit/reinit, unavailable cycle counter and refused gate/clock writes. The model asserts that startup-profile register reads never reach a gated SDMMC host. Real pinned CMSIS ARM C builds pass. Default-off binary identity and physical cold-start results are recorded separately by the build/bench owner.

## Measured startup intervals at 12.5 MHz

The saved `tail125-trace` and `startup-notail-trace` records isolate the following logged intervals. These are one run each, with different card readiness and transport selection; they are not a matched whole-cycle benchmark.

| Interval | Previous profile (ms) | Startup profile (ms) | Reduction (ms) |
|---|---:|---:|---:|
| GPIO settling, unchanged control | 1.020610 | 1.021005 | -0.000395 |
| Initial clock train | 10.020785 | 1.021523 | 8.999263 |
| Divider change and fresh readiness | 1.072440 | 0.148768 | 0.923673 |
| Coordinator SCR lookup | 0.179998 | 0.002970 | 0.177028 |

The three changed intervals total **10.100 ms less**. The divider/readiness envelope includes progress callbacks and CMD13, so its observed duration exceeds the explicit 1 us allowance. ACMD41 took 203.689 ms previously and 12.089 ms in the new run, with 62 versus 4 attempts. That 191.600 ms difference is card-state variation and is excluded from the optimization claim.

Independent parsing of the saved binary waveform found **108 CMD-high rising edges before CMD0**, spanning 1.085040 ms from the first captured rising edge. Identification clocks measured about 10.056 us per cycle; run clocks measured 80 ns median. Host command transitions aligned with falling edges within the analyzer's 4 ns sampling interval. All 113 CRC-valid host commands matched the firmware count, and only one CMD55/ACMD51 pair occurred. All 3,730 written sectors and 14,920 lane CRCs passed; the complete wire payload equaled the retained original camera RAM with its metadata and markers.

See [hash-bound waveform and timing evidence](startup-notail-waveform.json), including replay script and explicit limitations. This was an already powered RAM test: it does not establish a cold supply ramp, analog timing margin, Standby or energy. Separately, [the long-exposure snapshot report](startup-long-snapshots.json) checks all twenty published LINE tails against retained original RAM and confirms that the tail policy added no wait while FRAME was still pending.
