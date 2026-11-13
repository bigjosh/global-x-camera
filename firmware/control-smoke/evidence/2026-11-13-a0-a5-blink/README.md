# A0-A5 standalone 2 Hz FLASH diagnostic

Installed November13,2026 after the user confirmed all external header wiring
removed, direct5V power and ST-LINK attached. Left running for the user's
external A3 comparison. No camera/storage/USB/Standby operation occurs.

Allsix digital inputs/outputs alternated LOW/HIGH in firmware telemetry,
100,000,116-124 DWTcycles per half-period at the inherited400MHz clock.
External waveform/amplitude is not measured. UART recovery passed9valid/0bad
pulses, exactpark0x3418078C; a final normal poweredreset resumed blinking.
COM8 closed, BREAK released, no helper or instrument client remains active.

Full physical sector0 readback matches the candidate. The following64KiB and
4KiB match backups. Both original firmware sectors matched the November9
camera package before programming, establishing no unexpected firmware change.
Only the firsttwo4KiB subsectors changed;32pages programmed. Originalsector0
is preserved in blink-backup0/readback.bin; sector1 was not programmed.

- Candidate prefixSHA256:6d4deeee7b248f7e2d71a79d9bd5dcfd36bce87658138918c88b7dc87efa0869
- Sector0SHA256:28257715f614d42048618847be4edb1f13564edb47b0f265efb38785fa63d23a
- Blinker executable624bytes. UARTguard/faultvectors/earlyPA2hook byte-exact.
- Offline pinreview:16,384randomized cases/all64pin combinations passed.
- PROOFword6 interval is sampled independently of its sequence-protected peers.

See source/gpio-blink.md for mapping and telemetry; blink-final-state.json
for handoff. This temporary image intentionally toggles HOLD/A3. Restore
normalcamera firmware before reconnecting pots or the latch. Restoration must
use fresh exact blink UARTrecovery and normal bounded NORmaintenance checks.
No cold powercycle or external analog voltage qualification is claimed.
