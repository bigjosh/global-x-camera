# SD-to-NAND peak-current estimate — October 28, 2026

**Planning estimate: the selected Alliance serial NAND could reduce the
storage-phase peak by roughly 35–55 mA at the board's 5 V input.** That is not
a measured NAND result or a guaranteed reduction in the cycle's absolute peak.
It does not address the initial power-on transient, and camera/receiver peaks
remain. No storage replacement or physical modification was made for this estimate.

## Measured reference and model

An offline reanalysis of the existing GPIO-aligned recordings, with native
sample continuity and hash checks, finds:

| Whole-board condition | Current at 5 V |
|---|---:|
| SD transport, four unchanged normal warm runs: mean | 126.45–132.69 mA |
| Same SD transport: highest 1 ms average | 139.37–147.55 mA |
| Same SD transport: highest 10 ms average | 127.93–138.38 mA |
| Sensor stopped, before SD initialization: two controlled holds | 79.13–79.19 mA |
| Alliance NAND replacement, first-order programming-phase model | approximately 95–105 mA |

One-millisecond peak windows are sampled every 0.1 ms. They describe battery-
relevant operating demand on that timescale, not a bound on sub-microsecond
spikes. Per-run values and window boundaries are saved in
[sd-to-nand-peak-windows.json](sd-to-nand-peak-windows.json). The source recordings
and comparison limits are in the [aligned-ablation evidence](evidence/2026-10-28-aligned-ablation/README.md).

The model adds approximately 15–22 mA NAND-supply demand to the approximately
79 mA pre-init hold, then rounds to95–105mA to avoid false precision. Host
bit-banging/controller activity, changed IO-bank supply, pullups and NAND
startup are not measured. The hold still had the idle SD physically attached;
it is not a pure card-free residual. The result is an engineering estimate,
not an isolated SD-current subtraction or a worst-case power budget.

## Exact parts and conversion paths

| Part | Program current at chip | Approximate added 5 V input current |
|---|---:|---:|
| Alliance AS5F14G04SND-10LIN, 1.8 V | 20 mA typical / 30 mA DC-table maximum | 14.7 / 22.0 mA, via AUX3.3 buck → 1.8 V LDO, assuming 90% buck efficiency |
| Winbond W25N01GV on MIKROE-3780 Flash 5 Click, 3.3 V | 25 mA typical / 35 mA DC-table maximum | 25 / 35 mA through the main3.3 V LDO; or18.3 /25.7 mA from AUX3.3 at90% buck efficiency; board LED adds a few mA |

The Alliance model is `I5 = 3.3 × I_NAND / (5 × efficiency)`, because its
planned rail includes a3.3→1.8V LDO. Using1.8V directly in that equation would
omit the LDO loss. The SD now uses main3.3V from the5V LDO, so card-rail current
approximately appears one-for-one at the5V input. Converter incremental
efficiency is assumed, not measured at the new load.

Alliance Rev3.2 Table16-2 specifies20/30mA for read and program; its front-page
25mA shorthand is not used. These DC operating values do not establish a
power-on or instantaneous spike limit. Power-on readiness is3ms typical/4ms
maximum with status polling. This is the **serial AS5F** device; the older
parallel AS9F's20mA programming and50mA POR numbers do not apply.
[Alliance exact-family datasheet, pp44–47](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.2_Jan2026-revised.pdf).

Winbond RevR July2023 specifies25/35mA for read/program/erase and250µs typical
page programming. Its newer power-up timing differs from the older PDF linked
by the Click board; no startup-current maximum was found. The Click's1Gbit
capacity is also much smaller than the Alliance4Gbit, and its power LED adds
load. The project records support these two candidates but do not contain an
itemized order receipt.
[Winbond RevR](https://www.winbond.com/resource-files/W25N01GV%20Rev%20R%20070323.pdf),
[Flash5Click board documentation](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/190/MIKROE-3780_Web.pdf).

## Whole cycle, battery current and save time

The earlier normal camera/SD overlap produced approximately190–200mA peaks
over1ms. Delaying SD commands until sensor STOP reduced that to148–156mA while
the card was still present. This is direct evidence that scheduling matters:
a NAND substitution can lower storage demand without eliminating the camera's
own peak. Depending on overlap, a roughly20–40mA reduction in the largest
post-startup operating peak is plausible, but not established. Starting NAND
programming after sensor STOP offers more peak control at the cost of latency.

For scale only,35–55mA less at5V is175–275mW. At a healthy12V battery pack and
assumed90% LTC efficiency, that corresponds to16–25mA less through all four
series cells. The earlier collapsing-pack trace cannot be predicted by this
fixed-voltage conversion; its voltage and converter operating point change
with load. No reduction in the initial inrush peak is claimed.

The current1,909,760-byte RAW object occupies933 NAND pages of2048 data bytes.
Alliance600µs typical programming means **559.8ms internal programming alone**,
plus transfer/commands/metadata/error handling. It has no qualified next-page
load-while-programming sequence; the selected bit-banged Arduino interface
could add substantial time. This can be slower than the measured SD transport
164–384ms, so lower current can increase total energy. Pre-erasing while onUSB
removes erase work from the capture path but does not remove program time.

Ethernet power-down independently saved36.76mA/182.85mW in the
[isolated-board measurements](evidence/2026-10-28-isolated-nucleo/README.md).
That is a measured firmware saving of similar size to the NAND estimate;
combining it with NAND remains an unmeasured configuration. Qualify the NAND
rail and full-image save/readback on the bench before predicting coin-cell
operation or adopting a total-energy budget.
