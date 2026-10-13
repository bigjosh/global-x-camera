# Power-latch IC options

> **Historical alternatives:** this September 5 comparison predates the selected LTC3621 button/RUN/GPIO-HOLD direction. Use the [current power study](../power.md) for accepted prototype behavior and remaining integration work. The 50 ms target now means start of exposure from fully powered off; the main-path room-temperature OFF target is 100 nA, with RTC backup additional and separately budgeted. No controller recommendation below replaces those decisions.

Research date: 2026-09-05. Requirements retained: 8–13.2 V battery stack, common ground, button starts a capture, processor commands indefinite power-off after saving, USB can supply the system, very low off-state drain, and 50 ms from shutter press to acquisition. This is a candidate comparison; no component has been selected or circuit changed.

**Dedicated controllers can reduce off current to tens of nanoamps, but the lowest-current candidates do not directly accept the battery voltage and have appreciable button qualification delays. None below is a demonstrated drop-in solution meeting the complete timing, leakage and source-selection requirements.**

## Shortlist

The current column is controller supply current with its output off under the stated test conditions. It does not include external MOSFET leakage, interface resistors, an added regulator or the RTC. Temperature and voltage qualifications must stay attached to the numbers.

| Device | Operating supply | Off-current specification | Button-to-enable behavior | Assessment |
|---|---|---|---|---|
| MAX16150 | 1.3–5.5 V | 20 nA maximum through70°C;40 nA maximum through85°C, both specified at5 V.10 nA typical in the85°C-range row. | Fastest listed option50 ms nominal, ±20% timing accuracy:40–60 ms. | Best low-leakage latch shortlist item. CPU CLR gives indefinite off, but it needs a low-voltage always-on supply, high-voltage switch interface and a separate immediate-start path if retaining50 ms capture. |
| TPL5111 / TPL5110 | 1.8–5.5 V | 35 nA typical,50 nA maximum under2.5 V/25°C default conditions; not a full-temperature/voltage maximum. | Manual input must remain high20 ms, output asserts within the following10 ms after initialization. | Lower documented manual latency. One-shot mode avoids periodic wake and DONE ends a cycle, but still needs a low-voltage supply/interface and leaves little capture time. |
| TPS3424, appropriate latched KILL variant | 1–6 V | 18 nA typical;24 nA max at3 V/25°C;90 nA max at3 V through85°C;350 nA max at6 V through125°C. | Shortest supported setting50 ms nominal, ±10%. Smaller capacitors cannot bypass that floor. | Flexible latch/host shutdown, but no latency advantage overMAX16150 and no direct stack compatibility. |
| LTC2955-2 | 1.5–36 V | 1.2 µA typical,3 µA maximum through85°C, specified at7 V; no explicit12 V maximum in that row. | 19–45 ms debounce. KILL ignored for304–720 ms after startup; restart lockout0.6–1.4 s. | Straightforward direct-stack controller with external PFETs, but higher drain and minimum on-time work against this camera's objectives. |
| LTC2956-2 | 1.5–36 V | 0.3 µA typical,1 µA maximum through85°C in OFF, specified at3.3 V; no explicit12 V maximum in that row. | 19–45 ms debounce. True indefinite OFF needs a long SLEEP command followed by0.6–1.4 s delay. | Lower current thanLTC2955, but its timer/shutdown behavior is a poor match for short capture-and-save cycles. |

Sources: [MAX16150 pp7,12](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX16150.pdf#page=7), [TPL5111 pp5,9–11](https://www.ti.com/lit/ds/symlink/tpl5111.pdf#page=5), [TPL5110](https://www.ti.com/lit/ds/symlink/tpl5110.pdf), [TPS3423/3424 pp8–9,17–18](https://www.ti.com/lit/ds/symlink/tps3423.pdf#page=8), [LTC2955 pp3–6,15](https://www.analog.com/media/en/technical-documentation/data-sheets/2955fa.pdf#page=3), [LTC2956 pp3–4,10,12–15](https://www.analog.com/media/en/technical-documentation/data-sheets/2956fa.pdf#page=3).

## Integration details that affect selection

- A low-voltage controller could use the existing lowest-cell tap with a common ground, avoiding an always-on high-voltage regulator. Check the chosen cell's full voltage/sag range, the extra one-cell drain, controller output drive, and safe MCU interfaces when the main rails are off. A passive divider alone is not a regulated controller supply. The MAX16150's stated20/40 nA maximum is measured at5 V; confirm the required bound for the actual cell-tap operating envelope with the supplier rather than quietly relabeling it.
- These low-voltage parts cannot directly pull a battery-side PFET gate up to13.2 V or switch the complete camera load through their small internal outputs. An appropriate high-voltage interface and external power MOSFETs remain necessary. USB reverse-current blocking is a separate function; it is not supplied by a basic pushbutton latch.
- An immediate mechanical startup path could let the CPU boot while a nanopower controller debounces the same press. That is a possible circuit direction, not a validated workaround: it must maintain power for short valid presses, tolerate bounce, establish the latch before startup support ends, and keep battery voltage away from logic pins. It adds components and must be compared with the simpler corrected discrete latch.
- TPL5111 active-high output suits an enable/level-shifter path; TPL5110's output is active-low. In one-shot mode both allow repeated manual cycles without periodic wake, but they initiate a cycle when the controller itself powers up. DONE is ignored while the manual input remains held high. Their initial resistance-conversion interval is100 ms typical/120 ms maximum, separate from subsequent manual wake timing.
- LTC2955 KILL can leave the system off indefinitely when its unused automatic ON input is held low. Its shutdown lockout can require keeping a newly started system powered longer than the desired capture/save interval. LTC2956 needs SLEEP high longer than its long-press setting to reach true OFF; a short SLEEP instead returns to timed waking. At its shortest setting, long SLEEP plus the off delay can take up to about1.58 s; ONMAX must permit that command.
- All schemes still need the N6 main/auxiliary supply sequence and the camera's ordered shutdown. A latch IC is not a complete rail sequencer.

## Other screened parts

MAX16169 gives40/80 nA maximum at3.3 V through70/85°C, but retains50 ms nominal debounce; its200 mA internal output does not solve the13.2 V switching requirement. MAX16164 gives40/80 nA shutdown maxima at3.3 V through70/85°C and supports infinite sleep, but debounce can reach90 ms. MAX16151 handles5–36 V but specifies up to15 µA standby at36 V and has50 ms nominal debounce. None offers a better fit here. [MAX16169 pp5,9](https://www.analog.com/media/en/technical-documentation/data-sheets/max16169.pdf#page=5), [MAX16163/164 pp7,15](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX16163-MAX16164.pdf#page=7), [MAX16151 pp7,12](https://www.analog.com/media/en/technical-documentation/data-sheets/max16151.pdf#page=7).

STM6600/6601 have0.6 µA typical/1 µA maximum standby,1.6–5.5 V supply and20/32/44 ms minimum/typical/maximum debounce. They add no clear advantage to this shortlist. [STM6600/6601 pp39–40](https://www.st.com/resource/en/datasheet/stm6600.pdf#page=39).

## Leakage budget and recommendation

For any particular cell, constant drain over ten365-day years costs:

| Current | Charge consumed |
|---|---:|
| 20 nA | 1.752 mAh |
| 100 nA | 8.76 mAh |
| 1 µA | 87.6 mAh |
| 3 µA | 262.8 mAh |

These are charge calculations, not predicted battery life; capture energy, cell self-discharge and temperature/aging are additional. Stack-powered current flows through every series cell; a cell-tap controller adds its drain to that cell only.

**Recommendation:** keep MAX16150 as the primary low-leakage IC candidate and compare a proposed immediate-start implementation against the corrected discrete latch. Retain the50 ms requirement unless explicitly changed. Establish a provisional whole-latch off-current target of100 nA or less over the selected storage envelope, then see which implementation can actually meet it. This is a proposed target, not achieved performance. Optimizing an IC from40 to20 nA has little value if an external MOSFET or interface leaks1 µA. Select the power MOSFETs and interfaces on guaranteed off-state limits at the actual voltages/temperature, and measure the complete circuit.
