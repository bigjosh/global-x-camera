# Nucleo camera bring-up

The NUCLEO-N657X0-Q and mounted CAM-6G3-073CLR captured a recognizable monochrome image on October 15, 2026. This directory preserves the small RAM-only test and the changes needed to reproduce it using ST's camera example.

This is a hardware and image-capture proof. It does not qualify full-resolution RAW10 capture, the 50 ms cold-start target, battery operation, NAND storage, PTP, or the production PNG export path.

## Hardware and tools

- NUCLEO-N657X0-Q with the CAM-6G3-073CLR camera mounted.
- Development boot mode: **JP2 on pins 2–3**. Leave the other board settings as used for normal ST-Link operation. The executable is loaded into SRAM and is lost when power is removed.
- One USB connection to the onboard **ST-Link** supplies power, debugging, and its virtual serial port. The tested Windows machine assigned **COM8**; another machine may assign a different port. No second cable to the target USB connector is required for this test.
- ST's Arm GNU toolchain **GCC 12.3**, GNU Make, and Git for Windows' `sh`.
- **STM32CubeProgrammer 2.23** and **ST-Link GDB server 7.14**, obtained through the STM32Cube command-line tool bundles on the bring-up machine.
- Python with Pillow for the optional host-side PNG conversion.

The serial console uses **115200 baud, 8 data bits, no parity, and one stop bit**. The pixels are retrieved through the debugger, not through the serial console or a camera USB protocol.

The older local CubeProgrammer 2.17 installation did not support this MCU. The working tools were installed with `cube bundle --yes install programmer stlink-gdbserver` after obtaining ST's [STM32Cube CLI](https://dev.st.com/stm32cube-docs/stm32cubecli/latest/en/docs/markup/STM32CubeCLI_Getting_Started/STM32CubeCLI_Installation.html). ST-Link firmware V3J15M6 worked without an upgrade. The probe reported STM32N657 revision B, device ID `0x486`, at approximately 3.28 V.

## Source and local changes

Upstream: [STMicroelectronics/x-cube-n6-camera-capture](https://github.com/STMicroelectronics/x-cube-n6-camera-capture), pinned to commit [`e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/tree/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a), release v2.0.1. Its dependencies are included in that repository. The adapted capture code uses ST's camera application and middleware interfaces. [ST-LICENSE.md](ST-LICENSE.md) preserves the upstream `Src/LICENSE.md`; retain that license and the ST source notices when copying or modifying this code.

| File | Purpose |
| --- | --- |
| `upstream.patch` | Enables the VD56G3 build path, substitutes the capture application, enables sensor diagnostics, disables D-cache for the initial test, removes the unused FSBL-overlap assertion, and removes the OTP-programming and external-NOR initialization paths. |
| `capture_app.c` | Configures the sensor and image pipeline, allows three settling frames, captures one final hardware snapshot, and keeps its pixels and diagnostics in RAM. |
| `prepare.ps1` | Prepares the pinned upstream checkout and applies the bring-up changes. |
| `build.ps1` | Builds the Nucleo/VD56G3 executable using the local toolchain. |
| `capture.ps1` | Resolves local paths and runs Arm GDB in batch mode using the capture template. |
| `capture.gdb` | Template for loading the executable into SRAM, running the capture, checking its diagnostic state, and retrieving the framebuffer. |
| `decode_frame.py` | Converts the retrieved Y8 pixels into a host-viewable image. |
| `probe_smoke.ps1` / `probe_smoke.gdb` | Runs an optional RAM-only GPIO wiring test and pulses physical NRST. |
| `probe_capture.py` | Records the Logic Pro 8 while running a stimulus, then checks the observed wiring-test pattern. |

The unmodified ST application includes a call that programs OTP configuration bits. The bring-up patch removes that call and its source from the build. It also removes external-NOR initialization; this test requires **no OTP programming, external-flash erase, or external-flash programming**. Use the patched source build described here rather than substituting an upstream prebuilt image.

The Nucleo linker maps the capture buffer's `.psram_bss` section to **internal AXI SRAM**, despite that section's name. The tested buffer starts at `0x34000000`; code and vectors are loaded into the SRAM region beginning at `0x34180400`.

## Reproduction sequence

From the repository root, prepare and build:

```powershell
.\firmware\bringup\prepare.ps1
.\firmware\bringup\build.ps1
```

The default source directory is `tmp/bringup/x-cube-n6-camera-capture`. Preparation checks out the pinned revision, applies `upstream.patch` idempotently, and copies `capture_app.c`. The build selects **NUCLEO-N657X0-Q** and **VD56G3**, producing `build/Project.elf` in that checkout. Neither script accesses the board. Both accept `-SourceDir`; the build also accepts `-ToolchainBin`, `-MakeExe`, and `-ShellExe` when automatic tool discovery does not find the intended installation. Windows may require Git's per-command `core.longpaths=true` for upstream's generated CMSIS documentation.

Connect the board's ST-Link USB port, select development mode with JP2 on pins 2–3, and reset the board. Optionally open its serial console using the settings above. In one terminal, start the server, replacing the placeholder with the local directory containing `STM32_Programmer_CLI.exe`:

```powershell
ST-LINK_gdbserver -p 61234 -l 1 -d -s -e -cp "<CubeProgrammer bin directory>" -m 1 -g
```

This assumes `ST-LINK_gdbserver` is on `PATH` and there is one connected probe. An explicit probe serial number is unnecessary in that setup; select the intended probe if multiple probes are connected.

In a second terminal, starting from the repository root, run the capture wrapper with the actual Arm GDB executable path:

```powershell
.\firmware\bringup\capture.ps1 -GdbExe "<absolute path to arm-none-eabi-gdb.exe>"
```

`-GdbExe` defaults to `arm-none-eabi-gdb` if that executable is on `PATH`. The wrapper also accepts `-SourceDir` and `-OutputDir`, defaulting to the pinned checkout and `tmp/bringup`, respectively. It substitutes absolute paths into the template and runs GDB in batch mode; the tested GDB build has no embedded Python support. Do not execute `capture.gdb` directly. If a different source directory was prepared, pass the same `-SourceDir` here.

The wrapper generates `capture-run.gdb` and `gdb-capture.log` in the output directory, loads the checkout's `build/Project.elf` into SRAM, and retrieves `frame-640x480-y8.raw`. Its success checks require `g_capture_ready == 1`, `g_capture_stage == 5`, and `g_final_frame_errors == 0`; also inspect the other capture/error counters. After successful retrieval, it resets the board back to the development ROM and disconnects. The framebuffer contains **307,200 bytes**: 640 × 480 pixels, one unsigned byte per pixel, no file header and no row padding.

After the debugger returns, convert the raw frame from the repository root:

```powershell
python firmware/bringup/decode_frame.py tmp/bringup/frame-640x480-y8.raw tmp/bringup/first-capture.png
```

The decoder defaults to 640 × 480 and takes the input and output paths shown. Keep raw captures, previews, and local logs under `tmp/bringup`; they are intentionally excluded from the public repository.

The test has a bounded frame wait and retains its failure state for inspection. A filled buffer or successful memory download alone is not evidence that a complete camera frame was received.

The debugger stops at the named `capture_complete` function after diagnostics and buffer freeze. This breakpoint remains valid when source line numbers change.

## Capture configuration

The supplied middleware initializes the sensor in its **1120 × 1364 RAW8 mode**. DCMIPP pipe 1 takes an aspect-preserving centered crop and scales it to **640 × 480 Y8**. Exposure is set manually to **10,000 µs (10 ms)** and total gain to **0 mdB**, selecting unity analog and digital gain through the VD56G3 driver.

The application first streams three settling frames. It then stops the continuous receiver, requests one hardware snapshot, waits for completion, and stops the receiver again. This avoids freezing a buffer while another frame is partly overwriting it. The final buffer remains untouched while the host retrieves it through ST-Link.

D-cache is disabled for this initial proof; the capture code also contains cache-maintenance guards. Cache-enabled production operation needs its own verification.

## Observed result — October 15, 2026

| Measurement | Observed value |
| --- | --- |
| Sensor model ID | `0x5603` |
| Sensor revision register | `0x3110` |
| Sensor ROM revision | `0x0420` |
| Frame-completion count | 4: three settling frames and one final snapshot |
| Vsync count | 4 |
| Application capture-sequence time | Approximately 803 ms |
| First saved frame pixel minimum / maximum | 19 / 255 |
| First saved frame mean pixel value | 38.3743 |
| First saved frame pixel sum / FNV-1a | 11,788,581 / `0xdc298738` |
| Final snapshot error-callback count | 0 |
| Earlier CSI error | One D-PHY control error; accumulated flag `0x00008000` |

The first retrieved raw frame's SHA-256 is:

```text
3c4dbbb23aa5d6b0f183f919cac4ddba91e131af5466d0285327b46f6f58f5e1
```

The first raw file's pixel sum and FNV-1a matched the firmware's UART diagnostics, linking the retrieved bytes to the completed capture. A second run also completed with four frames, four vsync events, approximately 803 ms elapsed, and no new final-snapshot error callbacks. Its pixels had minimum 19, maximum 255, sum **11,653,007**, and FNV-1a **`0x17793f9e`**; these different bytes show a fresh capture rather than reuse of the first buffer.

The first build completed with ten warnings in unused upstream USBX standalone code concerning array bounds. The added capture source produced no warnings. These upstream warnings do not qualify the USB stack; this test does not execute a camera USB protocol.

The observed revision's upper byte, `0x31`, selects the fast-boot path in this pinned driver, skipping its firmware and VT patches. This verifies the fitted unit against the supported revision inspected here. It does not establish that `0x31` will remain the newest sensor revision; factory commissioning must continue to compare actual silicon against the qualified revision for that build.

The approximately 803 ms measurement starts inside the application capture sequence and includes conservative middleware initialization and settling frames. It is **not** button-to-exposure latency or a cold-power-start measurement. Likewise, the earlier `HAL_DCMIPP_CSI_ERROR_DPHY_CTRL` event remains an issue to characterize: the final snapshot reported no new error callbacks, but this does not qualify the link across startup conditions or repeated operation.

The source, reproduction instructions, and numeric results are retained in the public repository. The photographed scene and its image files remain local in ignored temporary storage.

The saved `capture.ps1` wrapper was also exercised against the physical board after the incremental rebuild. It completed the snapshot, downloaded all 307,200 bytes, and reset/disconnected successfully. Host decoding matched the firmware's pixel sum **11,384,148** and FNV-1a **`0x9739207f`**; raw SHA-256 **`0674b759576e8b06c14cb8e12daeea93bb9c9c001215494c3b8680e72cf22b0e`**. The same earlier CSI flag and zero final-snapshot errors were observed. The first wrapper attempt exposed GDB's literal handling of quoted dump filenames; using a selected output directory and a simple output filename resolved it before the successful test.

The debug server and serial monitor were stopped after verification. The board remains jumpered for development mode; a fresh capture requires loading the RAM test again.

## Proposed next experiment: startup timing breakdown

Source inspection after the capture found that the pinned middleware's `CMW_VD56G3_PowerOn()` (`Lib/Camera_Middleware/sensors/cmw_vd56g3.c`) requests a **200 ms delay with shutdown asserted, then 20 ms after release**. This test calls both `CMW_CAMERA_GetSensorName()` and `CMW_CAMERA_Init()`, each of which probes and initializes the sensor. Consequently it requests **440 ms of those fixed delays alone**, before configuration, diagnostic output and settling frames. This is a code-derived accounting of requested waits, not a measured minimum sensor startup time. Required reset/clock/rail timing must be established before shortening the waits.

The lower-level `VD6G_Init()` additionally requests 10 ms with shutdown asserted and 10 ms after release on each initialization. Together these two layers request **480 ms of fixed reset/initialization waits** across the duplicated startup. State polling adds further waits. The console uses blocking `HAL_UART_Transmit`; at 115200 baud, 8N1, 100 output bytes alone require approximately 8.7 ms on the wire. Neither the fixed waits nor logging should be mistaken for intrinsic sensor boot time.

Recommended first experiment, not yet implemented: record stage timestamps in RAM and print only after capture. Separate MCU startup/clock setup, camera reset and readiness, sensor configuration, receiver setup, stream command, first received frame start and first completed frame. Collect repeated runs and error counts. First measure the existing path; then compare changes individually, starting with the redundant probe and timing-path logging. Clock changes must be accounted for if using CPU cycle counts.

The current debugger load bypasses autonomous ROM-to-flash loading and starts with USB power already present. It cannot measure full cold-power startup or battery/rail rise. A received frame-start event is not itself a verified exposure-start timestamp. Final 50 ms qualification needs an external timing reference and a qualified sensor exposure indication or optical test, alongside the actual boot and power path. Follow-up experiments should test the first usable frame/manual settings, full-resolution RAW10 integrity, and repeated startup/link errors before battery/energy measurements.

## Available instruments and proposed external measurements

On October 15 the user confirmed owning a **Saleae Logic Pro 8** and **Joulescope JS110**. Windows detected the Logic Pro 8 during preparation. This records available equipment, not completed probe wiring or external measurements. The JS110 model was explicitly confirmed by the user; JS220 wiring assumptions do not apply.

Work through (1) external logic timing, (2) synchronized current/energy, then (3) autonomous cold-power startup. For the first step retain the working USB power and board jumper configuration, including development-mode JP2. The following accessible points are documented by [ST UM3417 Rev4, Tables 16, 19 and 20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf):

| Current Saleae connection | Nucleo point | Meaning |
|---|---|---|
| Ground | CN15 pin 20, or CN5 pin 6 or 7, GND | Common signal reference |
| Channel 0 | **CN3 pin 14, NRST** (same net as CN5 pin 3) | Verified MCU reset reference; not power-on or exposure start |
| Channel 1 | **CN15 pin 33, PD0** (also Arduino D2, CN13 pin 3) | GPIO wiring-test output; startup-stage instrumentation remains to implement |
| Channel 2 | **CN15 pin 29, PE0** (also Arduino D4, CN13 pin 5) | GPIO wiring-test output; frame/synchronization instrumentation remains to implement |
| Channel 3 | **CN3 pin 16, VDD3V3** (same net as CN5 pin 4) | Target auxiliary 3.3 V rail; capture analog voltage as well as logic level |
| Channel 4 | **CN3 pin 18, 5V** (same net as CN5 pin 5; also CN3 pin 6) | Target input supply downstream of CN9; physical input-power reference |
| Channel 5, temporary diagnostic | **CN3 pin 6, 5V** | Verified against target 5 V; duplicates CH4 for now. The earlier connection at CN15 pin 8 read zero and remains unexplained. |

**October 16 connector preference:** the user prefers accessible CN3/CN15 header connections. The initial reset recommendation was CN5 pin 3; its equivalent CN3 pin 14 was subsequently connected and verified. CN15 pins 33/29 expose the same PD0/PE0 marker signals previously assigned at CN13; the MCU pin selection is unchanged. CN15 pin 20 provides a convenient ground if the CN5 ground positions are occupied by JS110 leads. The mapping is also independently present in [ST-hosted UM3417 Rev3, Table 13](https://community.st.com/ysqtg83639/attachments/ysqtg83639/stm32-mcu-products-forum/292292/1/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics-12.pdf). Actual verification results are recorded below.

The user subsequently requested rail probes and easier alternatives to CN5. **CN3 pins 16 and 18** provide adjacent 3.3 V and target 5 V points; CN3 pin 20 is a nearby ground, although the existing CN15 ground can stay. CN15 pin 8 is instead `5V_STLK`, upstream of the target measurement/switch path, and CN15 pin 7 is `VREFP`; neither substitutes for the chosen rail points. [MB1940 C02 schematic, sheets 6, 9, 10 and 13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf).

`VDD3V3` is the target auxiliary rail generated by U34/ST1S31 from target 5 V and enabled by `PWR_ON`. It is distinct from debugger `3V3_STLK` and from the MCU's main VDDIO/AON supply. Its falling to zero alone does not establish complete MCU power removal. Use target 5 V rise to observe input-power arrival, and auxiliary 3.3 V rise to observe that downstream regulator starting. Both traces are useful; neither proves exposure has begun. The LP8 analog input supports these voltages directly; its approximately 5 mV resolution is sufficient for this wiring/startup check, not precision ripple characterization. [Saleae analog specifications](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/resolution-of-the-analog-inputs).

PD0 and PE0 are unused by the inspected capture application, main initialization and selected Nucleo camera support paths. Match header labels/pin 1 on the physical board before wiring. Arduino digital signals are 3.3 V; use the Logic Pro 8's 3.3 V threshold setting for this first group. Saleae's threshold is shared across channels, and all probe grounds are common with host USB ground: connect them to board GND, not to a supply or either end of a current shunt. See [thresholds](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/supported-voltages) and [ground connections](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/are-the-ground-pins-required-for-each-input-used).

**Moving signal probes:** unplugging board USB is not required merely to move an LP8 input between these known 3.3 V/5 V header signals while the common ground remains connected. The LP8 input is **2 MΩ in parallel with 10 pF**, and these voltages are within its normal input range. Earlier unplugging advice was a precaution against a probe clip bridging adjacent pins, not an electrical requirement of the analyzer. Keep the ground lead on board GND and avoid touching adjacent contacts. Changing CN9 jumpers or rewiring the JS110's current-carrying power connections is a different operation: power off before changing that supply path. [Saleae Logic Pro 8 datasheet, electrical characteristics and shared ground](https://downloads.saleae.com/specs/logic_pro_8_data_sheet.pdf).

The camera's reset/enable and I2C signals are on fine-pitch CN6 rather than the listed easy header points. A suitable breakout or verified pad is needed before adding those probes; do not probe the CSI differential lanes for this timing test. Firmware markers indicate software events and retain the exposure-timestamp limitations above.

The [JS110 user guide, section 12](https://download.joulescope.com/docs/JoulescopeUsersGuide/JoulescopeUsersGuide_v1_3.pdf) provides two GPI inputs recorded with current/voltage. Fan out a selected 3.3 V firmware marker to Saleae and **JS110 IN0**, with the JS110 GPIO reference configured for 3.3 V, to align traces. The JS110 digital I/O is referenced to host USB ground even though its measurement side is isolated. Enabling GPI uses one sample bit, leaving 13-bit current/voltage samples instead of 14; retain that setting with results. Keep GPO outputs disconnected for the initial measurement.

The JS110 must measure current in series with the selected positive supply path; its USB host connection does not power the target. Exact source/adapter wiring remains to settle. An initial whole-board USB-input measurement can include ST-Link/LED/regulator overhead and is useful for comparisons if labeled accordingly. Target-only energy requires a separately verified supply boundary with no bypass feed; CN9 alone does not remove the debugger supply branch through D2, and CN12 shunt pairs are not ready-made series ammeter inputs. See the [debugger/power isolation study](../../docs/power/nucleo-debug-isolation.md). No PCB rework or supply injection is prescribed here. Final main-path OFF-current qualification must account for instrument/probe loading and the separate RTC budget.

### Reset timing versus actual power-up

**October 16 hookup recommendation:** insert the JS110 in place of CN9's STLK 1–2 shunt: IN+ to pin 1 (`5V_STLK`), OUT+ to pin 2 (target `5V`), with IN−/OUT− at board GND. The [detailed wiring and boundary](../../docs/power/nucleo-debug-isolation.md#reversible-js110-insertion--october-16) preserves CN10 USB power/debugging and leaves other supplies disconnected. This is not a fully isolated target-current or cold-start qualification setup until residual power and debugger branch loading are checked. No physical hookup or successful measurement is yet recorded.

The user asked whether power-up could be controlled rather than measuring everything from reset. The **JS110 can disconnect its DUT supply by selecting current range `off`**, then restore the measurement/current path. This provides a route to real, scriptable power cycles once the board's entire intended supply passes through it and alternate USB/debug feeds have been excluded. [JS110 guide, section 9.3](https://download.joulescope.com/docs/JoulescopeUsersGuide/JoulescopeUsersGuide_v1_1.pdf); [manufacturer's Python clarification](https://forum.joulescope.com/t/using-js-to-measure-battery-capacity/879) identifies `i_range=off` rather than `sensor_power=off`. No power cycle or rewiring has yet been performed. Verify actual target rail discharge; opening the source alone does not guarantee capacitors or powered signal paths have let the MCU/camera lose power.

The current capture script uses `monitor reset`, downloads the ELF to SRAM and explicitly sets SP/PC before running. It does not power-cycle the rails, and reset-to-capture includes debugger operations rather than an autonomous boot path. For current software profiling, use firmware markers after execution begins; record NRST as context only. True power removal loses this RAM-loaded program. End-to-end startup testing first requires a bootable image in onboard external NOR and the appropriate normal boot configuration, then execution without debugger download/halt intervention.

Use the measured **target supply rise** as the physical power-on timing reference, not the PC's USB command-send timestamp. JS110 voltage sensing is at its input side on the standard front panel, so monitor the switched target supply separately, for example with a Saleae analog input, as appropriate to the selected wiring. Software reset or Standby wake does not substitute for full main/AON/camera power removal. A switched 5 V Nucleo test establishes board startup; the final button-to-exposure requirement additionally includes the four-cell/LTC3621 power stage and latch, plus an independently qualified exposure-start indication.

### GPIO wiring smoke test

The capture firmware now has an optional GPIO-only test. Its default behavior remains the camera capture above. `probe_smoke.ps1` loads the same ELF into SRAM, reaches `app_run` after startup has cleared BSS, and selects `g_probe_smoke_mode = 1`. This bypasses camera initialization and emits four nominal 50 ms PD0 pulses, three nominal 100 ms PE0 pulses, then a 200 ms pulse on both outputs. Both finish low. `probe_smoke_complete` is a stable debugger breakpoint; the wrapper checks completion and returns the MCU to development ROM. No flash or OTP is programmed.

Record physical NRST and the GPIOs while running the wrapper. Its initial `monitor reset hardware` deliberately exercises the reset lead. This confirms connections by a recognizable pattern; debugger load/reset intervals are not startup performance measurements. The normal camera path does not yet emit startup/frame markers.

Install the Saleae client locally, then start the installed Logic application with its documented `--automation` flag (default port 10430). This launch option avoids changing its persistent preferences. [Saleae launch documentation](https://docs.saleae.com/automation/guides/launching-logic2).

```powershell
python -m pip install --target tmp/bringup/saleae-deps logic2-automation==1.0.11
```

With the ST-Link GDB server running as above, record all five wired channels and start the stimulus only after the analyzer has begun recording:

```powershell
python firmware/bringup/probe_capture.py --capture --duration 15 `
  --digital 0,1,2,3,4 --analog 0,1,2,3,4 `
  --output tmp/bringup/probe-test-new `
  --stimulus-command pwsh -NoProfile -File firmware/bringup/probe_smoke.ps1 `
  -GdbExe "<absolute path to arm-none-eabi-gdb.exe>"
```

The output directory must be new. `--stimulus-command` must be last; all following arguments belong to that process. The analyzer uses the shared 3.3 V logic threshold, **6.25 MS/s digital** and **31.25 kS/s analog**, a combination accepted by the physical LP8 with Logic 2.4.46. Logic rejected the initially proposed 10 MS/s / 125 kS/s combination; supported rates must be selected together. Saved `.sal`, CSV, stimulus logs and `probe-summary.json` stay under ignored `tmp/bringup`. Offline checking is available with `--analyze <capture directory>`.

The checker verifies the reset transition, distinct marker pulse counts/order and broad pulse-width tolerances. It checks stable marker levels away from edges and reports the optional rail voltages. A successful GPIO test does not by itself qualify cold-start timing, exposure timing, current measurement, or complete rail isolation.

### First LP8 smoke-test attempt — October 16, 2026

The user confirmed connecting the existing reset/marker probes, then CH3 to CN3 pin 16 and CH4 to CN3 pin 18 and reconnecting board USB. Logic 2.4.46's automation API detected the physical Logic Pro 8 and successfully saved a roughly two-second passive recording of digital and analog channels 0–4. The first attempted rate combination was rejected before any stimulus; the accepted rates are recorded above.

| Check | Observed result |
|---|---|
| CH0 NRST | Approximately 0 V, no transitions |
| CH1 PD0 / CH2 PE0 | Approximately 0 V, no transitions |
| CH3 auxiliary 3.3 V / CH4 target 5 V | Approximately 0 V; median readings −13 mV / −17 mV, consistent with analyzer offset near zero |
| ST-Link target-voltage reading | **0.00 V**, unable to identify the MCU |
| JS110 GUI | Device connected, current range **auto**, voltage range 15 V; displayed current and voltage approximately zero |

**Result: analyzer acquisition works; the target is unpowered and GPIO/reset wiring is not yet verified.** No test firmware could be loaded, so no GPIO pattern or cold-start timing was measured. ST-Link's independent voltage reading corroborates the lack of target power; the all-zero analyzer traces alone would not establish correct probe wiring. CN9 jumper/JS110 physical path confirmation is pending. The JS110 GUI owns the instrument, preventing direct API access; only its device panel was inspected, with no power/range setting changed. Its standard front-panel voltmeter senses **IN+ to IN−**, so its near-zero display is also evidence to check the incoming source/reference wiring, not merely its output switch. [JS110 User Guide v1.3, §10.2](https://download.joulescope.com/docs/JoulescopeUsersGuide/JoulescopeUsersGuide_v1_3.pdf).

The passive `.sal`, CSV and analysis are local in `tmp/bringup/probe-static-02`. The optional GPIO firmware built without new warnings and passed the existing persistent-write symbol check. The analyzer checker passed synthetic expected-pattern, swapped-lead, missing-reset, overlapping-reset and voltage-failure cases; those software checks do not substitute for the pending physical pulse test. After target power is restored, run the coordinated capture above and verify the normal camera capture still completes using the new named breakpoint.

The user then confirmed the **JS110 is physically inserted in place of the CN9 jumper**. A fresh passive capture (`tmp/bringup/probe-static-03`) still showed both target rails near zero; ST-Link reported 0.19 V at its separate target-voltage reference and could not identify the MCU. The JS110's displayed input voltage remained approximately zero (about −1.3 mV in the inspected waveform), with its power control enabled. These readings do not identify which connection is responsible and do not prove zero voltage on every MCU rail.

The next requested diagnostic is one added analog probe: **Saleae CH5 to CN15 pin 8, `5V_STLK`**, retaining the existing board-ground connection. This is the source net at CN9 pin 1, after the ST-Link-controlled USB power switch but before the JS110. Compare it with CH4 at CN3 pin 18, the target supply after the JS110. A healthy source with a missing target supply directs attention to the meter path/connections; a missing source directs attention to USB input and its onboard power switch. Do not substitute this upstream point for the target-power reference in later startup measurements. [UM3417, ST morpho pin assignment](https://www.st.com/resource/en/user_manual/dm01122391-.pdf). Physical connection and measurement of CH5 remain pending.

### Powered GPIO test — October 16, 2026

After the user confirmed adding CH5 at CN15 pin 8 and reconnecting USB, target power was restored. ST-Link read **3.28 V** and identified the MCU. The reason the earlier supply was absent is not yet established. The connected LP8 had moved to a user-started Logic instance; its existing live capture was stopped and retained in Session 0. Only the task-launched duplicate Logic process was closed. The connected instance's already-enabled automation control was cycled off/on to recover its port after the duplicate released it; the user instance and its existing capture were preserved.

The passive six-channel recording `tmp/bringup/probe-static-04` measured approximately 3.28 V on CH3 and 4.81 V on CH4. The subsequent coordinated recording `tmp/bringup/probe-smoke-05` ran the SRAM GPIO firmware successfully (`g_probe_smoke_done = 1`), with these independent results:

| Probe | Actual result |
|---|---|
| CH1 / PD0 / CN15 pin 33 | **Passed**: four highs of 50.335–50.375 ms, then the joint pulse; stable low/high medians −0.015 V / 3.282 V |
| CH2 / PE0 / CN15 pin 29 | **Passed**: three highs of 100.624–100.739 ms, then the joint pulse; stable low/high medians −0.022 V / 3.278 V |
| Joint PD0/PE0 pulse | 201.408 ms on both, with edges aligned within one 160 ns digital sample |
| CH3 / CN3 pin 16 | Auxiliary 3.3 V rail median **3.283 V** |
| CH4 / CN3 pin 18 | Target 5 V rail median **4.801 V** |
| CH0 / intended NRST | **Not verified**: remained near zero (median 0.041 V), despite GDB reporting a successful hardware reset and the firmware executing |
| CH5 / intended CN15 pin 8 source | **Not verified**: remained near zero (median −0.024 V), despite the powered target |

No stable GPIO samples were outside the test's expected voltage ranges. The checker now reports GPIO and reset success independently, so a missing reset signal does not hide valid marker patterns or their voltage measurements. The overall wiring test correctly remains failed until reset is verified. The source-probe discrepancy needs separate investigation; do not infer the physical supply path from the powered target alone. Rail values were steady-state measurements; **no power-on transition or cold-start latency was captured**.

The normal camera path was then re-tested using the new named `capture_complete` breakpoint: four completed frames/four vsync events, approximately 804 ms for the diagnostic sequence, and zero final-snapshot errors. The earlier CSI control-error flag `0x8000` appeared once as before. The downloaded 307,200-byte frame's host-calculated sum **6,416,255** and FNV-1a **`0x207319e4`** matched firmware; pixel minimum/maximum were 15/155, SHA-256 `2c6ec357cd5631d524ab6e510190b4d39f1a8a46b23032f20af26cb565aaf1d8`. Image data remains local under `tmp/bringup/capture-after-probes`.

Next physical check, requested one item at a time: move **only CH0 to CN3 pin 14 (NRST)**, equivalent to CN5 pin 3, with USB disconnected while moving the lead. Reconnect and repeat the reset/GPIO test; then address the source probe. The debugger server was stopped and the MCU left in development ROM before requesting that move.

### Completed reset/marker verification — October 16, 2026

The user moved CH0 to CN3 pin 14. The next coordinated capture, `tmp/bringup/probe-smoke-06`, **passed both reset and GPIO checks**, with no stable marker-voltage warnings. NRST idled at a median **3.192 V** and showed an initial hardware-reset low pulse of approximately **725 µs**, followed by the correct GPIO pattern and a roughly **219 µs** cleanup-reset pulse. PD0/PE0 high medians were 3.287 V / 3.278 V; target rail medians were 3.288 V / 4.801 V. The pulse timings verify the stimulus and connections, not autonomous boot latency. No power-on transition was measured.

CH5 still read near zero at the intended CN15 pin 8 connection. To separate the lead/input from that connection, the user moved CH5 to the known target **5 V at CN3 pin 6**, keeping the board powered. A passive capture, `tmp/bringup/probe-static-07`, then measured **4.793 V on CH5**, alongside 4.806 V on CH4 and 3.293 V on CH3. This verifies CH5's lead/input as well. The passive recording intentionally contains no stimulus; the checker reports absent reset/GPIO patterns for that file, which is expected and does not invalidate capture 06's successful active test.

**Current result:** NRST, PD0, PE0, auxiliary 3.3 V and target 5 V probe connections are verified. CH5 temporarily duplicates target 5 V at CN3 pin 6. The earlier zero reading at the intended CN15 pin 8 source connection remains unresolved; establish that source connection and the actual meter supply path before claiming supply isolation or interpreting a JS110 power-cycle test. The previous unpowered condition's cause was not identified. The test firmware has been reset back to development ROM and the task's debugger server stopped. The user-owned Logic and Joulescope applications remain open.

The user correctly questioned the repeated USB-unplug instructions for signal-probe moves. Those were an adjacent-pin short precaution, not an electrical requirement of the LP8; use the powered-probe guidance above for these known low-voltage signal points. Power-path rewiring remains a separate operation.
