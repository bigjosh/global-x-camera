# Knob control firmware: exposure and gain (2026-11-14)

**Pre-release. This firmware has never run on a camera.** It was built and checked offline only: compiled, compared byte for byte against the installed firmware, and exercised with host-side tests (50 of the 50 that can run on Linux passing). Installing it is the first hardware test. The firmware it replaces is kept in the repository so you can go back (see [Going back](#going-back)).

This page is written so that someone, or another Claude session, who has not seen the work can install it. Read it to the end before touching the board.

## What changes for the person using the camera

| Knob | Wiring (unchanged) | Effect |
|---|---|---|
| Exposure | A0 low end, A1 wiper, A2 high end | Exposure time from **0.5 ms to 484 ms**. Equal turns give equal ratios (about 10 stops end to end); mid-travel is about 16 ms, near the old fixed 11 ms. |
| Gain ("ASA") | A4 high end, GND low end, A5 wiper | Sensor analog gain from **1x to 8x** in equal stops. Digital gain stays 1x. |

- Both knobs are read once, at the start of each photo. Turning a knob during a photo affects the next photo.
- The knobs are read only on the normal photo path (no cable in the camera's "USB" port). Photo download over USB is unchanged.
- Higher ADC reading means longer exposure or more gain. If a knob feels backwards, swap its two end wires; nothing in firmware needs to change.
- If the knob reading fails for any reason, the camera takes the photo with the old fixed settings (11 ms, 1x) instead of failing.
- The chosen exposure and gain are **not** stored with the photo. The photo format has no field for them yet.

## Which USB-C port

The board has two USB-C sockets. **Program through CN10, the ST-LINK socket on the top edge.** Do not use CN8.

![Top view of the Nucleo board. CN10, the ST-LINK USB-C socket on the top edge right of centre, is marked "program here". CN8, the USB-C socket marked "USB" on the bottom edge between the blue button and the Ethernet jack, is marked "not this one".](https://github.com/bigjosh/global-x-camera/releases/download/knobs-2026-11-14/nucleo-usb-ports.png)

The same drawing as text, board seen from the component side with the Ethernet jack toward you:

```
                      TOP EDGE
   +--------------------------[ CN10 ]----(o)(o)-----+
   |                           ^^^^^^     LD4 LD9    |
   | [CN1 debug]   [ST-LINK   PROGRAM HERE           |
   |               chip]      "ST-LINK" USB-C        |
   |                                                 |
   |        JP1 JP2  (boot jumpers, both on 1-2)     |
   | CN3 CN5                             CN14  CN15  |
   |  |   | 5V in pin 5                  D8=HOLD  |  |
   |  |   | GND   pin 6                    |      |  |
   |  |  CN4            [STM32N6]        CN13     |  |
   |  |   | A0..A5 = both knobs            |      |  |
   |                                                 |
   |      [== CN6 camera ribbon ==]         o LD5 red|
   |                                        o LD6 grn|
   |                                        o LD7 blu|
   |                              +----------+       |
   | (B1 blue)     [ CN8 ]        | Ethernet |  (B2  |
   |  USER          "USB"         |   RJ45   | RESET)|
   +----------------[     ]-------+----------+-------+
                     ^^^^^            BOTTOM EDGE
                 NOT THIS ONE
       photo download only; unplug it for
       programming and whenever you take a photo
```

How to tell them apart without the drawing:

- **CN10 (use this)** is alone on the short edge that has no buttons. Two small status LEDs (LD4, LD9) sit beside it and light when its cable is connected to a PC. It is the board's built-in ST-LINK programmer and serial port.
- **CN8 (do not use)** is on the opposite short edge, between the blue USER button and the metal Ethernet jack, with "USB" printed next to it. It is the camera's own USB port for downloading photos. If it is connected when the camera starts, the camera goes into download mode and does not take a photo, so leave it unplugged for everything on this page.

CN10 does not power the camera on this modified board (the CN9 jumpers and D2 are removed). The camera needs its own 5 V on CN5 pin 5, ground on CN5 pin 6, exactly as for the November 13 install.

## What is in this release

| File | What it is | SHA-256 |
|---|---|---|
| `sector0.bin` | 64 KiB image for NOR flash offset `0x00000` (boot prefix and capture code) | `06196d10e8ddeb50948ef3666729dbe390d575b58a0c1d2ee7f5796758ece6ad` |
| `sector1.bin` | 64 KiB image for NOR flash offset `0x10000` (boot selector with the knob reader, and the USB download app) | `ac1854200e78dfb04f0554b3555ccb794de1e0e2f6ddc587ee3358b3031e9736` |
| `manifest.json` | Build record: hashes, addresses, compiler, the exact bytes changed | |
| `SHA256SUMS` | Hashes of every file in the build folder | |
| `nucleo-usb-ports.png` | The drawing above | |

The same files, plus the recovery metadata the install scripts need, are in the repository at this tag under `firmware/usb-ptp/evidence/2026-11-14-knobs/package/`. **Use that folder for the install**; the loose release files are for checking hashes. Boot prefix: 7160 bytes, SHA-256 `0f87fbbe521230349db3d19b9449db38f2bff8000a4683461db080ad5525acc9`.

The firmware now on the camera (installed November 13) is in `firmware/usb-ptp/evidence/2026-11-13-d8-hold/package/`: sector 0 `1a9278ab1733134a86e382af61b3a78627fe40d82e9e137dd33f2bfcf8de1197`, sector 1 `ed6d416974bf0801f1b1daa6e29520db06fa3294bb33060a9dfbc48b761fbc38`.

## What the install needs

The install uses the project's own scripts, which were written for the owner's Windows bench PC. It has only ever been done from that PC.

1. **That PC and that board.** The scripts look for the ST-LINK with serial number `002100203335511035383531` and stop if it is absent.
2. **The repository checked out at this release's tag**, with the commands below run from the repository root.
3. **The local `tmp/` folder from earlier installs.** It is not in Git. The scripts expect these inside it:

   | Needed | Path the scripts use | Committed copy, if `tmp/` lacks it |
   |---|---|---|
   | STM32CubeProgrammer CLI **2.23.0** | `tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe` | none; install with `cube bundle --yes install programmer` (see `firmware/bringup/README.md`). Version 2.17 does not support this MCU. |
   | pyserial | `tmp/bringup/vcp-deps` | none; `pip install pyserial --target tmp/bringup/vcp-deps` |
   | Recovery sender | `tmp/bringup/sd125-negedge-20261026/uart_recover.py` | `docs/power/evidence/2026-10-28-isolated-nucleo/support/uart_recover.py` (byte-identical) |
   | Flash read helper | `tmp/bringup/rom-nor-maintenance-readonly-20261017/` (path is fixed inside `nor.py`) | `firmware/boot-timing/evidence/nor-programmer-20261017/builds/rom-nor-maintenance-readonly-20261017/`; copy the folder to the `tmp/` path |
   | Sector 0 writer | `tmp/bringup/rom-nor-programmer-v2-20261024/` | `firmware/capture-sd/evidence/2026-10-24-normal-profile/nor-maintenance/helpers/programmer-v2/build/`; pass it as `--build` |
   | Sector 1 writer | `tmp/bringup/usb-ptp-20261108/nor-sector1/` | **none.** It exists only on the bench PC. If it is missing, stop and ask the owner; a rebuilt copy is not the qualified one. |

4. **Python 3** with the standard library.

If you are a Claude session: you need shell access on that Windows PC, in that checkout. A cloud session cannot do this install. Read `AGENTS.md` first; it holds the bench rules and the live bench state, and it wins over this page wherever they differ.

## Before you start

- [ ] The owner knows you are about to program the camera and nobody else is using the bench, the ST-LINK or its COM port. Close STM32CubeProgrammer, CubeIDE and any serial terminal.
- [ ] 5 V is stable on CN5 pin 5 with ground on CN5 pin 6. On November 13 this was a direct 5 V supply with the battery latch bypassed. Do not program from the battery through the latch: nothing guarantees the latch stays on through a reset.
- [ ] JP1 and JP2 are both on pins 1-2.
- [ ] A USB-C cable runs from **CN10** to the PC. **CN8 is unplugged.**
- [ ] The camera is idle: no photo is being taken or saved.
- [ ] Hashes of `sector0.bin` and `sector1.bin` in the package folder match the table above (`Get-FileHash -Algorithm SHA256 <file>`).

Three rules that must not be broken:

1. **Never reset, halt or cut power while flash or SD card activity may be in progress.**
2. **If a step fails, stop.** Do not improvise a different way of writing flash. See [If something goes wrong](#if-something-goes-wrong).
3. **Each output folder must be new.** The scripts refuse to overwrite.

## Install

PowerShell, from the repository root. Each step says what success looks like; do not go on without it.

```powershell
$new = "firmware/usb-ptp/evidence/2026-11-14-knobs/package"
$old = "firmware/usb-ptp/evidence/2026-11-13-d8-hold/package"
$out = "tmp/bringup/knobs-20261114"        # any folder that does not exist yet
New-Item -ItemType Directory $out | Out-Null
```

**1. Put the camera in its recovery park.** This resets the camera through the ST-LINK and sends the recovery signal during the first 100 microseconds of boot, so the firmware stops before it touches the sensor, the SD card or flash.

```powershell
python tmp/bringup/sd125-negedge-20261026/uart_recover.py $out/programming-uart
```

Success: it prints `opened`, `break_on`, `break_off`, `stimulus_complete`, `closed` and exits without an error.

**2. Prove the camera is parked, and that it is running the firmware you think it is.**

```powershell
python firmware/usb-ptp/recovery.py --package $old --out $out/programming-park
```

Success: `$out/programming-park/result.json` contains `"passed": true`. If it does not, the recovery signal was missed or the installed firmware is not the November 13 package. Stop and read [If something goes wrong](#if-something-goes-wrong).

**3. Back up both flash regions.** `--expect` makes the script fail unless the flash holds exactly the November 13 firmware.

```powershell
python firmware/usb-ptp/nor.py read --offset 0     --out $out/backup0 --expect $old/sector0.bin
python firmware/usb-ptp/nor.py read --offset 65536 --out $out/backup1 --expect $old/sector1.bin
```

Success: each prints `Independent NOR read complete <offset> 65536 True`. Each folder now holds `readback.bin`, your backup.

**4. Write sector 1** (the selector and USB app). Sector 1 goes first: until sector 0 is written, the old boot code checks the selector's checksum, finds it changed and parks in an idle loop rather than running a mismatched pair.

```powershell
python firmware/usb-ptp/nor.py write --offset 65536 --build tmp/bringup/usb-ptp-20261108/nor-sector1 --out $out/write1 --current $out/backup1/readback.bin --desired $new/sector1.bin
```

**5. Write sector 0** (the boot prefix and capture code).

```powershell
python firmware/usb-ptp/nor.py write --offset 0 --build tmp/bringup/rom-nor-programmer-v2-20261024 --out $out/write0 --current $out/backup0/readback.bin --desired $new/sector0.bin
```

Success for 4 and 5: the script exits without an error after comparing the whole 64 KiB region. The writer checks the current contents before erasing anything, erases only the 4 KiB blocks that differ (two in sector 1, two in sector 0) and never resets the camera.

**6. Read both regions back independently.**

```powershell
python firmware/usb-ptp/nor.py read --offset 0     --out $out/verify0 --expect $new/sector0.bin
python firmware/usb-ptp/nor.py read --offset 65536 --out $out/verify1 --expect $new/sector1.bin
```

Success: both end in `True`. The flash now holds this release.

**7. Start the new firmware.** This is a reset, not a power cycle.

```powershell
python firmware/usb-ptp/reset.py --out $out/activate-normal
```

Success: prints `Normal powered reset released; no power cycle.` With CN8 unplugged the camera now takes one photo straight away, using the knob positions, and goes to sleep.

**8. Recommended: prove recovery still works with the new firmware**, so the next install is possible. Wait for the photo from step 7 to finish (LEDs off), then:

```powershell
python tmp/bringup/sd125-negedge-20261026/uart_recover.py $out/post-uart
python firmware/usb-ptp/recovery.py --package $new --out $out/post-park
python firmware/usb-ptp/reset.py --out $out/post-normal
```

Success: `$out/post-park/result.json` has `"passed": true`. The last command lets the camera run again.

Afterwards, record what you did in the repository the way earlier installs did (`firmware/usb-ptp/evidence/2026-11-13-d8-hold/hardware/` is the model) and update the bench state in `AGENTS.md`.

## Check that it works

A normal photo shows red (start), blue (capturing), green (saving), then all LEDs off. That sequence is unchanged.

1. **One photo, both knobs near the middle.** Expect the normal LED sequence. This alone shows the knob reader, the prefix edit and the capture change work together.
2. **Exposure knob.** Same scene, gain at minimum, photos at the low end, the middle and the high end. Download them (connect CN8, restart the camera, open **This PC → Global X RAW Camera**). Brightness should rise with the knob: the image should go from nearly black to washed out across the full travel in ordinary room light.
3. **Gain knob.** Same scene, exposure fixed mid-travel, gain at both ends. The high end should be about 8 times brighter (3 stops) and noisier.
4. **Exact exposure, if a logic probe is available.** PD0 (CN15 pin 33) mirrors the sensor's exposure strobe, so its pulse width is the exposure. Expect about 0.5 ms at one end of the exposure knob and about 484 ms at the other.

What a failure looks like, and what it means:

| What you see | Likely cause | What to do |
|---|---|---|
| 3 red flashes, five times | Capture failed. At the extremes of the exposure knob this would mean that exposure length does not work with the unchanged capture code. | Try mid-travel. Report which positions fail. |
| 2 red flashes, five times | Sensor start failed. Could be a gain or frame-length value the sensor rejects. | Try both knobs at minimum, then mid-travel. Report. |
| 8 red flashes, five times, or no LEDs at all | Loader or internal failure. | [Go back](#going-back). |
| Photos never change with the knobs, but are normal | Knob reading failed and the firmware fell back to the fixed settings. | Check the knob wiring. A debugger can read the reason (below). |
| Photos are black at every exposure setting | Exposure wiper open: an unconnected wiper reads as the shortest exposure. | Check the A1 wire. |

For a debugger: after the selector has run, the word at `0x343F9028` is the knob result (0 applied; 1 converter busy; 2 pin bank set for 1.8 V; 3 analog supply not ready; 4 or 5 converter setup; 6 conversion; 7 capture prefix not the expected bytes; 8 write did not read back; 9 memory protection on; all ones: knobs not read on this boot) and the word at `0x343F9024` points to a 32-word record laid out by the `K_…` names at the top of `firmware/usb-ptp/knob.c` (both raw readings of each knob, the chosen lines, frame length and gain code). These are only readable while the camera is awake.

## If something goes wrong

- **Step 1 or 2 fails (recovery missed).** Nothing has been written. Run step 1 and 2 again with new output folders; a few attempts can be needed. If the programmer reports `DEV_USB_COMM_ERR`, run `python firmware/boot-timing/stlink_recover.py --execute` once, then retry.
- **Step 3 fails its `--expect`.** The flash does not hold the November 13 firmware. Nothing has been written. Stop and ask the owner what is installed.
- **Step 4 or 5 fails or times out.** Leave the camera powered and do not reset it. Read the region again with `nor.py read` (no `--expect`) into a new folder, then run the same write again with `--current` pointing at that fresh `readback.bin`. The writer only proceeds if `--current` matches what is really in flash.
- **Sector 1 is written, sector 0 is not, and you must stop.** The camera will not take photos in this state: the old boot code parks at the selector checksum with the power latch held on, which would drain a battery. Recovery still works because it runs earlier in boot. Either finish step 5 or [go back](#going-back).
- **The camera no longer enters the recovery park at all.** Last resort, used once on October 20: move JP2 to pins 2-3 (development boot), power-cycle the camera, and write sector 0 with the standard external loader as recorded in `firmware/capture-timing/evidence/2026-10-20-vcp-sd-smoke/programming/write-request.json`. Ask the owner first.

### Going back

To restore the November 13 firmware, repeat steps 1 to 7 with the roles swapped: in step 2 use `--package $new`; in step 3 `--expect` the `$new` files; in steps 4 and 5 use `--desired $old/sector1.bin` and `--desired $old/sector0.bin`; in step 6 `--expect` the `$old` files. Use new output folders.

## What has and has not been checked

Checked offline:

- The build is reproducible: two independent builds give identical flash images.
- Against the installed firmware, sector 0 differs only in the 440-byte boot hook and five bytes of capture code; the hook is instruction-for-instruction the same logic. Everything before the hook, including the recovery guard, is byte-identical.
- In sector 1 the USB download app is byte-identical; only the selector in front of it changed.
- The knob reader, compiled for a PC against a model of the chip's registers: correct pins driven while reading, every register put back afterwards, correct bytes written for a table of readings, and every failure path leaving the fixed settings in place.
- The knob reader running with ST's real ADC driver code against a model of the converter's control register: four conversions, the right bytes written, no rule of the converter broken.
- The mapping for all 4096 possible readings: within the sensor's limits, never reversing, frame length always long enough.
- An independent review of the source and of the compiled result. It found that the first build could never read a knob on the real chip, because of a rule of ST's converter driver that the first tests did not enforce. That is fixed here and the tests now enforce the rule. It found the five-byte capture edit, the unchanged boot and recovery code and the mapping correct. The corrected reader was then run against the driver code itself; it has not had a second independent review.

Not checked, because it needs the camera:

- Whether the pots settle within the 1 ms the firmware allows before reading. Each knob is read twice; the record above shows both readings.
- Exposures shorter than 5 ms or longer than 231 ms. Those two values are the only non-default exposures ever run on this camera, and that was on an older build. At the 0.5 ms end the picture starts arriving only about 1 ms after the capture code is ready for it, against 11.5 ms today; that is the setting most likely to fail.
- Analog gain above 1x. The sensor documentation allows up to 8x; this camera has only ever run at 1x.
- Driving the gain knob's supply pin (PC12) in the capture path.
- Time from button to exposure. The knob reader adds an estimated 5 ms (a larger selector to load, and the reading itself).
- Picture quality at long exposures and high gain.

## How it works, briefly

1. On every boot a small selector program already ran before the camera code to check for a USB cable. It now also drives the two pots for about 2 ms, reads both with the ADC, and converts the readings to an exposure in sensor lines (7.69 microseconds each), a frame length and a gain code (`firmware/usb-ptp/knob.c`, `knob_map.h`, `knob_tables.py`). The exposure range is one pair of constants in `knob_tables.py`.
2. The capture code's sensor setup is not rebuilt. The selector writes the three values into the copy of that code already loaded in RAM: three bytes of the register block at `0x3418179C` and the frame-length instruction at `0x34181328`. Flash is not written at run time.
3. The capture code used to reject any photo whose exposure was not exactly 1428 lines. One branch instruction in flash is changed so that it accepts the sensor's reported exposure, and the four unreachable bytes after it are set so the code's checksum is unchanged (`firmware/usb-ptp/exposure_gate.py`; flash offsets `0x6B87` to `0x6B8B`).

Design reasons and rejected alternatives: `firmware/usb-ptp/NOTES.md`, entries dated 2026-11-14. Build record: `firmware/usb-ptp/evidence/2026-11-14-knobs/README.md`. To rebuild: `firmware/usb-ptp/README.md`.
