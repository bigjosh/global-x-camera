# Earliest GPIO boot marker experiment

**Unattended programming and recovery:** the observed October 17 USB communication failure was recovered with the [guarded WinUSB pipe helper](stlink-recovery.md), without a cable change or hub reset. The [bounded RAM NOR programmer](experiments/rom-nor-programmer/README.md) now reads, programs and verifies the first 64 KiB while preserving ROM's working clocks and XSPI routing. Explicit HOTPLUG **AP1** accesses the awake diagnostic after normal flash boot. Do not repeat the standard external loader's failing full initialization in this state.

**October 17 completed comparison:** nine autonomous cold boots passed. Additional initial firmware costs about **0.262 ms/KiB**; a shorter marker path did not establish an overall gain beyond observed variation. CH5 measures main VDDIO at CN3 pin 5. The board is left on the awake debug baseline, with the original exact sector backed up. See the [results, evidence and final state](optimization-results-2026-10-17.md).

This is a small **secure FSBL payload**, independent of the camera bring-up program. It raises **PD0 first**, raises **PE0 immediately afterward**, and leaves both high. **October 17, 2026:** three recorded API-controlled power cycles using CN8 → CN9.3 → JS110 → CN9.2 booted from NOR, with **15.20–15.43 ms from NRST rising to PD0**. The earlier roughly 50 ms reset hold did not recur after a one-time reset-release diagnostic. The slow 5 V ramp makes a late 4.50 V crossing unsuitable as a full-startup reference. See [current results and qualifications](bench-results-2026-10-17.md); the [October 16 results](bench-results-2026-10-16.md) preserve the earlier 62.75–62.91 ms ST-LINK-source measurements.

It uses no HAL, RTOS, C runtime, PLL changes, sensor initialization, image transfer, OTP programming, or external-memory writes. Both marker pins are configured as push-pull, no pull, low-speed outputs; all other pins' settings are preserved. The existing PD0 and PE0 probe connections remain appropriate.

## Build

The existing pinned vendor checkout from `firmware/bringup/prepare.ps1` must be available. From the repository root:

```powershell
./firmware/boot-timing/build.ps1
# Or provide another Arm GCC installation:
./firmware/boot-timing/build.ps1 -ToolchainBin 'C:/path/to/arm-gcc/bin'
```

The script locates the already-used STM32CubeIDE compiler when necessary. It makes no persistent PATH changes and does not access the board. It first compiles `address_check.c` without linking it, checking the register constants against ST's CMSIS header at commit `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`.

Ignored `build/` contains `first_gpio.elf`, `first_gpio.bin`, a disassembly, a link map, sorted symbols, and `build-info.json` with the payload hash and vector words. `-SourceDir` and `-OutputDir` override the local input/output directories.

**The `.bin` is only a raw payload.** Wrap it for autonomous boot with `python firmware/boot-timing/add_boot_header.py firmware/boot-timing/build/first_gpio.bin firmware/boot-timing/build/first_gpio_boot.bin`. The [header evidence](header-evidence.md) documents its independent comparison against ST-generated output. Backup and programming are separate operations; the bench record identifies the preserved original NOR contents.

## Capturing and analyzing

**API-only instrument control:** requested October 16, 2026. Use [Saleae's automation API](https://saleae.github.io/logic2-automation/) for the LP8 and [the Joulescope driver API](https://github.com/jetperch/joulescope_driver) for the JS110; do not operate their interfaces with computer-use tools. Logic 2 must remain running as the Saleae backend. The Joulescope GUI must release the JS110 before a direct-driver session takes ownership. Preserve settings and power during handoff. A passive API check on October 16 reached Logic 2.4.46 and enumerated the physical LP8 and JS110; it did not open the JS110, change target power, or start a capture.

Use the existing Logic 2 automation server on port 10430 and the isolated dependencies prepared for the camera bring-up. `python firmware/boot-timing/capture_manual.py tmp/bringup/new-boot-capture` records all six connected channels for up to 180 seconds. Create a file named `stop` in that output directory after the physical test. The script saves `.sal`, raw CSV, configuration, and timing JSON; it neither switches power nor changes firmware. `analyze_capture.py <capture-directory>` can reproduce analysis offline. Do not use the older multi-pulse wiring-test verdict for this two-marker payload.

`js110_session.py` keeps one restore-mode JS110 connection open and accepts explicit requests through a JSON mailbox. `cycle_once.py` requests an off/on cycle from that session. Use the [verified CN8 supply wiring](../../docs/power/nucleo-debug-isolation.md#board-source-using-the-second-usb-connector), with all CN9 shunts absent. The old CN9.1/ST-LINK route shut down on reconnection. With the current setup, use a 20-second off dwell and verify actual rail discharge: the measured 5 V tail takes about 7 seconds to fall below 0.1 V. Start a fresh capture and confirm `CAPTURE_STARTED` before launching a cycle; leave enough capture time for off dwell, restoration and a stable final interval. The session must release ownership before the Joulescope GUI reconnects.

`inspect_cycle.py <capture-directory>` performs an independent offline review of a single off/on capture, including continuous off intervals, all threshold crossings, final voltages and marker order. Keep its review alongside the generic summary: `analyze_capture.py` can report a zero-duration off interval when a noisy final sample near 0.1 V obscures a much longer preceding low interval. Neither successful process exit nor a range command establishes physical boot success.

`plot_capture.py <capture-directory> <output.png>` generates the measured plot and SVG. It uses Matplotlib, installed locally for this experiment with `python -m pip install --target tmp/bringup/plot-deps matplotlib==3.10.7`.

Normal flash boot uses **JP1 (BOOT0) and JP2 (BOOT1) on pins 1–2**. The original minimal marker does not reopen debug access; the revision-2 experimental image does so after both measured edges and stays awake. Normal-boot AP1 access, RAM programming and subsequent autonomous power cycles have now worked without changing jumpers. Use the [results record](optimization-results-2026-10-17.md) for the image actually left on the board. Development mode remains a recovery option, not a routine requirement for these trials.

`nor_bench.py info --build <reviewed-build-directory> --out <new-directory> --sequence <unique-number>` runs the reviewed identity/status check. Its `write` operation additionally requires `--current <exact-current-64KiB-file>` and `--desired <desired-64KiB-file>`. Both CRCs are checked before write enable, only changed 4 KiB sectors are erased, and the entire 64 KiB result is compared on the host. An unchanged-buffer test issued zero write-enable commands, and a deliberately wrong current CRC was refused before writing. The host polls completion without halting an active NOR operation. A failure leaves the target as-is for diagnosis; it does not reset or retry a flash write.

The RAM helper's code must occupy fresh instruction memory after a cold boot or remain byte-identical to the code previously executed there. Do not overwrite executed code with a changed helper while I-cache is enabled. Read the [programmer's preconditions and fixed memory map](experiments/rom-nor-programmer/README.md) before use; this is a bench tool for the verified ROM state, not a general production flash driver.

## Execution sequence and interpretation

1. Mask configurable interrupts, establish a small secure stack, and point secure VTOR at the payload's core exception vectors. Faults enter an infinite loop for debugger inspection.
2. Enable the GPIOD and GPIOE AHB4 clocks. Read back AHB4ENR as ST's LL driver does, then apply a data synchronization barrier.
3. Configure only PD0's output type, slew rate, and pull settings. Preload its output latch high and switch its mode to output. **This is the first marker edge.** `pd0_first_edge_store` labels the mode-register store.
4. Perform the same operations for PE0. **Its edge confirms continued execution.** `pe0_second_edge_store` labels that store.
5. Clear SLEEPDEEP and remain in an ordinary `WFI` loop with the marker outputs high. `boot_markers_ready`/`boot_idle` identify completion. This is not an idle-power optimization test.

The first edge includes this short, fixed assembly setup after ROM handoff. It is not literally the first instruction, nor does it mark sensor exposure. An instruction count alone cannot convert that interval to nanoseconds: CPU/bus clocks, stalls, barriers, pad slew, and probe thresholds affect it. The PD0-to-PE0 interval should be short and contains no intentional delay.

A debugger-loaded RAM run can validate the pin behavior but **does not measure autonomous boot**. For a cold-boot result, use the packaged image in external NOR, normal boot selection, and an externally recorded supply transition after confirmed discharge. A reset-only result starts with already powered rails and must be labeled separately. Do not include PC download or debugger-start delays in either result.

The GPIO pins are analog inputs before this payload drives them; their prior voltage is not controlled by the payload. Confirm a clean low baseline externally rather than interpreting an arbitrary floating transition as the first marker. The analysis used for the longer `probe_smoke_run` pulse sequence does not apply to this two-edge experiment.

## Address, clock, and security evidence

| Item | Value / source |
|---|---|
| Payload/vector address | `0x34180400`, immediately after the ROM's 1 KiB header area at `0x34180000`; UM3234 memory layout and the pinned Nucleo linker script |
| Initial stack | `0x34181000`; reserved stack region `0x34180C00`–`0x34180FFF` in secure AXISRAM2 |
| Secure RCC base | `0x56028000` |
| AHB4 clock enable / readback | offsets `0xA5C` / `0x25C`; bits 3 and 4 enable GPIOD/GPIOE |
| Secure GPIOD / GPIOE bases | `0x56020C00` / `0x56021000` |
| GPIO offsets | MODER `0x00`, OTYPER `0x04`, OSPEEDR `0x08`, PUPDR `0x0C`, BSRR `0x18` |
| Secure context | Cortex-M boots secure/privileged; GPIOs default secure. The payload retains that context and does not change SAU, RIF, GPIO security, or privilege attributes. |

ST's `system_stm32n6xx_fsbl.c` describes execution after the Boot ROM and performs substantially more housekeeping. This experiment intentionally does not call it. Its source comment that HSI is selected *at reset* does not establish the clock at ROM handoff: **UM3234 §3.12.1 specifies nominal ROM clocks of 400 MHz CPU / 150 MHz AHB/APB / 300 MHz AXI**, with a 64/32/64 MHz engineering configuration also possible. The payload changes neither configuration and requires no frequency assumption.

RM0486 §15.3.16 states that GPIO ports are secure after reset; its security overview states that the CPU boots secure/privileged. The VDDIO2–5 port lists in the power chapter exclude PD0 and PE0, so these pins use the main I/O domain and do not require an auxiliary VDDIO-valid-bit sequence. Only normal low-speed GPIO behavior is required here. The compensation-cell initialization and other full-system housekeeping in ST's standard startup are not a substitute for later production validation.

Primary references:

- [UM3234 — STM32N6 Boot ROM](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf), especially memory layout and §3.12.
- [RM0486 — STM32N6 reference manual](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), GPIO and power chapters.
- [Pinned STM32N657 CMSIS device header](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Include/stm32n657xx.h).
- [Pinned FSBL system initialization](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Source/Templates/system_stm32n6xx_fsbl.c).
- [Pinned AHB4 clock-enable implementation](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver/Inc/stm32n6xx_ll_bus.h).
