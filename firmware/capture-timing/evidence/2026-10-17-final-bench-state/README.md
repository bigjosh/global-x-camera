# Final bench state — October 17, 2026

The selected native RAW10 v25 firmware was restored, programmed and verified, then passed its fifth cold start. The first 64 KiB SHA-256 is `c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`. Final capture: `tmp/bringup/capture-opt-v25-raw10-restore-05/cold`.

The JS110 controller stopped normally at 07:44:00 UTC, restoring its initial automatic range (128). The target remained powered. A separate 23.689312-second Saleae capture spanning controller release showed all three monitored board rails, NRST and PD0 remained high. The measured ranges were auxiliary 3.3 V: 3.268–3.309 V; target 5 V: 4.811–4.858 V; main VDDIO: 3.271–3.287 V. These probes do not directly observe every MCU or camera supply.

A subsequent read-only HOTPLUG debugger connection succeeded at 3.28 V, reading expected capture-trace magic `0x43545031` from `0x343F0000`. The MCU remains awake after a completed capture, the sensor has been stopped by the capture harness, and no experiment script owns either instrument. Logic 2 remains available as the Saleae API backend. Boot jumpers remain in normal flash-boot positions; wiring is unchanged.

Archived files preserve exact source bytes. Full analog and Saleae recordings remain local; their identities are recorded in `archive-index.json`. No OTP/fuses/lifecycle settings or permanent board modifications were made.
