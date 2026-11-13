# User's unpowered resistance comparison

The user reports **all A contacts measure approximately1 megohm to GND**
after the requested removal of direct5V and ST-LINK power. Exact readings,
meter model and lead polarity were not recorded. This is consistent with
the nominal470k+560k conditioning branches and does not show an A3-specific
hard short. It does not exclude a damaged output driver or open MCU-to-PCB
connection.

Next requested measurement, still unpowered: resistance directly between
A3/CN4.4 and CN3.34, expected near0ohm through fittedSB6. Result pending.
No instrument or firmware action accompanied this observation. User owns
the unpowered bench; standalone all-output FLASH blinker remains installed.
