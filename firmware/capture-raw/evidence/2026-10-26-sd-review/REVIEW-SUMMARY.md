# SD review: changes, results and remaining work

October 26, 2026. The review found correctness fixes and **10.100 ms less fixed startup work**. A complete 50 MHz write succeeded, but six sustained 50 MHz reads failed CRC checks. **50 MHz is not reliable yet.** Reviewed four-bit 12.5 MHz with startup improvements and no tail wait is installed after cold awake and Standby tests, full saved-image readbacks and first-attempt UART recovery. The [README](README.md) records the exact qualification and its limits.

## What changed

- **Safer completion.** Set the timeout before CMD7 busy; drain the full 256-word FIFO when aborting CPU-managed reads; finish CMD12 busy and check late errors before clearing data-path state. Limit the address exception to a complete read at media end. Failed operations remain failed after successful cleanup.
- **Explicit High Speed setup.** The existing 150 MHz kernel cannot divide to 50 MHz; truncation would generate 75 MHz. The experiment owns a separate 100 MHz kernel, validates CMD6 negotiation and restores the mux before recovery. Other clocks stay unchanged. High Speed uses the datasheet's post-rising launch; 12.5 MHz retains falling launch.
- **Less startup work.** Keep 100 kHz identification, reduce initial clocks from 10 ms to 1 ms and divider settling from 1 ms to 1 us, and reuse validated SCR within one card session. Retain GPIO and readiness checks. The shorter allowance assumes the existing shared 3.3 V rail is already valid.
- **Separate DMA experiments.** A bounded tail wait can finish sensor STOP before choosing complete-buffer IDMA; incomplete frames still start progressive writes immediately. A separate IDMA read path removes CPU FIFO servicing. Both retain completion/security/ownership checks and remain outside the selected 12.5 MHz profile.

The [primary-source review](PROTOCOL-REVIEW.md) records the manual, datasheet, errata and SD specification basis. Actual-driver tests cover errors, ownership, cache lifetime and clock restoration; they do not establish electrical margins.

## Measured improvements and their limits

| Logged interval | Previous profile | Startup profile | Reduction |
|---|---:|---:|---:|
| Initial clock train | 10.020785 ms | 1.021523 ms | 8.999263 ms |
| Divider change plus fresh readiness | 1.072440 ms | 0.148768 ms | 0.923673 ms |
| Coordinator SCR lookup | 0.179998 ms | 0.002970 ms | 0.177028 ms |
| **Total of these intervals** | | | **10.100 ms** |

GPIO settling stayed about 1.021 ms. ACMD41 separately changed from 203.689 ms to 12.089 ms, with 62 versus 4 attempts; that card-state variation is **excluded** from the savings claim. This is not a matched whole-cycle or energy benchmark. [Detailed evidence](startup-notail-waveform.json).

The waveform verified 108 initial clocks, falling-edge host launch, one SCR query, all 3,730 write packets/14,920 lane CRCs and complete wire-to-original-RAM equality. The [long-exposure test](startup-long-snapshots.json) matched all twenty LINE snapshots and began writing 9.433 ms before FRAME without a tail wait.

At 50 MHz, one capture waited **5.521 ms** for final-sector publication, then spent **89.282 ms** in the SD write call using IDMA. Subsequent **12.5 MHz** readback matched every original byte. The earlier roughly 205 ms PIO result used different scene/pattern and electrical conditions, so it is not an isolated A/B speedup. At 12.5 MHz, tail waiting added delay without improving the approximately 321 ms storage phase and was excluded. [50 MHz write](tail50-outcome.json), [12.5 MHz trials](startup125-trials.json). No energy improvement is claimed.

## Why 50 MHz remains open

Six sustained reads failed: two with uniform slew, one with mixed slew, two fixed-compensation variants, and one using receive IDMA. Earlier successes did not survive repetition. All failures preserved their CRC error and separately proved cleanup/clock restoration. [Failure archive](hs50-read-failures.json).

Next, investigate signal integrity: shorten wiring/returns, move CLK series termination near the MCU source, then compare otherwise identical tests with and without SD probes. Keep the failing setup as a control and change one variable at a time. Inspect ringing and timing at the card with analog measurements. The analyzer's 4 ns resolution cannot prove the width or cause of narrow digital CLK pulses; flow control and wiring remain hypotheses.

## Deferred work

- **DTMODE:** the manual prescribes mode 3; ST HAL uses mode 0 with fixed DLEN and CMD12. The manual also uses a known length, so that does not resolve the discrepancy. Keep the tested path pending an isolated comparison or ST clarification.
- **400 kHz identification:** needs correct division, timeout/proof updates and validation. It reduces command serialization, not internal card initialization.
- **Earlier initialization:** an asynchronous design must preserve the 50 ms exposure target and early recovery; blocking SD initialization before camera setup would threaten both.
- **Readiness and power loss:** retain fresh completion checks. Faster polling, production margins and arbitrary SD power-loss safety need separate evidence.

The [optimization audit](OPTIMIZATION-AUDIT.md) contains implementation details and telemetry layouts.

The [final cold qualification](FINAL-QUALIFICATION.md) records exact installed
identities and full image checks. The separate [Standby wire review](FINAL-STANDBY-WIRE.md)
verified all 3,730 packets and 14,920 lane CRCs against the retrieved image.
