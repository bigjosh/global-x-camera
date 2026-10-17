# Earliest GPIO boot marker experiment

This is a small **secure FSBL payload**, independent of the camera bring-up program. It raises **PD0 first**, raises **PE0 immediately afterward**, and leaves both high. **Tested on October 16, 2026:** two autonomous USB power-ups reached PD0 in **62.75–62.91 ms from the target 5 V rail's first 4.50 V crossing**, including roughly 50 ms with NRST held low. The observed NRST rising edge to PD0 was **12.92–13.43 ms**. See the [bench results and qualifications](bench-results-2026-10-16.md).

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

Use the existing Logic 2 automation server on port 10430 and the isolated dependencies prepared for the camera bring-up. `python firmware/boot-timing/capture_manual.py tmp/bringup/new-boot-capture` records all six connected channels for up to 180 seconds. Create a file named `stop` in that output directory after the physical test. The script saves `.sal`, raw CSV, configuration, and timing JSON; it neither switches power nor changes firmware. `analyze_capture.py <capture-directory>` can reproduce analysis offline. Do not use the older multi-pulse wiring-test verdict for this two-marker payload.

`js110_session.py` keeps one restore-mode JS110 connection open and accepts explicit requests through a JSON mailbox. `cycle_once.py` requests an off/on cycle from that session. **The present ST-LINK supply shut down when JS110 reconnected the load**, so the successful measurements used manual ST-LINK USB reconnection. Resolve that supply behavior before relying on automatic cycling. The session must release ownership before the Joulescope GUI reconnects.

`plot_capture.py <capture-directory> <output.png>` generates the measured plot and SVG. It uses Matplotlib, installed locally for this experiment with `python -m pip install --target tmp/bringup/plot-deps matplotlib==3.10.7`.

The board is currently configured for this standalone marker: **JP1 (BOOT0) and JP2 (BOOT1) on pins 1–2**. For the RAM-only camera/debug test, return JP2 to pins 2–3 with board power removed. A read-only ST-LINK hot-plug attempt could not access the MCU in this minimal standalone image; the image does not configure debug access.

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
