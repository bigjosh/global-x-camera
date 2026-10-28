# Isolated Nucleo: bounded MDIO diagnosis

2026-10-28. Offline support for the root agent, which exclusively operates the
bench. Camera and SD are reported physically disconnected. This directory does
not assert a successful PHY transaction or power saving until the root's actual
operation evidence establishes it.

## Scope and interfaces

`mdio_diag.c` toggles actual MDC/MDIO GPIO pads, scans all 32 Clause 22 addresses
for the LAN8742 IDs, and restores the exact owned pin settings and added GPIO
clocks. MDIO is open drain throughout; HIGH means released to the board's pullup.
There is no PHY write frame, reset, MAC enable, storage command or power switch.
The nominal bus rate is 100 kHz at the required 400 MHz processor clock. Every
wait and scan loop is bounded. Missing turnaround still clocks the complete read
frame before the next preamble. The pad check does not replace a waveform or
voltage measurement at the PHY package.

- Frozen image: 2,264 bytes, SHA256
  `eb9dc283de0dbdf692774723d29760a90595292dcaf392e77ef4c361b056b0e3`.
- Load `0x343C4000`, Thumb entry `0x343C48AD`, self-branch park `0x343C4862`.
- Proof: 2,048 bytes at `0x343C6000`; stack `0x343AF000..0x343B0000`.
- The naked entry switches to that stack before any C prologue. Final execution
  remains at the diagnostic park; the old caller stack/PC are not restored.
- `run.py` is inert on import. Running it directly verifies hashes offline.
  `prepare`, `prepare_from_refused_v1`, `launch`, and `observe` are explicitly
  root-only hardware operations. Call `observe` at least 0.5 seconds after launch.
- `completed_and_restored` and `phy_found` are independent outcomes. Zero
  responding addresses is a completed diagnosis, not power-down qualification.
- `test_offline.py` mocks instrument access and checks exact binary identity,
  proof handling, and refusal to access high SRAM while its clocks/reset are bad.

## Mapping and sources

Three independent board/MCU records agree:

| Signal | MCU pad | Board evidence |
|---|---|---|
| MDIO | PF4, package L2 | U24 pin 12, R56 1.5 kΩ pullup to auxiliary VDD3V3; ODB net138; DS14791 AF11 ETH1_MDIO |
| MDC | PG11, package U13 | U24 pin 13; ODB net115; DS14791 AF11 ETH1_MDC |
| PHY reset | Target NRST through SB14 | U24 pin15; no independently controlled reset GPIO |
| Reference oscillator | X4 25 MHz crystal | PHY XTAL1/XTAL2, R91/C59/C60; no MCU oscillator-enable signal |
| PHY address strap | RXER/PHYAD0 via R68 pulldown | Expected address0; diagnostic checks every address |

Primary sources: [MB1940 C02 schematic, sheet7](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
[STM32N657 DS14791 alternate functions](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf),
[LAN8742 datasheet §§3.5, 3.8.3.1, 4.2, 5.6.5](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf).
Local independent layout records are in
`tmp/hardware-review/nucleo-modifications/odb/odb/steps/pcb/eda/data` and
`layers/comp_+_top/components`; local MCU text is
`tmp/hardware-review/mcu/STM32N657X0_DS14791_plain.txt`.

Expected IDs are register2 `0x0007` and register3 masked by `0xFFF0` equal to
`0xC130`. The read sequence uses ST01/OP10, five address bits, five register bits,
released turnaround followed by the PHY's zero, sixteen data bits and idle.
The 5 µs half-period exceeds the documented management timing limits.

The earlier ablation helper failed at turnaround before any PHY register write.
Released MDIO HIGH and restored GPIO configuration alone did not prove that
the low-driving pad worked, that the PHY responded, or that address0 was correct.
The new diagnostic separates those questions. The source crystal is independent
of camera/MCU firmware, so “firmware never enabled the Ethernet clock” is not an
established explanation. PHY power-down remains unqualified until identification
and stable BMCR reads succeed.

For a later controlled power-down experiment, use only the identified PHY;
read BMCR twice, change only bit11, verify twice, and retain a matched control.
Clearing power-down automatically resets the PHY, so restoration must be read
back, not assumed. General power-down keeps management accessible and stops
REFCLKO; it is not equivalent to removing all PHY supply current.

## Preserved access incident and revised precondition

`../mdio01/debug/cli-01.log` records a failed RAM download at `0x343C4000`
directly from the normal early recovery park. The diagnostic never executed.
Root subsequently reported AP1 inaccessible and recovered the board. The early
prefix park identifies firmware and safe execution context, but **does not
establish that high AXISRAM is enabled**. It is insufficient for this placement.

The ordinary `prepare(output, prior)` route now requires a successful frozen
isolated-v1 sweep result. Before any high-memory read/write, it checks live
RCC_MEMENR/MEMRSTR for all AXISRAM1–6, then exact main park, code, proof and faults.
The main sweep must first have run the existing reviewed SRAM bridge.

A separate `prepare_from_refused_v1(output, prepared, proof_file)` admits only
the exact hashed `../inherited02/resume` refusal: STATE15/ERROR4, disabled
TCM_ECC pending, no timer/workload/GPIO/debug changes, IRQ-masked terminal park.
It rechecks live code, proof, memory clocks, 400 MHz clock tuple and faults.
It preserves `source_run_passed:false` and does not clear that pending interrupt.
This is a narrow recovery precondition for a device without camera/SD attached,
not a generic failed-storage or failed-experiment success override.

Future main-probe versions are not implicitly admitted by their address range.
Qualify their exact code/proof/park and restored 400 MHz clock state separately.

## Follow-up: the PHY responded; the original sampling edge was wrong

Root's `../mdio02/debug/result.json` completed all32 addresses and restored the
pins, but address0 returned `0x000F`/`0x8263`. Those are exactly
`(0x0007 << 1) | 1` and `((0xC131 << 1) | 1) & 0xFFFF`.
The apparent second-register turnaround failure was its first data bit.
It was incorrect to summarize this as no response at every address.

The original routine sampled MDIO5µs after raising MDC. LAN8742 table5-15 allows
the PHY's next output bit to appear immediately after that edge. V2 samples the
stable bit at the end of the low interval, before raising MDC. Root's
`../mdio03/debug/result.json` then returned address0 IDs`0007/C131` and two
BMCR`3000` reads, with exact GPIO restoration and no CPU fault. V1 remains frozen;
V2 is in `v2/`, SHA`ebe2fa414c75c11081fa07ed2ba518c3622b1b95cddb019f460f7c28aece4027`.

`v2/test_edge_model.py` compiles the actual v1/v2 `clock_bit` and framing C against
a software PHY that advances on the rising edge. Nine patterns reproduce the
old shift and read correctly with v2. The earlier power-ablation host test had
replaced `clock_bit`, so its passing result did not cover this defect.
The earlier `firmware/capture-raw/power_phy.inc` shares the bad sampling edge;
its old power-down experiment is not qualified by those earlier mock tests.

Official C02 BOM explicitly marks U24 LAN8742A, X4 25MHz crystal and L5 fitted.
Neither an absent component nor a missing MCU-supplied oscillator explains this
now-resolved read failure. These read-only results qualify management access,
not yet a measured power-down saving; the separate `power_aba/` experiment
changes and restores only the identified PHY's BMCR power-down bit.
