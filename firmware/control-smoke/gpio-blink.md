# Standalone A0–A5 digital blink test

**Current status, November 13:** the temporary blinker has been replaced by the
normal [D8 HOLD camera/PTP firmware](../usb-ptp/evidence/2026-11-13-d8-hold/README.md),
which the user reports works. The procedure and results below describe the
earlier isolated-board diagnostic, not the currently installed application.

Before ever loading this temporary diagnostic again, disconnect the
exposure/ASA pots and HOLD circuit: **all six contacts become outputs**.

| Contact | MCU output | Supply |
|---|---|---|
| A0 / CN4.1 | PF5 | Main 3.3 V |
| A1 / CN4.2 | PC10 | VDDIO4, 3.3 V |
| A2 / CN4.3 | PF6 | Main 3.3 V |
| A3 / CN4.4 | PA2 | Main 3.3 V |
| A4 / CN4.5 | PC12 | VDDIO4, 3.3 V |
| A5 / CN4.6 | PH2 | VDDIO4, 3.3 V |

All pins change together: LOW250ms, HIGH250ms, repeating at2Hz. Compare each
to CN5.6/GND. A DC meter may show an average near half the HIGH voltage;
a scope or logic analyzer resolves the waveform.

`gpio_blink.c` contains the624-byte direct-register loop. The original
400MHz boot/UART guard, early PA2 hook and fault handlers remain unchanged.
The normal path branches to the loop before camera/storage/USB/memory setup.
The buffered analog companions stay analog/no-pull. VDDIO4 uses its existing
3.3V supply with isolation released. There is no capture, save or shutdown.
A3 retains its early HOLD behavior during startup/recovery, then joins the
square wave in normal mode.

Build offline with `build_gpio_blink.py --out <new-directory>`. After the
established UART stimulus, use `blink_recovery.py --build <reviewed-build>
--out <new-directory>`. Its precise binary admission must be reviewed for
each new build. No general recovery allowlist was relaxed.

RAM proof is32words at0x34183000: word0BLNK,1schema,2sequence,3half-cycle
count,4level,5edgeDWT,6independent last interval,7packed IDR,8packed ODR,
11PWR_SVMCR1,12AHB4ENR,13last LOW inputs,14last HIGH inputs,15–16LOW/HIGH
counts,17target interval,18initialDWT,19error,20–23GPIOA/C/F/H MODER.
Packed bits0..5 mean A0..A5. Word6 is outside the sequence-protected
publication and must be interpreted separately. The retained original fault
handler records faults at0x341F5000.

Live input/output readbacks alternated0x00/0x3F, with advancing counters,
zero errors and100,000,116–124cycles per half-period (nominal250.0003ms).
No external waveform/amplitude was measured by the automated check. UART recovery passed9/0;
the final normal reset returned to continuous blinking. Full64KiB programmed
sector independently matched; the following64KiB+4KiB remained unchanged.
Original camera firmware was backed up for restoration.

[Frozen evidence and final state](evidence/2026-11-13-a0-a5-blink/README.md).

**Subsequent physical result:** the user reports the five other A contacts
blink, while A3 and direct PA2 tap CN3.34 remain near0V. Fresh read-only GPIO
reads still showed PA2 IDR/ODR alternating. The user subsequently reported
approximately 1 Mohm from each A pin to ground, and effectively 0 ohm between
A3 and CN3.34. Those observations do not identify the exact failure mechanism.
A3 is no longer used for HOLD. [Historical physical investigation](evidence/2026-11-13-a0-a5-blink/physical-a3-followup/README.md).
