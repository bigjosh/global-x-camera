# BMP thumbnail renderer

`thumbnail_bmp.c` renders a **128 × 156, 24-bit BMP** from a complete
1120 × 1364 packed MIPI RAW10 snapshot. The result is always **59,958 bytes**.
Call `gx_thumbnail_bmp_read()` with arbitrary byte offsets to stream it without
allocating a second image. Input begins at the first image pixel, excluding
the slot's magic and metadata. The caller owns the snapshot and its error
assessment; this helper performs no storage access or state mutation.

The renderer samples pixel centers, uses each sample's upper eight bits for all
three color channels, and emits bottom-up rows. It applies no gain, gamma or
auto-contrast; it is a small lossy preview, separate from the exact PNG16 export.
The portrait aspect ratio differs by less than 0.2% through integer sizing.
BMP layout follows Microsoft's [file header](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapfileheader)
and [bitmap header/stride](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader)
definitions.

The installed USB firmware reports thumbnail format
`0x3804`, length `GX_THUMB_SIZE`, width `GX_THUMB_WIDTH`, height
`GX_THUMB_HEIGHT`; GetThumb returns those exact bytes as the same photo's
resource, not a separately deletable object. **Native Windows WPD thumbnail
retrieval passed on the real camera**, including the final November 8 firmware.
This qualifies the WPD resource path, not every application's preview UI.
See the [qualification record](../evidence/2026-11-08-native-ptp/README.md).

```powershell
python -m unittest discover -s firmware/usb-ptp/thumbnail -p test_thumbnail.py -v
```

Four tests compile the portable C renderer with MinGW, independently check
every preview pixel, verify arbitrary chunk boundaries and bounds rejection,
and decode with native Windows WIC. They do not use a USB device.
