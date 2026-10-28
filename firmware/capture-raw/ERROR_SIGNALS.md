# Red error signals and shutdown

**Corrected and installed October 26:** runtime error handling now executes
from a verified copy outside the camera frame. A complete real frame followed
by an injected code4, and a separate real SD CRC failure, both produced five
four-blink sets and Standby. UART recovery passed during signaling and after
shutdown. See the [fix and qualification](evidence/2026-10-26-error-handler-fix/README.md)
and the preserved [original fault diagnosis](evidence/2026-10-26-error-handler-overlap/README.md).

The selected `--error-blinks` profile displays an error as a numbered set of
red flashes, repeats that set five times, then turns all LEDs off and enters
Standby. It applies to normal capture failures in the existing four-bit
25 MHz startup profile. Successful capture keeps the existing red startup,
blue acquisition, green storage and LEDs-off Standby sequence.

The option is explicit so historical firmware can still be rebuilt. The
[canonical build commands](README.md#build-the-selected-profile-explicitly)
select it; [AGENTS.md](../../AGENTS.md) identifies the exact installed image and
live bench state.

## Codes

| Red flashes per set | Meaning | Current implementation |
| ---: | --- | --- |
| 1 | Low battery | Reserved. There is no implemented battery detector yet. |
| 2 | Camera initialization failed | Sensor startup/configuration, receiver preparation, and START acknowledgement or streaming-state failures. |
| 3 | Image capture failed | Capture timeout, receiver/producer errors, failed frame validation, or sensor STOP failure. A camera fault propagated through an SD write keeps this camera classification. |
| 4 | Storage unavailable | SD initialization, communication, SCR or allocation-scan read failure. |
| 5 | Saving the new photo failed | SD write/completion or final cleanup failure. The current normal path does not add image readback verification. |
| 6 | Storage index or allocation metadata damaged | Reserved. The current magic-slot format has no separate index or corresponding integrity detector. |
| 7 | Storage full | No erased slot remains after the existing allocation scan; existing photos are preserved. |
| 8 | Internal firmware or shutdown guard failure | New prototype fallback for a loader/assertion/internal-state failure, refused shutdown, or unexpected return from low power. It is distinct from the previously agreed product codes 1–7. |

The classifier is in [error_codes.h](error_codes.h). Unknown or partially
written slot markers remain occupied; they are not automatically classified
as damaged metadata. Allocation still starts after receiver arm while camera
work can continue. Adding code 7 does not move a full-card scan ahead of
exposure or change the retained linear frame-buffer design.

Failures before the ROM can load this firmware, arbitrary hangs and
unrecoverable HardFaults cannot be guaranteed to display a code. This change
does not add a watchdog or an automatic retry.

## Timing

Each pulse is **100 ms on**. Consecutive pulses within a set have **400 ms off**
between them. After the last pulse of sets 1–4, the LED stays dark for a total
of **2,000 ms** before the next set starts; this replaces the ordinary 400 ms
gap rather than adding another 2,000 ms to it. After the final pulse of set 5,
the LED stays off for 400 ms before shutdown.

For example, code 2 is:

```text
ON 100 ms → OFF 400 ms → ON 100 ms → OFF 2,000 ms
                       repeat for sets 1–4
ON 100 ms → OFF 400 ms → ON 100 ms → OFF 400 ms → shutdown
```

The nominal display time is `2,500 × code + 6,400` milliseconds: 11.4 seconds
for code 2, 16.4 seconds for code 4 and 18.9 seconds for code 5. These totals
exclude error detection, bounded cleanup and final shutdown preparation.
Delays use the checked 400 MHz DWT counter, with wrap-safe intervals and a
bounded stopped-counter escape; they do not depend on SysTick interrupts.

## Failure shutdown and storage

The capture coordinator first returns faults to the active SD owner and
attempts its existing bounded cleanup when the driver state permits it. It
does not call the SD driver recursively from camera callbacks. The standalone
failure engine then asserts scoped camera, I2C and SD-controller resets and
gates their clocks before displaying the code. It resets the sensor, releases
external data pins without pulls, and deselects NOR before stopping its host.
There are no reads from CSI, DCMIPP, SDMMC, I2C or XSPI register banks in this
last-resort engine, avoiding accesses to already gated or reset peripherals.

This explicitly abandons the failed capture or storage operation. It does
**not** assert that an unresponsive card became ready, change an error into
success, clear the historical ownership/error report, or synthesize an idle
proof. A failed current photo may be incomplete. SD-card behavior after
interrupted writes remains outside the power-loss qualification; the stricter
successful-save commit and idle checks are unchanged.

After the fifth set, the engine disables interrupt/wake sources and checks
the CPU, PWR, BSEC, existing option shadows and debug-emulation state before
Standby. It keeps the required BSEC clock and avoids OTP writes. If the timing
clock or CPU context is unsuitable, signaling may be skipped. If deep-mode
prerequisites cannot be established, it leaves the LEDs off and falls back to
masked shallow WFI. That fallback is not equivalent to the normal Standby
current. Standby destroys ordinary SRAM, including diagnostic records; the
record is not made persistent by displaying a code.

The Nucleo's Standby path controls the target's switched supplies. This is
not a newly implemented LTC3621 RUN/HOLD release or a guarantee of production
camera off-state current.

## Boot layout and recovery

The self-contained failure engine resides initially in the ROM-loaded prefix
at `0x34181840`; a stage-one bridge at `0x34181820` handles failures before
receiver handoff. Before any receiver error path or camera arm, the receiver
copies and compares all 384 words to reserved executable RAM
`0x343C8000..0x343C8600`. It rejects enabled D-cache, invalidates I-cache,
and publishes fresh `ECP1` copy proof at `0x343FD380`. Runtime calls use only
the high-RAM copy. A failed copy falls back to the prefix before DMA starts.
RAM diagnostic builds continue to link their own engine.

The build audits all engine branches and PC-relative loads for relocation
safety, rejects external code/data dependencies, and reserves its destination
outside the frame, stack, low-power helper and LINE snapshots. The copied
engine remains available even if the late storage-code CRC fails. The prefix
must never be called after camera DMA is armed; the earlier implementation
violated this lifetime rule.

The reviewed prefix grows from **5,140 to 6,720 bytes**, while the early
receiver load remains **15,804 bytes** and the receiver stays at NOR offset
`0x2000`. In the old prefix range, the only changed bytes are the six-byte
later failure loop/alignment and the two checked receiver-CRC words. The
complete PE1/PE6 early recovery path and all 20 referenced literals remain
unchanged. The larger ROM-loaded prefix may increase cold-start time; that
cost must be measured rather than inferred from unchanged receiver loading.

UART recovery still means sending the existing qualified PE6 pulse train
across an NRST reset, then proving the exact early park and live code. It is
not a UART wake-from-Standby handler. The failure engine leaves PE6 alone,
does not issue an automatic reset, and never sends NOR deep-power-down, because
ROM must read NOR before that guard runs. The existing exact prefix/sector
allowlists and maintenance checks remain required for host operations.

## Qualification

The corrected normal and post-frame diagnostic builds passed independent
ELF/binary/disassembly review, all20 recovery-literal checks,182 capture tests,
33 recovery/Standby-reader tests, and18 exact/modified/truncated/cross-pair
admission checks. Both installations passed full64KiB physical NOR readback
and unchanged following4KiB checks. The normal, uninjected build is installed.

The explicit `--error-after-frame-test` flash profile acquired all1,909,600
bytes, validated one frame and its guards, stopped the sensor, then entered
the normal code4 failure terminal before any SD operation. During signaling,
read-only ST-LINK snapshots showed the original prefix overwritten, the
entire relocated engine intact, and CFSR/HFSR zero. Current traces showed
five groups of four, the specified timing within the retained±20ms bin/filter
uncertainty, then8.059mA. A second full-frame trial passed UART recovery during
signaling, requested2.123s after power-on.

The normal firmware then encountered a real CMD17 data CRC error at25MHz
with the CLK resistor removed. It likewise showed five groups of four and
reached8.062mA without HardFault. Both complete sequences passed first-attempt
warm UART recovery and guarded SBF=1/PDDS=1/STOPF=0; the flag reader retains
`trial_entry_proven:false`. The failed SD cleanup history remains recorded;
it was not converted into a successful storage operation.

LED states are inferred from current changes, not optical/GPIO probes. Each
trace retains71 startup nonfinite current samples and whole-session validity
false; the complete post-launch windows are finite and contiguous. No new
energy, boot-latency, image-save, resistor-free SD reliability or interrupted
write-preservation qualification is claimed. [Reproducible evidence and limits](evidence/2026-10-26-error-handler-fix/README.md).

### Earlier pre-capture tests

The tests below describe the original build, before the placement defect was
discovered. They remain historical observations, not post-DMA qualification.

[test_error_signal.py](test_error_signal.py) executes the actual pulse scheduler
with a host platform model: all codes, exactly five sets, final dark period,
all 80 timer-failure positions in the longest sequence, invalid-code fallback
and the no-late-helper/register-access constraints. These are software tests,
not physical pulse-width or power measurements.

The exact flash candidate has also passed independent ELF-to-binary and
disassembly comparison, all 20 recovery-literal checks, and exact admission in
both recovery gates. Modified, truncated and cross-paired images are rejected.
The installed four-bit 25 MHz Standby image passed complete independent NOR
readback. A normal cold capture saved slot 51, which was confirmed free before
the cycle; all 3,730 sectors read back at 25 MHz and independent PNG decoding
matched the recovered RAW10 samples. Original camera RAM was lost in Standby,
so this is not an additional camera-source equality test.

Synthetic RAM codes 2 and 7 reached the low-current state and preserved UART
recovery. The complete code-7 current trace contains five sets of seven
pulses. A separate test read back the exact installed 6,500-byte prefix, set
the synthetic stage-one failure result to 17, and entered its failure bridge;
that trace contains five sets of two pulses and a roughly 8.066 mA plateau.
The measured intervals are consistent with the specified schedule within the
retained 5 ms bin/filter uncertainty. These are current-step observations,
not direct LED optical measurements. Startup nonfinite samples and the earlier
partial recording remain explicit in the archive.

UART recovery passed after completion and when requested about 1.375 seconds
into the nominal 11.4-second prefix sequence, with nine good pulses and zero
bad pulses. Guarded post-completion reads observed SBF=1/PDDS=1/STOPF=0 and
retain `trial_entry_proven:false`. Tests inject the error category; they do
not reproduce every physical camera/card failure or qualify interrupted-write
preservation. The [durable evidence and offline replay](evidence/2026-10-26-error-blinks/README.md)
separate each observation, while [the bench checkpoint](../../AGENTS.md)
records the live state.
