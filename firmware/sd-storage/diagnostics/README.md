# Offline four-bit SD trace inspection

`decode_sd4.py` reads Saleae binary exports without accessing an instrument.
It preserves invalid command/data packets, checks each DAT lane's CRC16 and
reports DAT0 write-status candidates. It requires Python and NumPy.

Example with the October 25 probe map:

```powershell
python firmware/sd-storage/diagnostics/decode_sd4.py PATH_TO_BINARY_EXPORT --offset-ns 0 --out decode-zero.json
python firmware/sd-storage/diagnostics/decode_sd4.py PATH_TO_BINARY_EXPORT --offset-ns -4 --out decode-early.json
python firmware/sd-storage/diagnostics/decode_sd4.py PATH_TO_BINARY_EXPORT --offset-ns 4 --out decode-late.json
python -m unittest discover -s firmware/sd-storage/diagnostics -p 'test_*.py'
```

Optional `--start-s` / `--end-s` bound analysis of long free-running clocks.
Compare offsets explicitly; never select only the offset that passes.
Partial packets interrupted by CMD12 and extra threshold crossings can defeat
simple framing. A CRC-valid analyzer decode does not establish analog margins,
and an invalid decode does not by itself prove the card received bad bytes.
See the [observed limitations and resistor experiment](../../capture-raw/evidence/2026-10-25-sd25-crc/POST_RESISTOR.md).
