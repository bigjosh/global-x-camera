# Instrument access

Use APIs only for the Joulescope JS110 and Saleae Logic Pro 8. The user requested this on October 16, 2026. Do not use computer-use tools, screenshots, mouse clicks, or keyboard automation to operate these instruments unless the user changes this preference.

- Saleae: use `saleae.automation` through the existing Logic 2 server on localhost port 10430. Logic 2 remains the instrument backend; API-only does not mean the application can be closed. Reuse the running instance and save captures and exports programmatically.
- Joulescope: use `pyjoulescope_driver` directly. Only one client should own the device. If the GUI owns it, use a documented release mechanism if available, or request the minimum manual release; do not silently revert to computer use or force-terminate an application with unsaved data.
- Preserve instrument settings and target power during ownership changes. The existing JS110 helper opens in `restore` mode and preserves its starting current range. A successful API command is not proof of physical power restoration: verify the measured rails.
- Use the verified CN8 supply route for automated cycling: CN8 USB → CN9.3 → JS110 IN+ → OUT+ → CN9.2, all CN9 shunts absent. The old CN9.1/ST-LINK supply route tripped on reconnection. Three recorded CN8 cycles booted autonomously on October 17 after an initial stuck NRST was released with one documented ST-LINK hardware-reset pulse. Do not silently add debugger resets to a standalone timing experiment. Check actual rail discharge, restoration and marker edges every run.

See [the boot timing workflow](firmware/boot-timing/README.md), [current bench evidence](firmware/boot-timing/bench-results-2026-10-17.md), and [the earlier source limitation](firmware/boot-timing/bench-results-2026-10-16.md).
