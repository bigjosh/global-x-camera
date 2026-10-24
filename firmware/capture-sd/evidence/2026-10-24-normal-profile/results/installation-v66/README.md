# v66c installation

The programmer completed all changed blocks, reported successful cleanup and
no pending operations. The full 64 KiB host readback matches the exact archived
v66c sector. The following 4 KiB matches the earlier pre-installation bytes.
See [verified-installation.json](verified-installation.json) and the indexed
original CLI/status/diagnostic records.

These checks establish programming and readback identity. Boot, capture, image
readback and Standby qualification are separate results. No image or raw
instrument stream is included. Run `python verify_installation.py` from the
parent results directory to replay these checks.
