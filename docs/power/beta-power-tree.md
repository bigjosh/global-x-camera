# Beta board power tree: proposal

**Status: proposed November 25, 2026; not yet approved by the user.** It answers the user's idea for the beta board: one buck for 1.8 V, and a 3.3 V rail the MCU switches on for the SD card. The idea holds, with four changes. A researcher built this from the stored ST, sensor and regulator documents and a second reader re-opened the citations and re-derived the numbers. Nothing here has been measured, and distributor figures are search snippets, not live pages.

Inputs settled with the user: a single LiPo, the Grepow GRP292434 (210 mAh, 2.9 mm cell, protection board unfolded flat beside it), and no charger; USB powers the camera when plugged in and must never charge the cell; an SD card on SDMMC2; unordered power-down accepted; the SPDT-and-capacitor start stays; ST-LINK is the only programming path.

## The tree

| Block | Part class | Makes | Notes |
|---|---|---|---|
| Source select | P-FET on the cell, gate on VBUS; VBUS joins through a reverse-blocking switch after the latch | cell or VBUS on one node | VBUS present turns the cell's FET off in hardware. The two body diodes oppose, so nothing flows into the cell. Untested: the prototype's version was removed on November 10. |
| Latch | the existing P-FET latch, SPDT switch and 2.2 µF trigger, held by an MCU pin | switched input | At a 3.0 V cell the trigger holds the gate for only about 40 ms, so the FET must be specified for 1.8 V gate drive. |
| Main buck | TI TPS6282x, 1.8 V (stored datasheet; used in the recovered design) | `1V8_MAIN` | Soft start 1.25 ms, inside ST's ramp limits. Feeds VDD, VDDA18AON, VDDA18PLL, VBAT, the unused banks and the boot flash. |
| Auxiliary switch | load switch enabled by `PWR_ON` (TI TPS22918, stored datasheet), with a bypass link | `1V8_AUX` | ST requires the main supplies up before the auxiliary ones. Feeds the internal SMPS, the ADC, CSI and USB analog supplies, the sensor's I/O and the 1.2 V regulator. |
| Core | the MCU's internal SMPS | 0.81 V | No extra converter and no firmware needed to start. Never run in this project: the Nucleo ships on its external buck. |
| SD rail | LDO with slow slew and active discharge (onsemi NCP115C 3.3 V, stored datasheet), enabled by an MCU pin with a pull-down | `3V3_SW` | Feeds the card, the MCU's SD pin bank (VDDIO5) and, through a link, the USB PHY's 3.3 V pin. |
| Sensor analog | 2.8 V LDO from the input node | 2.8 V | Holds until the cell is near 2.75 V. |
| Sensor core | 1.2 V LDO from `1V8_AUX` | 1.2 V | Burns up to about 52 mW while streaming, which a LiPo can afford. |
| LED | low-side FETs from the input node | — | Fault blinks then work with the 3.3 V rail off. |

## Why an LDO for 3.3 V

On a 3.0 to 4.2 V cell the drop is small: an LDO is 79 to 92% efficient between 4.2 and 3.6 V, and below about 3.4 V it simply follows the cell, which the card accepts down to 2.7 V. A buck would save under 10 mW for under a second per photo and add an inductor and ripple on the card and PHY supplies. The slow-slew version matters: ST limits these rails to between 20 and 1500 µs per volt, rising and falling, and the fast versions of the same LDO ramp at 5 µs per volt.

## The 1.8 V window

The MCU pins need 1.746 to 1.89 V: the floor is the USB and CSI analog supplies, the ceiling the internal SMPS input. A fixed 1.8 V buck leaves about 18 mV above the floor after the load switch. If that proves short, ST's own arrangement is the fallback: a small always-on 1.8 V regulator for the main group and the buck enabled by `PWR_ON`.

## Firmware rules this tree forces

- Switch `3V3_SW` on early in boot, not only for the save, so the card is ready when readout ends. Whether that adds image noise during the exposure has to be measured.
- Rail on: enable the LDO, wait a fixed time (the supply-ready flag does not work, erratum ES0620), set the bank's supply-valid bit, then start the card. Rail off: idle the card, stop SDMMC2, drive its pins low or high-impedance, clear the supply-valid bit, disable the LDO. Do this before releasing the latch.
- Never set the bank's 1.8 V range bit while it is at 3.3 V: ST says that damages the device.
- Never issue a backup-domain reset: a stored erratum says the internal SMPS output then drops and does not recover.
- The SD start-up profile and the USB start-up wait both assume an already valid rail and must change.
- With `3V3_SW` off until firmware runs, the boot ROM's USB loader cannot work. That fits ST-LINK-only programming.

## Open points

1. **Ask ST.** The datasheet's Table 24 limits inputs in the 3.3 V range to "Min(VDD, VDDIOx) + 0.3", which read literally forbids a 3.3 V SD bank beside a 1.8 V VDD. The hardware guide says the banks are independent and may be tied to the card supply, and the reference manual says they "can be independent from VDD", but no stored ST board shows the combination. Also ask whether one 1.8 V rail may feed both supply groups at once; if yes, the load switch is bridged.
2. **Try the internal SMPS on the Nucleo** before committing copper. UM3417 Table 7 gives the solder bridges. This is a function trial, not one of the power measurements the user declined.
3. **Source selection has never run on hardware.** Bench or simulate plug and unplug, VBUS at 4.4 V against a full cell, and the trigger at a 3.0 V cell.
4. **Low-battery lock-out** at about 3.3 to 3.4 V under load keeps both the 3.3 V rail and the 2.8 V regulator in regulation. It needs the chosen cell's resistance.
5. **VBUS over-voltage and inrush.** The buck and LDO are rated 5.5 V; the prototype measured 6.14 A of USB inrush without series resistance.
6. **Probe.** The board is 1.8 V: an STLINK-V3MINIE works from 1.65 V; a plain STLINK-V3SET needs its voltage adapter.
7. **RTC supply** waits on the RV-3032 documents.
8. The 2.8 V version of the LDO looked thinly stocked; buy it early or name an alternate.

## What would change this

ST says no to a 3.3 V bank beside a 1.8 V VDD: run VDD at 3.3 V as the prototype does, or put a level translator on the SD lines. The internal-SMPS trial fails: an external core buck. The card is ready within about 20 ms, or noise shows during exposure: switch 3.3 V on after readout. Operation is wanted below a 3.3 V cell: a buck-boost for 3.3 V.

Sources: DS14791 Rev 10, AN5967 Rev 5, RM0486 Rev 4, ES0620 Rev 5, UM3417 Rev 4, the VD56G3 and Swissbit S-56u datasheets, and the TI and onsemi regulator datasheets, all stored under `datasheets/`.
