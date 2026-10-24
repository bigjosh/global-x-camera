# Final powered-on checkpoint

The 64 KiB NOR readback immediately before the last normal boot matches the exact v66c sector. Earlier UART recovery also passed its exact early-park guard. The last cold-cycle recording ended cleanly at **2026-10-24 02:39:05.697298 UTC**, restoring JS110 current range 128 and leaving the target powered. Final measured-branch statistics were **4.892853 V and 8.069970 mA**.

Ten complete pulses were recorded. The original strict width decoder still failed. No UART recovery, SBF check, or photo readback followed this final cycle, so its Standby state and expected IMG00072.PNG are **not independently verified**. The preceding three cycles have separate qualification records. These final sample statistics are not an energy calculation or isolated MCU current measurement.

[final-state.json](final-state.json) distinguishes archived record-derived fields from the hardware owner's report that COM8 was closed, BREAK released, all helper owners inactive, and no subsequent recovery/readback occurred. The original recorder result and limitations remain unchanged. Run `python ../verify_final.py` to verify all 51 compact indexed files, exact pre-boot NOR identity, final statistics, and these restricted claims. Raw recordings and imagery are excluded.
