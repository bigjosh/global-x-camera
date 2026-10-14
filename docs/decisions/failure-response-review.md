# Failure response review

The user settled the complete response map on October 13, 2026, after first approving low-battery handling, the shutdown definition and preservation of prior photos. All cases below now have an accepted prototype policy. This records requirements; firmware, storage format, circuit changes and fault qualification remain to implement.

The [decision register](2026-10-13-project-baseline.md), [specification](../../spec.md), and [power study](../../power.md) govern existing requirements. Storage-full behavior, ignored busy presses and inactive shutter operation in USB mode are already settled. This review addresses failures and transitions beyond those decisions.

## Accepted response map

| Case | Failure or transition | Status |
|---|---|---|
| F-01 | Low battery detected at any point in the cycle | Approved: one red LED flash, abort to shutdown; another image requires a power cycle. |
| F-02 | Power collapses or is interrupted during capture/save | Retain data already written; mark allocation USED at save start and DONE only on successful completion. USED without valid DONE is occupied and possibly corrupt. Prior committed photos must be preserved. No automatic retake. |
| F-03a | Camera initialization fails or times out before exposure | Two red flashes, then shutdown. |
| F-03b | Exposure/frame capture fails, times out or yields an incomplete frame | Three red flashes, then shutdown. |
| F-04 | Photo storage is absent, unidentified or unresponsive | Four red flashes, then shutdown. |
| F-05 | Writing a new photo, enabled readback verification or final commit fails | Five red flashes, then shutdown; do not treat the image as successfully saved. |
| F-06 | An existing committed photo cannot be read reliably | On the host request, read/check the original image into RAM and return recoverable data with read warnings. Preserve the source; predictive media errors retire its whole slot from future writes. No relocation or automatic deletion. True transfer failures still report a USB error. |
| F-07 | RTC time or orientation data is unavailable or invalid | Save an explicit magic BAD value at capture time; omit the corresponding unavailable EXIF fields when generating photo files over USB. Save the image. |
| F-08 | Boot fails or firmware hangs/resets | No additional prototype indication or recovery mechanism selected. Firmware that cannot run cannot be relied upon to indicate or shut down. |
| F-09 | USB is inserted/removed during an operation | Allowed; no separate error code. Implement source transitions consistently with photo preservation and the existing inactive-shutter USB mode. |
| F-10 | Storage index/allocation metadata is unreadable or inconsistent | Six red flashes, then shutdown; preserve stored photos rather than automatically erase or rebuild destructively. |
| F-11 | An explicit erase fails or is interrupted | Report over USB. Erase is an explicit USB-only operation; a read/download itself never authorizes erasure. |
| F-12 | Exposure would start later than the 50 ms deadline | Resolve by deterministic design and qualification of the startup budget; no runtime error code or late-shot policy added. The ≤50 ms requirement remains. |

Red-coded capture failures abort to the approved shutdown state; another attempt requires a main-system power cycle and a fresh intentional press. Detected low battery at any cycle phase retains the one-flash policy, even though the final checklist abbreviated it to “before exposure.” Flash duration, spacing and detection thresholds remain engineering details. Indication requires adequate remaining power. These decisions do not add an automatic retry loop.

## Shutdown definition — approved

Shutdown means the **lowest attainable power state**, and the camera must undergo a **power cycle before taking another image**. A normal firmware wake or software reset does not satisfy this requirement. This concerns the main capture electronics; independently retained RTC backup does not need to lose power. With the current divider/HOLD circuit, a held button can keep the regulator enabled while the MCU remains in Standby until release. A fresh press is necessary for a new shot and must follow actual main-power removal/restart; button activity must not wake the existing shutdown session into another capture. Exact rail-discharge and rearming detection remain implementation work.

## F-01 Low battery detected at any point in the cycle — approved

**User decision:** “single flash of red led will indicate low battery at any point in the cycle and abort the cycle to the shutdown state.” The same approval defines shutdown as the lowest possible state attainable, requiring a power cycle before another image. This supersedes the narrower pre-exposure-only proposal.

**Required behavior:** when low battery is detected during startup, exposure, readout, saving or another part of the capture cycle, indicate it with **one red LED flash**, abort the cycle and enter shutdown. Do not automatically retry, resume capture after voltage recovery or take a replacement image in the same powered session. Preserve already committed photos and do not report an incomplete/unverified save as successful.

**Implementation boundaries:** the LED flash requires sufficient remaining power; it cannot be guaranteed if supply disappears before firmware can act. Thresholds, detection latency, flash duration and the circuit/firmware implementation remain unselected. The threshold/detection method must be qualified against the actual startup/capture/save load and the 50 ms exposure-start requirement for accepted shots. Any in-flight NAND operation must be handled according to the selected device's power-fail rules; do not interpret abort as a requirement to finish a full save with inadequate supply. Abrupt-loss behavior follows the separately approved F-02 policy below; its storage implementation remains open. Red indication is a hardware requirement to reconcile with the fitted prototype LED; no CAD change is implied.

## F-02 Abrupt power loss — approved

**Scope:** power disappears or collapses before firmware can reliably indicate low battery or complete an orderly abort. No LED indication is guaranteed in this case.

**User decision:** “yes, losing the current photo is ok as long as previously saved photos are preserved.” This accepts loss of the current in-progress photo; it does not permit damage to previously saved photos.

**Required response, refined by the complete checklist:** the current uncommitted image may be lost or corrupt, but bytes already written remain in NAND. Mark the allocated blocks/space **USED at the start of saving**, before writing the image payload; mark the image **DONE only after successful completion and required save checks**. On the next valid start, recover complete committed records and recognize **USED without valid DONE as occupied and possibly corrupt**. Do not automatically erase or recycle that space or present it as a normal complete photo. Preserve its recoverable contents until an explicit USB erase; whether to offer suspect images for host recovery is not yet specified. If the interrupted cycle's image was already validly committed, retain it too. Do not automatically resume the interrupted shot or take a replacement exposure during brownout/restart cycling; another image requires a valid main-system power cycle and a new intentional shutter press.

USED and DONE name **logical states**, not selected NAND bit values, atomic writes or an erase-block layout. Missing, torn or inconsistent records must conservatively prevent unsafe reuse of potentially occupied space and protect prior photos. The implementation must reconcile final-marker writing and verification: a failed commit/check cannot be advertised as a successful save. Full-image readback remains configurable, while required completion/status checks, integrity metadata and final commit-record verification remain mandatory.

**Implementation and qualification:** completion of the current save after sudden loss is not required. Preserving prior photos remains a firm requirement on storage layout, metadata updates, erase isolation and recovery. Do not assume commit markers alone protect existing data from every device-level interrupted-operation effect. Qualify the selected device/format with power-cut tests across image programming, metadata/commit updates and any block erase; verify prior photos remain readable and unchanged. Recovery, brownout-loop inhibition and the storage format are unimplemented. Any energy reserve needed to protect existing photos or meet device requirements remains an engineering matter; this approval only removes guaranteed completion of the current photo.

## F-03a Camera initialization failure — approved

**Scope:** the sensor does not respond or initialization/configuration fails or times out before exposure. Failure after exposure/frame start is F-03b; merely missing the exposure-start target without a hard camera fault is F-12.

**Approved response:** indicate the camera initialization fault with **two red LED flashes**, then enter the approved shutdown state. Require a main-system power cycle and a fresh shutter press for another attempt. Indication requires adequate power; detected low battery follows its already-approved one-flash policy.

**Tradeoff:** a transient initialization glitch costs that attempted shot; the proposed behavior avoids retry loops and an unexpectedly delayed exposure. Timeout values and LED timing remain to be defined and qualified.

## F-03b Frame capture failure — approved

Exposure/frame capture or readout failure receives **three red flashes**, followed by shutdown. This is distinct from a camera initialization failure (two flashes) and a storage readback failure (five flashes). Do not mark an incomplete capture as a successfully saved photo. Preserve previously committed photos.

## F-04 Storage unresponsive — approved

An absent, unidentified or unresponsive photo-storage device receives **four red flashes**, followed by shutdown. Storage full remains its separate settled condition: preserve photos and refuse new captures until an explicit erase frees space. No full-condition flash count is selected here.

## F-05 New-photo save failure — approved

A payload write, enabled readback check or final commit failure receives **five red flashes**, followed by shutdown. Preserve previous photos and retain any newly allocated incomplete record as USED/possibly corrupt. Disabling full-image readback does not waive required completion/status checks, integrity metadata or final commit-record verification.

## F-06 Existing photo unreadable — approved

**Refined October 14:** every USB host image-data request freshly reads the whole original NAND image into RAM and checks ECC/CRC-32C before export. Return the current recoverable image with filename/EXIF warnings distinguishing corrections from damaged data. Repeated reads may differ. Preserve original bytes and expected CRC; only host deletion removes the photo. Predictive media errors permanently retire the whole slot from new writes but do not block existing reads. No background image scans, relocation or refresh. True transfer failures still report errors. See the [accepted read policy](ecc-read-error-review.md).

## F-07 Time or orientation unavailable — approved

Save the image with an explicit magic **BAD** value for each unavailable/invalid metadata item at capture time. During USB file generation, omit the corresponding unavailable EXIF fields rather than invent time or orientation. Valid metadata can still be included. Sentinel encoding and the generated file format remain implementation details; metadata failure alone does not abort the photo.

## F-08 Boot failure or firmware hang — accepted prototype limitation

The user selected no additional response: “nothign we can do.” This records the prototype scope, not a claim that watchdogs or recovery hardware are impossible. No automatic restart, red code or guaranteed controlled shutdown is added. In particular, firmware hung while driving HOLD can leave the main supply enabled; the present circuit does not guarantee a bounded drain in that case. Any actual power interruption still follows F-02.

## F-09 USB connection changes — allowed

The user accepts USB insertion/removal during an operation (“fine”), with no special error code. USB source detection and transition behavior remain to implement; acceptance does not establish uninterrupted power or successful completion of every transfer. Preserve committed photos, use F-02 if power disappears, and follow F-11 for interrupted explicit erase. USB mode keeps the shutter inactive and the battery converter disabled with reverse-power isolation. No automatic exposure or erase is triggered by a connection change.

## F-10 Damaged storage index or allocation metadata — approved

Indicate **six red flashes**, then shutdown. Preserve existing data; do not treat uncertain allocation as free space or automatically format/erase the device to recover capture capability. Distinguish a recognizable interrupted USED/not-DONE record (F-02) from damaged allocation information that cannot safely be interpreted. Exact validation and recovery layout remain implementation work.

## F-11 Explicit erase failure or interruption — approved

Report failure over USB. Erase can be requested only in USB mode and must be explicit; the user's wording “over USB reads” does not change the previously settled rule that reading/downloading alone does not erase photos. If disconnection prevents immediate reporting, detect and report unresolved erase state on a subsequent USB session. Do not falsely report successful completion. Interrupted-erase detection and metadata recovery remain to implement.

## F-12 Exposure-start deadline — design and qualification requirement

The **≤50 ms button-press-to-start-of-exposure requirement from fully off remains binding**. Budget startup, boot and initialization deterministically during design, then verify the saved frame's actual exposure start on hardware across the intended conditions. The user explicitly declines a runtime late-exposure error case; no new blink code, timeout-triggered abort or permission for a late shot is selected. Compliance has not yet been demonstrated.

## Evidence and remaining work

The October 13 user checklist supplied: one red flash for low battery; USED at save start/DONE at completion; two/three red flashes for initialization/capture; four for storage unresponsive; five for new-photo save failure; USB reporting for an unreadable existing photo; BAD metadata with EXIF omitted at USB read; no boot/hang response; accepted USB connection changes; six red flashes for damaged index/allocation; USB reporting for explicit erase failure; and a design-time rather than runtime treatment of the 50 ms deadline. The case numbers above preserve the earlier review IDs, splitting user item 3 into F-03a/F-03b.

The response-policy checklist is complete. Remaining work is the storage record/marker format and conservative recovery, exact NAND geometry and retention qualification, LED hardware/timing, fault detection, safe power transitions and firmware implementation. None of these documentation decisions constitute completed circuit changes or successful fault tests.
