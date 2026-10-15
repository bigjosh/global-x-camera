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

The debugger's success breakpoint is tied to line 292 of the preserved `capture_app.c`. If that source is edited, keep the breakpoint aligned with the final buffer-frozen loop before rerunning the wrapper.

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
