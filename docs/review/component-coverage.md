# Component review coverage

**148/148 component references accounted for.** The table maps every component in the physical schematic baseline to the reports that reviewed its role. It is a scope/evidence index, not a pass stamp. Circuit inspection is broader than footprint dimensional inspection; only the explicitly listed critical footprints have a measured drawing comparison in this review.

Baseline SHA256: `51e7cc050d23652d4eaf891e7384f519d6f3fd94c0c72f2dd945cbf626a62e98`. All737 terminals are present; dedicated pin/voltage tables and no-connect treatment are in the MCU and reconstruction reports. CAM1 is external; SW2/SW3 are inferred optional DNP parts. Generic passive values retain native per-instance units, but lack production MPNs.

| Reference | Part or value | Pins | Role | Review reports |
|---|---|---:|---|---|
| C1 | 10uF | 2 | Decoupling | [power](power-review.md) |
| C2 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C3 | 22uF | 2 | Power Filtering | [power](power-review.md) |
| C4 | 47uF | 2 | Energy Storage | [power](power-review.md) |
| C5 | 47uF | 2 | Energy Storage | [power](power-review.md) |
| C6 | 47uF | 2 | Energy Storage | [power](power-review.md) |
| C7 | 47uF | 2 | Energy Storage | [power](power-review.md) |
| C8 | 3.3nF | 2 | Soft Start | [power](power-review.md) |
| C9 | 4.7uF | 2 | Decoupling | [power](power-review.md) |
| C10 | 10uF | 2 | Power Filtering | [power](power-review.md) |
| C11 | 10uF | 2 | Power Filtering | [power](power-review.md) |
| C12 | 120pF | 2 | Feedback | [power](power-review.md) |
| C13 | 1uF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| C14 | 1uF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| C15 | 22uF | 2 | Energy Storage | [power](power-review.md) |
| C16 | 22uF | 2 | Energy Storage | [power](power-review.md) |
| C17 | 22uF | 2 | Energy Storage | [power](power-review.md) |
| C18 | 22uF | 2 | Energy Storage | [power](power-review.md) |
| C19 | 4.7uF | 2 | Decoupling | [power](power-review.md) |
| C20 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C21 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C22 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C23 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C24 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C25 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C26 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C27 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C28 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C29 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C30 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C31 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C32 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C33 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C34 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C35 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C36 | 8.2pF | 2 | Timing | [mcu](mcu-review.md) |
| C37 | 8.2pF | 2 | Timing | [mcu](mcu-review.md) |
| C38 | 100nF | 2 | Filtering | [mcu](mcu-review.md) |
| C39 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C40 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C41 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C42 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C43 | 4.7uF | 2 | Energy Storage | [power](power-review.md), [system](system-review.md) |
| C44 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C45 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C46 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C47 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C48 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C49 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C50 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C51 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C52 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C53 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C54 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C55 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C56 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C57 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C58 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C59 | 2.2nF | 2 | Snubber / Damping | [power](power-review.md) |
| C60 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C61 | 100nF | 2 | Decoupling | [power](power-review.md) |
| C62 | 1uF | 2 | Input Capacitor | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C63 | 1uF | 2 | Output Capacitor | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C64 | 1uF | 2 | Input Capacitor | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C65 | 1uF | 2 | Output Capacitor | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C66 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C67 | 100nF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| C68 | 100nF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| C69 | 1uF | 2 | Decoupling | [power](power-review.md) |
| C70 | 1uF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C71 | 100nF | 2 | Decoupling | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| C72 | 100nF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| C73 | 1uF | 2 | Bulk | [power](power-review.md), [system](system-review.md) |
| C74 | 1uF | 2 | Decoupling | [power](power-review.md), [system](system-review.md) |
| CAM1 | CAM-5G0-079CLR | 34 | Image Sensor Module | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| D1 | USBLC6-2SC6 | 6 | ESD Protection | [system](system-review.md) |
| D2 | SS34 | 2 | Power ORing | [power](power-review.md), [system](system-review.md) |
| D3 | 1N4148W-13-F | 2 | Isolation | [power](power-review.md) |
| J1 | USB4105-GF-A | 16 | USB-C Device Port | [footprint-spot-check](footprint-spot-check.md), [system](system-review.md) |
| J2 | TC2030-IDC-NL | 6 | SWD Debug | [footprint-spot-check](footprint-spot-check.md), [mcu](mcu-review.md), [system](system-review.md) |
| J3 | BM28B0.6-30DS/2-0.35V(51) | 34 | Camera Connector | [camera-memory](camera-memory-review.md) |
| L1 | 2.2uH | 2 | Power Filtering | [power](power-review.md) |
| L2 | 0.47uH | 2 | Power Filtering | [power](power-review.md) |
| L3 | 1uH | 2 | Power Filtering | [power](power-review.md) |
| LED1 | SML-P11MTT86R | 2 | Status LED | [power](power-review.md), [system](system-review.md) |
| Q1 | AO3401A | 3 | Latch | [power](power-review.md) |
| Q2 | BSS138 | 3 | Switching | [power](power-review.md) |
| Q3 | AO3401A | 3 | Reverse Polarity Protection | [power](power-review.md) |
| R1 | 1Mohm | 2 | Pull Up / Down | [power](power-review.md) |
| R2 | 100kohm | 2 | Current Limiting | [power](power-review.md) |
| R3 | 1Mohm | 2 | Pull Up / Down | [power](power-review.md) |
| R4 | 100kohm | 2 | Pull Up / Down | [power](power-review.md) |
| R5 | 200kohm | 2 | Feedback | [power](power-review.md) |
| R6 | 100kohm | 2 | Feedback | [power](power-review.md) |
| R7 | 100kohm | 2 | Pull Up / Down | [power](power-review.md) |
| R8 | 10kohm | 2 | Pull Up / Down | [mcu](mcu-review.md) |
| R9 | 10kohm | 2 | Pull Up / Down | [mcu](mcu-review.md) |
| R10 | 5.1kohm | 2 | Pull Up / Down | [system](system-review.md) |
| R11 | 5.1kohm | 2 | Pull Up / Down | [system](system-review.md) |
| R12 | 1.5kohm | 2 | Current Limiting | [system](system-review.md) |
| R13 | 10kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R14 | 10kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R15 | 10kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R16 | 10kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R17 | 200ohm | 2 | Voltage Reference | [camera-memory](camera-memory-review.md), [mcu](mcu-review.md) |
| R18 | 200ohm | 2 | Voltage Reference | [mcu](mcu-review.md), [system](system-review.md) |
| R19 | 2ohm | 2 | Snubber / Damping | [power](power-review.md) |
| R20 | 100kohm | 2 | Pull-Down | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| R21 | 100kohm | 2 | Pull-Down | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| R22 | 4.7kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R23 | 4.7kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R24 | 10kohm | 2 | Pull Up / Down | [system](system-review.md) |
| R25 | 10kohm | 2 | Pull-Down | [system](system-review.md) |
| R26 | 1Mohm | 2 | Pull Up / Down | [system](system-review.md) |
| R27 | 100kohm | 2 | Pull Up / Down | [camera-memory](camera-memory-review.md) |
| R28 | 4.7kohm | 2 | Pull Up / Down | [system](system-review.md) |
| R29 | 4.7kohm | 2 | Pull Up / Down | [system](system-review.md) |
| R30 | 10kohm | 2 | Pull-Up | [system](system-review.md) |
| R31 | 10kohm | 2 | Pull-Up | [system](system-review.md) |
| R32 | 100kohm | 2 | Pull Up / Down | [power](power-review.md), [system](system-review.md) |
| SW1 | B3U-3000P | 2 | Shutter Switch | [footprint-spot-check](footprint-spot-check.md), [power](power-review.md), [system](system-review.md) |
| SW2 | B3U-3000P | 2 | DNP Boot Switch | [mcu](mcu-review.md), [system](system-review.md) |
| SW3 | B3U-3000P | 2 | DNP Reset Switch | [mcu](mcu-review.md), [system](system-review.md) |
| TP1 | TP1 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP2 | TP2 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP3 | TP3 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP4 | TP4 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP5 | TP5 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP6 | TP6 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP7 | TP7 | 1 | Sensing (Shunt) | [system](system-review.md) |
| TP8 | TP8 | 1 | Test Point | [system](system-review.md) |
| TP9 | TP9 | 1 | Test Point | [system](system-review.md) |
| TP10 | TP10 | 1 | Battery Tap | [system](system-review.md) |
| TP11 | TP11 | 1 | Test Point | [system](system-review.md) |
| TP12 | TP12 | 1 | Test Point | [system](system-review.md) |
| TP13 | TP13 | 1 | Test Point | [system](system-review.md) |
| U1 | STM32N657X0H3Q | 264 | Main Processor | [footprint-spot-check](footprint-spot-check.md), [mcu](mcu-review.md), [power](power-review.md) |
| U2 | TPS62132RGTR | 17 | Power Conversion | [power](power-review.md) |
| U4 | TLV70033DDCT | 5 | USB PHY LDO | [power](power-review.md), [system](system-review.md) |
| U5 | W25Q128JVPIQ | 9 | Boot Flash | [camera-memory](camera-memory-review.md) |
| U6 | MX30LF2G18AC-TI | 48 | Energy Storage | [camera-memory](camera-memory-review.md) |
| U7 | TPS62825DMQR | 6 | Power Conversion | [power](power-review.md) |
| U8 | RV-3028-C8-32.768kHz-1PPM-TA-QC | 8 | Timing | [system](system-review.md) |
| U9 | TLV70028DDCR | 5 | Power Conversion | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| U10 | NCP115AMX120TCG | 5 | Power Conversion | [camera-memory](camera-memory-review.md), [power](power-review.md) |
| U11 | LIS2DW12TR | 12 | Orientation Accelerometer | [system](system-review.md) |
| U12 | TPS22918DBVT | 6 | Load Switch | [power](power-review.md), [system](system-review.md) |
| Y1 | CX3225SA40000D0PTWCC | 4 | HSE Clock | [mcu](mcu-review.md) |

Physical net membership remains unchanged. Review reports identify intentional future corrections; regenerated source-equivalence tests will need an explicit approved-change list when those corrections are applied.
