# Native Windows photo access verification

`wpd_camera.cpp` exercises the installed Windows Portable Devices (WPD) driver.
It does not replace the camera driver, touch ST-LINK, or send raw USB transfers.
Run it only when the bench owner has put the camera in USB mode.
Windows supplies PTP support through WPD's class driver.
[Microsoft driver overview](https://learn.microsoft.com/en-us/windows-hardware/drivers/portable/wpd-drivers-overview).

## Build and offline checks

From the repository root:

```powershell
./firmware/usb-ptp/host/build.ps1
python -m unittest discover -s firmware/usb-ptp/host -p test_host_offline.py -v
```

The script discovers installed MSVC and Windows SDK paths, changes only its
process environment, and writes `tmp/usb-ptp-host/wpd_camera.exe`. It runs only
the offline self-test. On November 8, MSVC 14.44.35207 / SDK 10.0.26100.0 built
cleanly and all ten offline tests passed, including asynchronous cancellation
scheduling, early disarming, and bounded cleanup of a stalled fake Cancel.
Local WIC decoded a synthetic PNG16
and the actual photo-backend fixture as native 16-bit gray, preserving the
`sample << 6` values. This proves local decoding, not USB interoperability.

## Explicit device operations

Use the exact WPD ID and object IDs returned by the preceding reads; they are
strings, not the firmware's numeric PTP handles. No action picks the first
device automatically.

```powershell
$tool = './tmp/usb-ptp-host/wpd_camera.exe'
& $tool devices
$device = '<exact id from devices>'
& $tool list --device $device --recursive
& $tool info --device $device --object '<photo object id>'
& $tool get --device $device --object '<photo object id>' --out 'D:/Github/global-x-camera/tmp/photo.png'
& $tool decode --file 'D:/Github/global-x-camera/tmp/photo.png'
& $tool thumbnail --device $device --object '<photo object id>' --out 'D:/Github/global-x-camera/tmp/thumb.bmp'
& $tool delete --device $device --object '<photo object id>' --confirm-object '<same photo object id>'
```

Download creates a new `.partial` file, preserves partial bytes on failure,
checks the advertised size, then publishes the complete file without replacing
an existing destination. It uses `WPD_RESOURCE_DEFAULT`; thumbnail uses
`WPD_RESOURCE_THUMBNAIL`. Delete accepts only an image content type and sends one
nonrecursive deletion, checking the overall and per-object results. In
particular, `S_FALSE` is not successful deletion. Enumeration and transfer use
the standard [WPD content APIs](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/enumerating-content)
and [deletion result contract](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/deleting-content-from-the-device).

Each invocation emits UTF-8 JSON lines with native monotonic microsecond
timestamps and Windows thread IDs. GetStream and every Read also have paired
start/end records, including byte count and HRESULT. For a bounded run and
preserved evidence:

```powershell
python firmware/usb-ptp/host/run_wpd.py --timeout 90 --log tmp/usb-list-01.jsonl -- list --device $device --recursive
```

The wrapper records executable SHA-256, exact arguments, results, duration and
download SHA-256. Its log file must be new. A timeout kills only the child client;
it neither retries nor resets the camera and does not establish card idleness.
Wrapper output timestamps are receipt times. The native payload's `mono_us`
timestamps are taken at each API/event boundary, not at receipt; neither is a
USB packet timestamp.

`get --cancel-after N` calls WPD `Cancel()` after a completed read reaches the
threshold and retains `.partial`. This exercises abandoned-stream cleanup but
does not prove an in-flight USB Cancel request occurred: the driver may already
have prefetched the whole object. Firmware logs or a bus trace must establish
actual wire-level cancellation.

For cancellation while an operation is pending:

```powershell
python firmware/usb-ptp/host/run_wpd.py --timeout 30 --log tmp/usb-cancel-01.jsonl -- get --device $device --object '<photo object id>' --out 'D:/Github/global-x-camera/tmp/cancel-01.png' --cancel-ms 100
```

`--cancel-ms` accepts 1 through 60000 milliseconds and cannot be combined with
`--cancel-after`. A second MTA-initialized thread calls `Cancel()` on the **same
PortableDeviceFTM instance** used by the download. It starts its deadline at
GetStream, then requires an active GetStream/Read scope before issuing the
request. Microsoft documents separate-thread cancellation of a pending WPD
command; a separately opened device instance would address a different I/O
scope. [SendCommand cancellation](https://learn.microsoft.com/en-us/windows/win32/api/portabledeviceapi/nf-portabledeviceapi-iportabledevice-sendcommand),
[Cancel scope](https://learn.microsoft.com/en-us/windows/win32/api/portabledeviceapi/nf-portabledeviceapi-iportabledevice-cancel).

Logs distinguish timer attempt, the pending API's cancellation HRESULT, and
whether that scope remained active when Cancel returned. A race or driver
prefetch can still prevent wire-level cancellation; the tool deliberately
leaves `wire_cancel_proven:false`. Correlate firmware Cancel counters or a USB
trace. The attempt retains `.partial`, even if the pending API returned
success. A completed download before the deadline is saved but reports a missed
cancellation window and exits nonzero.

Cleanup disarms and joins the worker. If Cancel itself has not returned after
five seconds of join waiting, the client exits 124 and records that device
idleness is unknown; it never detaches a thread against released COM interfaces,
resets a device, or changes power. The wrapper timeout also bounds a pending
Read that does not respond to Cancel. Afterward, use a new exact-device client
to list and download again. Close/Open demonstrates session recovery, not a
physical USB disconnect/reconnect.

## Qualification sequence

1. Enumerate the exact camera, list objects and preserve their IDs/metadata.
2. Download at least two photos, run native WIC decode and independently compare
   all exported pixel samples against their source RAW slots.
3. Download the same photo again; inspect a fresh firmware storage-read counter.
4. Fetch a thumbnail if advertised. Check content and resource format.
5. Delete one disposable image. List again, verify that it disappeared, verify
   other photos still download unchanged, reconnect and repeat the checks.
6. Exercise interrupted downloads/reconnects separately and verify the next
   request succeeds. Do not interpret timeout as proof of a failed deletion.

These are prepared checks, not a record that hardware qualification passed.
The root campaign's evidence/checkpoint owns actual results.
