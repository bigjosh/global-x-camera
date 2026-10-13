# Shutter-motion energy harvesting: envelope calculation

> **Historical energy estimate and future-work input:** the assumed 50 mJ and earlier VD55G0 workload below are not measured requirements for the selected VD56G3 prototype. The user retained a mechanical frame-advance mechanism winding/driving a spring as future work; no mechanism or energy-conversion topology is selected. The [current prototype](../../spec.md) uses four series CR2032 cells through LTC3621.

**September 19, 2026. Feasibility estimate, not a measured energy budget or a component selection.**

**Conclusion:** a normal short shutter click cannot practically power the present STM32N6 camera through capture and durable save. A deliberate squeeze, slider or winding action could supply the required work, but would change the mechanism, thickness and user experience. The next useful experiment is a complete electrical energy measurement; detailed generator selection is premature.

## Electrical energy to capture and save

Use **50 mJ = 0.050 J** delivered to the camera electronics as a central screening target. This is an assumption supported in scale by the existing [current budget](current-budget.md) and [quad NAND assessment](quad-nand-comparison.md), not a measured requirement, physical minimum or guaranteed maximum.

| Contribution | Illustrative operating assumption | Energy |
| --- | --- | ---: |
| Boot/setup and acquisition | 350 mW for 50 ms | 17.5 mJ |
| MCU and other non-flash loads during save/verify | 200 mW for 100 ms; camera safely shut down after capture | 20 mJ |
| NAND operations | Allowance; earlier internal-program-only estimates are about 1–3 mJ | 3 mJ |
| Startup charging, shutdown and uncertainty allowance | Engineering allowance, not derived maximum | 9.5 mJ |
| **Screening total** | | **50 mJ** |

The first 50 ms is the desired acquisition target, not proven cold-boot performance. The flash allowance can be too small for a slower device, additional verification, erases or retries. MCU sleep during NAND busy time can reduce the model. Existing 3.3 V / 250 mA planning current sustained for 150 ms would itself imply **124 mJ**, demonstrating that 50 mJ is not conservative for every architecture/workload.

The sensor's published reference currents are 0.25 mA at 1.8 V, 46 mA at 1.15 V and 17.3 mA at 2.8 V: **about 102 mW at its own pins** under the stated full-resolution 185 fps operating conditions. The existing 1.8 V-fed core LDO increases upstream power. An STM32 active reference in the project is about 192 mW at 800 MHz. These references establish scale; they do not measure one cold capture. [VD55G0 Rev.10 p.16](https://www.st.com/resource/en/datasheet/vd55g0.pdf#page=16), [STM32 datasheet](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [project current accounting](current-budget.md).

Evaluate a range such as **20, 50 and 150 mJ** when comparing mechanisms. All mechanical requirements scale linearly with the actual measured energy. Even a future 5 mJ implementation would still exceed the output of the commercial click harvesters below by more than an order of magnitude per actuation.

## Work available from a finger

`E_mechanical = integral(F dx) ≈ F_average × travel`

Convenient units: **1 N × 1 mm = 1 mJ**. Electrical energy actually consumed by the camera is `E_camera = eta_total × E_mechanical`. Here eta_total includes the generator, rectification, storage usability and regulation. Use **50% as an optimistic illustrative system target**, not a proven efficiency of a miniature click harvester.

| Illustrative action | Average force | Travel | Mechanical work | Camera energy at 50% total efficiency |
| --- | ---: | ---: | ---: | ---: |
| Light short button | 3 N | 1 mm | 3 mJ | 1.5 mJ |
| Firm long button | 10 N | 5 mm | 50 mJ | 25 mJ |
| Deliberate squeeze/lever | 20 N | 10 mm | 200 mJ | 100 mJ |

These forces are **averages across travel**, not maximum spring forces. A zero-preload linear spring stores only `0.5 × F_peak × travel`. A mechanism can exchange force for distance but cannot increase the work. Holding a stationary button down adds no mechanical energy; press duration is useful only while displacement continues. A spring can store press energy and release it rapidly into a generator, but that is the same energy, not an additional source.

For the current **Omron B3U-3000P**, the latest manufacturer sheet lists nominal operating force 1.59 N and pretravel 0.2 mm. Their product is only **0.318 mJ**. That is a rough work scale rather than a measured force-displacement integral; the switch is not a generator. Even this amount converted perfectly is about **157 times below 50 mJ**. [Omron A162-E1, p.1](https://components.omron.com/eu-en/sites/components.omron.com.eu/files/datasheet_pdf/A162-E1.pdf#page=1).

## Actual miniature harvester benchmarks

**EnOcean ECO 260**, November 2025 datasheet: **120–210 microjoules = 0.12–0.21 mJ at 2 V per actuation**, with suitable power management at the recommended temperature. Its force is 1.6–2.7 N and travel 1.5–1.6 mm. Dimensions are 29.3 × 19.5 × 7 mm, already thicker than the complete camera's 5 mm target. It generates on push and release: ideal accumulation across a full cycle is about 0.24–0.42 mJ, before additional storage/regulation losses. A 50 mJ camera would therefore require approximately **120–210 complete push/release cycles**, assuming no loss after the specified output. Release energy is unavailable before release. [Manufacturer datasheet](https://www.enocean.com/wp-content/uploads/downloads-produkte/en/products/enocean_modules/ECO-260/ECO_260_Datasheet_Datasheet_Nov2025.pdf).

**ZF AFIG-0007** provides a second scale reference: approximately **0.33 mJ per actuation into a 100-ohm load at the stated 0.1 m/s speed**, with 5–12 N operating force and 5.3 mm typical total travel. Usable regulated camera energy would be lower; electrical energy into a resistor is not a qualified battery-charging output. [ZF technical specification TS-AFIG-01, revision 04](https://switches-sensors.zf.com/wp-content/uploads/2023/03/2023_3-TS-AFIG-01_04.pdf).

These are benchmarks, not recommendations to integrate either product. Open-circuit voltage and peak power from a piezo or magnetic harvester do not establish its total usable energy; require a loaded integral of voltage times current and measured storage charge.

## Motion required for one shot

For **50 mJ electrical** at **50% total efficiency**, the user must provide **100 mJ mechanical work**:

| Available travel | Required average force |
| --- | ---: |
| 1 mm | 100 N, about 10.2 kg-force |
| 5 mm | 20 N, about 2.0 kg-force |
| 10 mm | 10 N, about 1.0 kg-force |

At 20% total efficiency, those forces increase by 2.5 times. A 10 mm stroke at 10 N is mechanically plausible for a deliberate lever or slide, but is a substantially different control from a shutter button. It also disturbs the camera during capture. An in-plane sliding cover or fold-out winding lever could avoid imposing all the travel through the board's thickness, but adds mechanism volume and wear. Separate charging from exposure: charge on the larger motion, then use a light trigger for capture. A spring release can make generator output less sensitive to finger speed, while increasing mechanism complexity.

## Buffering and startup

The generator pulse must be buffered because the electronics need sustained power through boot, capture and storage. A voltage supervisor should admit startup only after enough energy is stored for a complete transaction, then maintain the MCU/camera shutdown ordering and NAND commit. Repeated partial boots can otherwise consume every incoming pulse without ever completing a photo. Do not depend on the user holding or releasing at a precise time to finish a write.

For a capacitor discharging from `Vhigh` to `Vlow`:

`E_camera = 0.5 × C × (Vhigh^2 - Vlow^2) × eta_regulator`

At an illustrative 80% regulator efficiency and 50 mJ delivered:

- **5 V down to 3 V:** C = **7.81 mF** effective.
- **10 V down to 4 V:** C = **1.49 mF** effective; requires suitable high-voltage parts/converters.

Both exclude tolerance, bias derating, ESR/transient limits and margin. They are much larger energy reservoirs than ordinary decoupling. For the 5-to-3 V case, charging from zero initially stores **97.7 mJ**, of which 62.5 mJ is accessible before reaching 3 V and 50 mJ reaches the load after conversion. The residual 35.2 mJ is unavailable to that converter; starting from a fully discharged device is more demanding than topping up an already charged reservoir. The separate illustrative 50% total-efficiency assumption must be validated including such unusable residual energy, not multiplied into the capacitor calculation a second time.

A fully battery-free device also needs an answer for timekeeping between shots; a one-shot capacitor cannot maintain the existing RTC indefinitely in darkness. A small RTC backup cell would preserve the current timestamp behavior even if capture power came from a generator.

## Recommendation

Keep battery power with the shutter acting as a physical power-on control for the present thin, fast-shutter camera. If mechanically powered operation is a desired product feature, investigate a **separate wind/squeeze/slide-to-charge action** after measuring complete capture energy. Use that measurement, including startup from zero and durable save, to specify mechanical work and storage capacitance. A stronger click alone is unlikely to bridge the gap without an unacceptable change in force and travel.
