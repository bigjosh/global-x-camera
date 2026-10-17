# ROM handoff, sensor reset, and remaining critical path

Offline assessment, October 17, 2026, with subsequent results supplied by the root bench controller. No-reset cold captures have produced valid images; their electrical sequencing qualification remains open.

## What the previous boot experiment establishes

The [completed boot-size comparison](../boot-timing/optimization-results-2026-10-17.md) measured three shorter-marker cold starts at14.957–15.165ms from external NRST rise, using a1408-byte packaged image (372 raw executable bytes padded to384 plus1024-byte header/alignment area). The awake baseline varied15.063–15.672ms. The descriptive load-size slope was0.262ms/KiB, consistent with the ROM's32MHz single-bit SPI transfer. These are empirical observations with supply-ramp dependence, not a statistically established lower bound.

The trimmed RAW8 v24 prefix is 3356 raw bytes, versus 372 raw bytes for the tiny marker. Applying the descriptive 0.262 ms/KiB slope to that 2984-byte difference gives approximately 0.76 ms of extra ROM transfer. The selected native RAW10 v25 prefix is 4008 raw bytes (5056 bytes packaged), including memory bootstrap work; its corresponding deliberately generous size-saving estimate is approximately 0.93 ms. This replaces the earlier v24b prefix of 4916 raw bytes and its 1.16 ms estimate. The capture prefix cannot discard all its sensor setup, guarded loading and handoff code and still perform its job. Alignment/padding and supply-ramp variation also affect the actual comparison. Previous shorter-marker tests did not isolate an overall timing improvement beyond baseline variation. A reasonable engineering model therefore assigns roughly 15 ms to ROM plus tiny handoff work on this supply setup, with at least the observed several-tenths-millisecond variability. Do not turn the fastest 14.957 ms run into a guaranteed lower bound.

The [ROM optimization limits](../boot-timing/experiments/optimization-limits.md) already review the supported alternatives. Initial sNOR uses fixed0x0B single-line32MHz reads and loads the selected FSBL before handoff. Header alignment is1024bytes; no inspected header field selects quad/octal initial transfer or runs user GPIO code before the load. EADLY resets to5ms on power-on, so a later software write cannot remove it from that cold start. Boot clock/source alternatives involve OTP or different hardware. None is proposed here.

UM3234 Rev5 §3.12.3 uses PN6/PN1/PN2/PN3 for this serial-NOR boot. PO5 is not among the documented pins used by that path. Its reset/default I/O domain is isolated until VDDIO2SV is set. RM0486 Rev4 §13.5.7 and PWR_SVMCR3 describe that isolation, but do not provide an externally measured PO5 waveform.

## The sensor may already be booting during ROM

The [P-board PCB4280D schematic](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf), sheet2, connects R17(100k) between sensor XSDN and VDDIO. D1(BAT20JFILM) connects that node to host NRST; the existing low/high reset behavior is consistent with a low clamp through the diode. The [BOM](https://www.st.com/resource/en/bill_of_materials/steval-cam-m0i-bom.pdf) fits R17/D1/R4 and omits R12. Thus module rails are independently enabled and XSDN has a sensor-side pull-up. This is not a PGOOD-controlled release.

The [MB1940 C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), sheets3/11, routes PO5 to NRST_CAM. Its optional10k reset pull-up R48 is marked DNF; no fitted reset pulldown is shown in the inspected camera sheet. The [Nucleo manual](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf) maps PO5 to CN6pin17. These circuit facts support a cold trial which does not deliberately restart the sensor at ROM exit.

**Qualification limit:** UM2602 §5.2 requires CLKIN before XSHUTDOWN release; the sensor datasheet requires valid supplies. The passive R17 circuit does not prove those conditions. Neither the existing main/auxiliary rail probes nor a successful image establish camera VCORE/VDDIO/VANA, oscillator and XSDN sequencing. A production implementation must qualify those signals or provide a controlled hardware release. An unchanged-board no-reset success is useful timing evidence with this limitation, not automatic approval of that power sequence.

`STAGE1_SKIP_SENSOR_RESET=1` in `stage1.c` is a cold-only, bounded experiment. It records initial PO5mode/pulls/latch/input and PWR state; rejects an unexpected driven/alternate-function/pulled pin; preloads the output latch high while input/analog; then removes isolation and enables high output without a deliberate low pulse. This also prevents the frozen stage2's later OUTPUT initialization from asserting reset. The sensor must still reach the expected READY_TO_BOOT state; there is no silent reset fallback. Analog/isolated IDR is not proof of physical XSDN voltage.

New stage1 STATUS words at0x341F3000:28 policy;29 MODER;30 PUPDR;31 ODR;32 IDR;33 OTYPER;34 SVMCR3 (initial values);35 MODER,36 ODR,37 IDR (after high enable). Events208/209 mean snapshot/high-enable, not measured reset release. The default path retains the102nominalµs low pulse and events201/202. Both branches preserve guarded read-only loading, CRC and post-error debug access. The no-reset branch passed offline Werror/general-register-only compilation; that is not hardware validation.

## The overlap changes if automatic startup succeeds

With deliberate reset, the serial dependency is approximately:

`ROM + prefix → max(sensor READY, stage2 load + independent receiver work) → required sensor transactions → START-to-strobe`.

Root measured a5.16ms stage2 copy and6.46ms sensor READY delay in one staged build. Since the former is hidden inside the latter, accelerating the copy alone gives no optical-start saving until another dependency changes.

If the sensor is already ready at handoff, the copy becomes exposed. Skipping reset then saves approximately only the uncovered1.30ms in that example, not the full6.46ms. A15KiB image loaded by ROM costs about3.84ms, while the separate prefix plus the observed byte-copy loop costs roughly0.3+5.16ms. Thus a monolithic no-reset build is a worthwhile matched comparison, potentially around1.6ms faster than that particular staged loader. These are model predictions; compare exact build sizes and measured captures.

The stage1 byte loop writes three volatile progress fields per iteration and computes CRC through two nibble-table steps per byte. Its single-line bus transfer is theoretically about3.76ms for15040bytes, before command overhead. The observed5.16ms leaves about1.4ms of potential software overhead. Word reads and sparse progress updates are now implemented behind `STAGE1_WORD_READS`; they preserve finite bounds, error detection, byte order, CRC and tail handling. This is a new application loader, not a change to the frozen maintenance programmer. See [loader optimization notes](loader-optimization.md) for measured bottlenecks and subsequent options.

No firm27–29ms optical-start floor should be claimed before resolving the automatic-start and load-overlap alternatives. A defensible near-minimum judgment must bound the remaining serial work and treat the undocumented START latency as an experimentally tested invariant rather than a proven silicon minimum.

## Subsequent cold trials

The root reported v18 no-reset success with visible LED image and first strobe at 29.3552 ms after NRST. Prefix snapshots showed PO5 initially analog (MODER4095), no pulls, ODR0, and SVMCR3=512; after glitch-free high enable, ODR/IDR bit5 were both set. Initial IDR0 was observed while the domain remained isolated and does not contradict a sensor-side pull-up.

The v20 early-START split moved sensor configuration ahead of the second-stage load. It produced a recognizable first image with strobe at 24.6696 ms. Thus the earlier 27–29 ms estimate was not a floor. Its copy/receiver margin was about12 nominal microseconds to the conservative4.5ms software guard; the actual receiver lead before the measured first strobe was about768µs. These are different deadlines. V22 subsequently increased margin to that guard to approximately1.513ms by reaching the32MHz wire-transfer floor. The copy occurs within the sensor's observed START-to-strobe interval; reducing that copy now primarily improves margin rather than advancing exposure.
