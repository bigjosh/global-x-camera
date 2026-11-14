# Guided camera firmware installer — r2 v1

This installs the calibrated exposure/ASA firmware from `knobs-2026-11-14-r2`
on the assembled Global X Camera NUCLEO-N657X0-Q prototype. **It uses the
existing UART recovery boot path; no access to the boot jumpers is needed.**
The firmware and three RAM flash helpers are included. No project checkout,
compiler, CubeIDE, Joulescope or external flash loader is required.

**Status:** offline checks and simulated failure-path tests only. The individual
flash helpers and UART sequence have prior Windows bench evidence, but this
portable installer, macOS serial behavior and complete r2 image still need
hardware testing. Preparing or publishing this bundle did not access a board.

## First time on a Mac

1. Download and extract this installer's ZIP from the
   [r2 release](https://github.com/bigjosh/global-x-camera/releases/tag/knobs-2026-11-14-r2).
   Compare its SHA-256 with the value on that release page. Use the installer
   asset, not GitHub's automatic Source code archive.
2. Install **Python 3.10 or newer** using the normal
   [Python macOS installer](https://www.python.org/downloads/macos/) if it is not
   already installed. The launcher checks common Python.org and Homebrew paths.
3. Install **STM32CubeProgrammer 2.23.0** from
   [ST](https://www.st.com/en/development-tools/stm32cubeprog.html): **MacOS Arm**
   (`STM32CubePrg-McA`) for M-series Macs, **MacOS Intel** (`STM32CubePrg-Mac`)
   for Intel Macs. About This Mac shows which processor you have. Unzip and run
   ST's setup app. Java is bundled. ST may request an account/email to download;
   macOS may request administrator permission for ST's installer. Do not start
   a programming session in CubeProgrammer's GUI; our utility uses its CLI.
4. Double-click **`Install.command`** in the extracted folder. If Finder does
   not launch it, open Terminal, type `bash ` (with a trailing space), drag
   `Install.command` into that window, then press Return. Keep the whole
   extracted folder together.

The launcher creates a private `.venv` inside this folder and installs the
small `pyserial==3.5` dependency there. It does not change system Python. The
first launch needs internet access for that dependency. The Python utility
finds CubeProgrammer in its usual installation locations; if needed it asks
you to select/paste its installed application path.

## What the utility will ask you to do

It first explains the two USB connections:

| Camera port | Connection and purpose |
|---|---|
| **CN10 / ST-LINK**, debugger end | Data-capable USB cable to this Mac; firmware download/debugging |
| **CN8 / HOST / MCU USB**, beside Ethernet | Second data-capable USB cable to this Mac or powered hub; supplies target power through the camera's selector and later carries photos |

Finish any capture/save/download and close other camera, serial-monitor and
debugger applications. Leave the current boot jumpers untouched and this
modified prototype's CN9 source jumpers removed. Use the existing physical
power selector, not a new connection between supply rails.

The utility says to leave the selector on **BATTERY**, without pressing the
shutter, and press Enter when the cables are connected. It then starts the
recovery signal and says:

> OK, now switch the camera's power switch to USB.
> I am sending the recovery signal and will detect the camera when it starts.

Keep the switch on **USB**, both cables attached and the Mac awake until the
utility reports completion. It recognizes the MCU's verified recovery state;
it does not electrically measure the mechanical switch. It waits up to two
minutes, with a waiting message if needed. It never interprets an elapsed delay
alone as permission to program.

Progress describes actual completed stages: recovery, backups, USB-section
write, boot-section write, independent readback, and recovery recheck. The
percentages indicate overall stages, not an estimated network transfer rate;
reported flash page counts come from the running programmer. At completion it
releases normal startup and tells you where it saved the logs and backup.

With HOST connected and the selector on USB, expect photo-access mode. It is
PTP, not a mounted disk; do not format the SD card. macOS Image Capture is a
reasonable app to try, but Mac PTP operation is not yet qualified. To take a
photo later, finish transfers, unplug HOST, select battery and press the shutter.

## What it checks and preserves

- Independently pinned r2 sector hashes, helper binaries/manifests and known
  recovery prefixes before device access. Unknown firmware is refused.
- ST-LINK serial-port VID/PID **0483:3754** and the same full serial used for
  SWD, with macOS `/dev/cu.*` selected instead of a duplicate `/dev/tty.*` alias.
- The exact early UART guard status, qualified pulse evidence, full live
  prefix, halted PC, CPU/cache state and clocked/idle XSPI before loading helpers.
- Backups of both 64 KiB NOR regions and the following 4 KiB, with the existing
  pair matched to the recognized image. Current admitted pairs are the November
  13 D8 fixed-settings image and this r2 controls image.
- **Sector1 first, sector0 second**, using the three unchanged ROM-context RAM
  helpers. These fixed-window writers check current/input CRCs and safe fresh
  completion; they do not reinitialize the board through ST's external loader.
- Full independent post-write rereads and preservation of the following 4 KiB.
  SD photos are never formatted or deleted by the installer.
- Post-install UART recovery with the exact r2 prefix, followed by normal reset.
  These last reset steps use the previously observed ST-LINK BREAK-to-NRST
  behavior; that behavior still needs confirmation on the Mac host path.

This is an updater for firmware that already has our working recovery guard.
It cannot rescue an erased/damaged boot guard or unknown firmware without a
different hardware recovery route. Never remove power during flash programming.

## If it stops

Read the displayed reason. Before flash work begins, missing cables, tools or
an unrecognized recovery response cause a stop without writing firmware.
Check the stated issue before restarting the utility.

If it reports an unresolved programming/verification session, **leave power
and cables unchanged**. Do not reset, rerun, power-cycle or delete the safety
record. Preserve the logs and seek help interpreting completion first. A host
timeout does not prove the MCU stopped writing. The utility never automatically
retries a failed flash operation. A successful flash write followed by a failed
recovery recheck is recorded distinctly in the log; do not treat it as proof the
download itself failed and blindly write again.

Logs/backups normally go to `~/global-x-camera-installs/<timestamp>/`. A persistent
per-ST-LINK record under `~/.global-x-camera/installer/` blocks a new installation
after an uncertain interruption. Removing it requires an informed review of the
actual target state, not simply waiting and assuming completion.

## For a user's AI or an experienced terminal user

The default `python3 camera_install.py` launches the same interactive guide.
`python3 camera_install.py --check` validates the included files entirely
offline and does not enumerate instruments or open a serial port.

For an already powered, idle, **USB-selected** camera, this explicitly
acknowledged alternative requests recovery using the existing UART/BREAK
reset sequence rather than waiting for a switch transition:

```sh
.venv/bin/python camera_install.py --non-interactive --confirm-idle --restart
```

Only use that after the operator establishes no capture, SD save, host photo
transfer or previous flash operation is active. Without `--restart`, the utility
arms the serial signal and waits for the operator to switch to USB. `--serial`
selects one probe when multiple are attached; `--port` still must match that
probe. `--cubeprogrammer` accepts the installed CLI or `.app` path. `--output`
must name a new log directory. Run `--help` for the options. Do not invoke ST's
stock external loader from our normal-boot recovery park.

Offline developer checks use `python3 -m unittest discover -s . -p 'test_*.py'`.
Build a new ZIP with `python3 build_bundle.py <new-output.zip>`; this never
publishes or accesses hardware. Shipped ZIP checksums cover the included files;
the executable firmware/helper identities are additionally pinned in the code.

Sources: [ST Mac installation](https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_How_To_Start/CubeProg_Installation.html#macos-install),
[ST CLI documentation](https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html).
Prior helper provenance is in `assets/PROVENANCE.json`; the original build
manifests/disassemblies are preserved beside each binary. Absolute paths in
those historical manifests describe the original build, not install requirements.
