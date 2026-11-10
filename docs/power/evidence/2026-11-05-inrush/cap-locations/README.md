# Input capacitor locator study

Offline source review only; neither part was modified and no instrument was accessed.

| Part | Side / center in ST PCB coordinates | Fitted C02 part | PCB pad nets |
|---|---|---|---|
| C14 | Top, X20.0660/Y111.2796mm, rotation90 | 220µF6.3V X5R ±20%,1206, Murata GRM31CR60J227ME11 | pin1 target5V/net380; pin2 GND/net358 |
| C17 | Bottom, X16.4084/Y23.2918mm, rotation180 | 10µF25V X5R ±10%,0805, Yageo CC0805KRX5R8BB106 | pin1 GND/net358; pin2 target5V/net380 |

`c14-location.png/.svg` and `c17-location.png/.svg` show the actual ST assembly vectors with independently verified body rectangles. Each face is viewed directly with the ST-LINK end at the top; flip left-to-right for the underside. C14 is between the now-removed D2/R23 sites. C17 is immediately below the removed U42 footprint, distinct from C155 at its left. Both capacitors are non-polar; pin labels identify PCB nets, not polarity. The output `locations.json` retains geometry, source hash and ODB++ pin records.

Sources: local official `docs/prototype/nucleo-assembly/mb1940-c02-assembly.pdf`, C02 BOM, manufacturing pick/place and ODB++ component records under `tmp/hardware-review/nucleo-modifications/`. Both fitted statuses were verified against the C02 BOM; generic manufacturing placement does not itself establish population.

## Shutdown qualification consequence

C14 is on the common target5V input bus, upstream of main, AON and auxiliary supply branches. Reducing it changes available energy and source impedance for all those branches. It is not an isolated main-only hold-up capacitor, so its value alone does not prove correct relative rail timing.

[AN5967 Rev6, section3.5](https://www.st.com/resource/en/application_note/an5967-getting-started-with-hardware-development-for-stm32n6-mcus-stmicroelectronics.pdf) requires auxiliary supplies to discharge below0.6V before main supplies leave their operating range. It also constrains VDD/AON threshold timing and their relative voltage. A smaller C14 therefore needs startup and shutdown rail requalification, including source removal and any planned RUN/HOLD cutoff. Checking only successful capture or total input current cannot establish these rail relationships.

When power is cut only after verified Standby and auxiliary rails have already discharged, less input hold-up may be acceptable; this is an inference requiring actual rail measurements, not an existing proof. C17 also remains on the shared5V bus after U42 removal but represents only10µF nominal. Removing C155 does not remove a5V input charge load once U42 is absent, because it is on U42's isolated output net.

Rebuild from repository root with the project Python and `tmp/bringup/inrush-20261105/cap-locations/build_cap_locators.py`. The script inserts the existing local PyMuPDF package path and writes only this directory.
