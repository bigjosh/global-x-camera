# Failure response review

Work through these cases one at a time and record the user's chosen response. The user requested individual failure policies instead of adopting the preceding general failure-response proposal. F-01, F-02 and the shutdown definition below are approved; other responses remain pending.

The [decision register](2026-10-13-project-baseline.md), [specification](../../spec.md), and [power study](../../power.md) govern existing requirements. Storage-full behavior, ignored busy presses and inactive shutter operation in USB mode are already settled. This review addresses failures and transitions beyond those decisions.

## Discussion queue

| Case | Failure or transition | Status |
|---|---|---|
| F-01 | Low battery detected at any point in the cycle | Approved: one red LED flash, abort to shutdown; another image requires a power cycle. |
| F-02 | Power collapses or is interrupted during capture/save | Approved: current uncommitted photo may be lost; previously saved photos must be preserved. Recover valid committed records on next start and do not automatically retake. |
| F-03a | Camera initialization fails or times out before exposure | Next discussion; proposed two red flashes, shutdown and no automatic retry. |
| F-03b | Exposure/frame readout fails, times out or yields an incomplete frame | Pending; discuss separately from initialization and from optional payload readback verification. |
| F-04 | Photo storage is absent, unidentified or unresponsive | Pending; no usable device is different from the already-settled storage-full condition. |
| F-05 | Writing a new photo, readback verification or final commit fails | Pending; consider bounded retries of the same buffered image, spare allocation and definitive failure indication. |
| F-06 | An existing committed photo cannot be read reliably | Pending; distinguish correctable errors from unrecoverable data and preserve other photos. |
| F-07 | RTC time or orientation data is unavailable or invalid | Pending; metadata failure need not have the same policy as image failure. Discuss each separately if appropriate. |
| F-08 | Boot fails or firmware hangs/resets | Pending; recovery may require hardware or early-boot support rather than application code. |
| F-09 | USB is inserted/removed during an operation | Pending; distinguish saving, download and explicit erase, and account for source transitions. |
| F-10 | Storage index/allocation metadata is unreadable or inconsistent at startup | Pending; the device may identify correctly while the usable-photo catalog is damaged. Distinguish recovery, read-only access and refusing capture. |
| F-11 | An explicit erase fails or is interrupted | Pending; distinct from saving a new photo or the already-approved decision to erase only explicitly. |
| F-12 | Exposure cannot start within the 50 ms deadline despite no hard camera fault | Pending; decide whether a late photo is preferable to refusing that shot. |

## Shutdown definition — approved

Shutdown means the **lowest attainable power state**, and the camera must undergo a **power cycle before taking another image**. A normal firmware wake or software reset does not satisfy this requirement. This concerns the main capture electronics; independently retained RTC backup does not need to lose power. With the current divider/HOLD circuit, a held button can keep the regulator enabled while the MCU remains in Standby until release. A fresh press is necessary for a new shot and must follow actual main-power removal/restart; button activity must not wake the existing shutdown session into another capture. Exact rail-discharge and rearming detection remain implementation work.

## F-01 Low battery detected at any point in the cycle — approved

**User decision:** “single flash of red led will indicate low battery at any point in the cycle and abort the cycle to the shutdown state.” The same approval defines shutdown as the lowest possible state attainable, requiring a power cycle before another image. This supersedes the narrower pre-exposure-only proposal.

**Required behavior:** when low battery is detected during startup, exposure, readout, saving or another part of the capture cycle, indicate it with **one red LED flash**, abort the cycle and enter shutdown. Do not automatically retry, resume capture after voltage recovery or take a replacement image in the same powered session. Preserve already committed photos and do not report an incomplete/unverified save as successful.

**Implementation boundaries:** the LED flash requires sufficient remaining power; it cannot be guaranteed if supply disappears before firmware can act. Thresholds, detection latency, flash duration and the circuit/firmware implementation remain unselected. The threshold/detection method must be qualified against the actual startup/capture/save load and the 50 ms exposure-start requirement for accepted shots. Any in-flight NAND operation must be handled according to the selected device's power-fail rules; do not interpret abort as a requirement to finish a full save with inadequate supply. Abrupt-loss behavior follows the separately approved F-02 policy below; its storage implementation remains open. Red indication is a hardware requirement to reconcile with the fitted prototype LED; no CAD change is implied.

## F-02 Abrupt power loss — approved

**Scope:** power disappears or collapses before firmware can reliably indicate low battery or complete an orderly abort. No LED indication is guaranteed in this case.

**User decision:** “yes, losing the current photo is ok as long as previously saved photos are preserved.” This accepts loss of the current in-progress photo; it does not permit damage to previously saved photos.

**Required response:** the current uncommitted image may be lost. Preserve previously committed photos. On the next valid start, recover valid complete committed records and ignore incomplete writes. If the interrupted cycle's image was already validly committed, retain it too. Do not automatically resume the interrupted shot or take a replacement exposure during brownout/restart cycling; another image requires a valid main-system power cycle and a new intentional shutter press.

**Implementation and qualification:** completion of the current save after sudden loss is not required. Preserving prior photos remains a firm requirement on storage layout, metadata updates, erase isolation and recovery. Do not assume commit markers alone protect existing data from every device-level interrupted-operation effect. Qualify the selected device/format with power-cut tests across image programming, metadata/commit updates and any block erase; verify prior photos remain readable and unchanged. Recovery, brownout-loop inhibition and the storage format are unimplemented. Any energy reserve needed to protect existing photos or meet device requirements remains an engineering matter; this approval only removes guaranteed completion of the current photo.

## F-03a Camera initialization failure — next discussion

**Scope:** the sensor does not respond or initialization/configuration fails or times out before exposure. Failure after exposure/frame start is F-03b; merely missing the exposure-start target without a hard camera fault is F-12.

**Proposed response, not yet approved:** indicate the camera initialization fault with **two red LED flashes**, then enter the approved shutdown state. Do not automatically retry initialization in that powered session. Require a main-system power cycle and a fresh shutter press for another attempt. Indication requires adequate power; detected low battery follows its already-approved one-flash policy.

**Tradeoff:** a transient initialization glitch costs that attempted shot; the proposed behavior avoids retry loops and an unexpectedly delayed exposure. Timeout values and LED timing remain to be defined and qualified.

**User decision:** pending.
