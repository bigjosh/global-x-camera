# Series-resistor comparison

Offline reanalysis of completed recordings; no hardware operations.

| Run | First peak (A) | Secondary peak (A) | Secondary time (ms) | Exposure (ms) | Cycle (ms) | Energy after 5 ms (mJ) | Full energy incl. unqualified startup (mJ) |
|---|---:|---:|---:|---:|---:|---:|---:|
| No resistor 01 | 6.1676 | 1.3124 | 1.4855 | 24.7695 | 436.8875 | 158.7826 | 160.7812 |
| No resistor 02 | 6.0825 | 1.3108 | 1.4905 | 24.8975 | 437.7170 | 159.9739 | 161.9784 |
| No resistor 03 | 6.1397 | 1.3108 | 1.4910 | 24.9910 | 460.6000 | 169.4533 | 171.4612 |
| 2.2 ohms 01 | 1.7425 | 1.0509 | 1.5060 | 24.5840 | 445.5010 | 168.4246 | 170.8472 |
| 2.2 ohms 02 | 1.7441 | 1.0524 | 1.5065 | 25.1220 | 564.5770 | 222.1859 | 224.6150 |
| 2.2 ohms 03 | 1.7379 | 1.0493 | 1.5065 | 25.2675 | 647.5795 | 263.3824 | 265.7959 |

All six runs must have a unique eleven-marker train and one bounded exposure mirror. No image-readback claim is made here.

| Median metric | No resistor | 2.2 ohms | Change |
|---|---:|---:|---:|
| first_250us_peak_A | 6.13973 | 1.74250 | -71.62% |
| secondary_250us_to_5ms_peak_A | 1.31083 | 1.05089 | -19.83% |
| post5ms_energy_mJ | 159.97388 | 222.18587 | +38.89% |
| full_cycle_energy_mJ_unqualified_startup | 161.97840 | 224.61497 | +38.67% |
| onset_to_plateau_ms | 437.71700 | 564.57700 | +28.98% |
| first_exposure_mirror_ms | 24.89750 | 25.12200 | +0.90% |
| post5ms_peak_1ms_mean_mA | 126.27148 | 132.57721 | +4.99% |
| post5ms_nominal_R_heat_mJ | 6.08736 | 8.38680 | +37.77% |

Phase windows overlap and must not be added. Per-run phase timings/energies and sample identities are in summary.json.

Nominal I²R heat is calculated from recorded current, not independently measured resistor temperature/power or added source energy. The baseline value is counterfactual. Converter behavior and LDO losses can change.

Source-side voltage does not measure DUT input after the resistor or downstream MCU rails. This analysis cannot qualify rail droop/rise times, minimum boot voltage, or physical unclipped startup extrema.

No LiPo/LTC/battery loss is included. SD service-time variation prevents assigning total-energy differences solely to the resistor.
