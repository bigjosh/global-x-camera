# Host verification decisions

## 2026-11-08  Qualify through native WPD without replacing the USB class driver

**Why:** the requested product behavior is ordinary host browse, download and
explicit deletion. Testing through the Windows class driver exercises the
same transport family used by Explorer and avoids making a custom bulk client
appear to prove native host support. Exact device/object arguments prevent a
newly connected unrelated portable device from becoming the test target.

**Rejected:** installing WinUSB/libusb over the PTP interface for primary
qualification; automatically opening the first enumerated device; treating
WPD Delete's `S_FALSE` as success; silently overwriting download evidence.

**Evidence:** `wpd_camera.cpp`, `run_wpd.py`, six passing offline tests in
`test_host_offline.py`, and the primary links in `protocol-review.md`. Native
MSVC compilation and local Windows WIC decoding passed November 8. No device
enumeration, USB operation or bench mutation was performed by this preparation.

## 2026-11-08  Cancel pending reads through the same WPD instance and bound cleanup

**Why:** cancelling only after a completed stream read can miss all actual USB
activity. The host tool now starts an independent MTA cancellation worker,
times GetStream/Read scopes, and calls the same free-threaded WPD instance while
a scope is active. The evidence distinguishes a host API attempt from verified
wire cancellation because completion/prefetch races remain possible.

**Rejected:** opening a new device instance to cancel another session's I/O;
claiming successful wire cancellation from `Cancel()==S_OK` alone; detaching a
worker that could outlive its COM interfaces; waiting unboundedly for a stuck
Cancel. A five-second worker-join timeout exits only the verification client
with status124 and explicitly leaves device idleness unproven.

**Evidence:** `AsyncCancel` in `wpd_camera.cpp`, `--cancel-ms`, ten passing
offline tests in `test_host_offline.py`, and
`tmp/usb-ptp-host/async-selftest-20261108.jsonl`. The fake stalled-worker test
exercises the bounded exit without opening any device. Live cancellation and
recovery qualification belong to the root bench campaign.
