# Exposure/ASA firmware reconciliation — November 14

The working branch was fast-forwarded from `7ca6e634` to upstream
`9f1595865f54c26d89f5713d3c9fd9df61222259`. Three new commits add the
release workflow, a knob implementation, and its subsequent ADC fix/release.
Pre-existing work was preserved in named stash
`d0609865185bee49eb8fded990ecdbea20f56289`, plus a working-file ZIP and binary
patch under `tmp/review-knobs-20261114/`. The stash is retained as a recovery
copy. The review did not operate instruments, install firmware, publish a
release, or change the existing test-card contents.

**Recommendation:** consolidate around our November13 source-built controls
path, retaining Claude's real-ST-HAL test model, portability improvements and
release packaging. The published upstream binary does not yet implement the
agreed physical controls. Our candidate also remains hardware-untested; this
review does not qualify either image for normal use.

## What exists now

The [GitHub release](https://github.com/bigjosh/global-x-camera/releases/tag/knobs-2026-11-14)
is **published as a prerelease, not a draft**, at17:07:40UTC on November14.
Its tag points to `9f159586`; both uploaded sector digests match the committed
release. The release correctly says it has not run on hardware. Repository
state still identifies the previous D8 package as last installed; no fresh
physical firmware identity was read in this review.

| Behavior | Agreed/local controls candidate | Claude upstream prerelease |
|---|---|---|
| Exposure direction | CCW longer; invert measured exposure ADC | Higher ADC means longer, therefore CW longer on this knob |
| Exposure range | Continuous logarithmic1–500ms | Approximately0.500–484.254ms |
| ASA control | Four sectors100/200/400/800 →1×/2×/4×/8× | Many intermediate analog-gain settings from a33-point table |
| ADC endpoints | Sample LOW and both HIGH references each boot | Fixed120/3720 clipping thresholds |
| Maximum analog gain | Set/read back MAX_AG_CODED28 before manual configuration | Request manual code28 without changing the default maximum24 |
| Applied sensor settings | Compare actual exposure, line/frame/margin and analog/digital gain | Remove fixed1428-line assertion without a replacement requested-value check |
| Knob failure | Initialization error indication and shutdown | Silently use approximately10.98ms/1× |
| Photo settings | CKN1 record in existing first-sector metadata; USB comment | Intentionally deferred |
| D8 and UART recovery | Preserved; USB-selected HOLD LOW | Preserved; USB-selected HOLD LOW |
| Hardware qualification | Not installed/qualified | Not installed/qualified |

Our frozen package is
[2026-11-13-knob-controls](../../firmware/usb-ptp/evidence/2026-11-13-knob-controls/README.md).
Claude's frozen package is
[2026-11-14-knobs](../../firmware/usb-ptp/evidence/2026-11-14-knobs/README.md).
Neither frozen binary was changed by reconciliation.

## Findings

### P1 — The exposure knob turns the wrong way for the calibrated hardware

`firmware/usb-ptp/knob_map.h` passes increasing exposure ADC values into an
increasing exposure curve. The live diagnostic measured CW3840 and CCW≈0;
we explicitly selected counterclockwise for longer exposure and printed the
labels accordingly. The ASA potentiometer has the opposite electrical
polarity, so applying one direction to both does not work.

**Recommended correction:** retain our exposure inversion and positive ASA
mapping. No rewiring is needed. Evidence is the
[three-position live calibration](../../firmware/control-smoke/evidence/2026-11-13-dual-knobs/README.md).
Those points establish direction and approximate taper, not exact angular
calibration.

### P1 — The upstream path does not enable the requested8× analog gain

The upstream reader writes manual gain up to code28 but does not change
`MAX_AG_CODED` at0x0960 or read back applied gain at0x0068. The sensor's
documented default limit is code24/4×, and the limit applies to manual as well
as automatic exposure. A request above that limit can be clipped while the
normal capture still reports success. This is a documented configuration
problem, not a measured assertion that this particular board clipped a photo.

**Recommended correction:** keep our explicit maximum28 write/readback and
post-frame applied-gain validation. See ST's
[UM2602, sections14.7/14.7.5 and Table51](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf).
ASA numbers remain a provisional label convention, not calibrated ISO.

### P2 — The exposure and gain scales do not match the selected labels

At1236pixels/line and160.8MHz, the upstream65–63000 coarse-line range is
499.627µs–484253.731µs. Our selected range is1ms–500ms, and the updated
exposure disc ends at reciprocal `2` (1/2second). Its ASA dividers denote
four discrete1×/2×/4×/8× sectors, not a continuous gain curve.

**Recommended correction:** retain our logarithmic exposure curve and four
ASA sectors. Constant line length1280 permits the half-second endpoint with
the existing2000-line reserve:62813coarse lines, frame64813, nominal
500003.98µs. This increases line/readout time3.56% versus1236 and still needs
hardware qualification. Keeping1236 instead requires a different frame-margin
decision or an honestly labeled shorter maximum.

### P2 — Silent fallback and removed validation can disguise incorrect settings

The upstream selector records knob failure in RAM and continues with the old
fixed exposure/gain. Its `exposure_gate.py` also changes the receiver's
conditional exposure check to an unconditional branch, using four unreachable
bytes to retain the prior CRC. The checksum-preserving patch is narrowly
checked, but it removes the old assertion without checking applied settings
against the requested ones. Successful LED/capture behavior therefore does
not prove that either knob took effect.

**Recommended correction:** use the rebuilt receiver's requested-versus-applied
checks and explicit configuration-failure path. If silent fallback is desired
instead, it should be an explicit policy choice with a visible indication and
saved metadata. A normal LED sequence alone, as suggested by the release
smoke-test instructions, cannot validate this feature.

### P1 — The release's timeout instructions can interrupt unfinished programming

`release/knobs-2026-11-14/RELEASE_NOTES.md` tells the operator to run
`nor.py read` and retry after a write failure or timeout. That reader halts
the MCU and replaces its helper. A host timeout, however, can leave the
original programming helper running; some failure states also leave the
NOR/controller state uncertain. The existing programmer intentionally does
not automatically retry or reset in that situation.

**Recommended correction:** first inspect the matching completion/status
record and establish a quiescent NOR/controller state. Only then select an
appropriate read/recovery/retry operation. Treat a timed-out host command as
unknown completion, not a proven failed/idle write. The published instructions
have not been edited by this offline review.

### P2 — Reusing a release tag can separate binaries from their source

The workflow updates an existing release with `--clobber` without checking
that its tag resolves to the current commit. Reusing the same request tag in
a later commit can replace the binaries while the installation instructions
still direct users to the old tagged code/recovery identities. The current
first publication is internally consistent; this is a reproducible workflow
failure on a subsequent same-tag request.

**Recommended correction:** use a new immutable tag for each binary build,
or reject an update when the existing tag does not resolve to the publishing
commit. Do not silently overwrite release firmware assets.

## Useful work to retain

- The actual-ST-HAL model catches the disabled-before-channel-change rule,
  unlike the first upstream stub. The final upstream `convert()` and our
  existing sampler both stop ADC before selecting a channel. The first broken
  upstream revision is not the published binary.
- Compiler discovery, optional HAL/CMSIS paths and recorded source hashes
  improve reproducibility across the local Windows and cloud environments.
- The USB-port diagram and clear offline/not-installed release labels are
  useful. Release assets are internally consistent with the committed files.
- The receiver-arm timing analysis is worth preserving. Our1ms floor provides
  more nominal margin than the upstream0.5ms floor, but the changed complete
  startup path and ≤50ms target still need measurement.

## Reconciliation boundary

Both implementations must be mutually exclusive. Upstream changes the
frame-length instruction's4336 argument in RAM; our fixed helper deliberately
requires that original argument and would reject it if both samplers ran.
Upstream's receiver patch also must not be applied to our rebuilt receiver.
The conflict resolution keeps the upstream profile and `--capture-controls`
profile separate while retaining both exact historical recovery identities.
This makes the source tree coherent; it is not a new released or installed
firmware build. Selecting and qualifying a consolidated release remains next.

The local CKN1 metadata/USB-comment support remains useful and backward
compatible with older slots. A report-only error in our evidence README was
corrected: selector0x34200000 is beyond image DMA, which ends0x341D2400. It is
the later RAW-read helper buffer that overlaps the selector region.

## Completed offline checks

Both profiles build and pass 33 focused package/selector tests each. Our
rebuilt prefix, both NOR sectors and selector match the frozen November 13
controls package byte for byte. All 17 RAW-slot tests pass. Both samplers
also pass six cases using ST's actual ADC/ADCEx driver in a register model;
no new ADC sequencing defect was found in our implementation. The model was
adapted for Windows and does not measure analog behavior or capture timing.
The ordinary upstream knob suite passes 10 tests with 3 environment skips;
the separately run model covers its Linux-only HAL-model skip.

All 203 frozen evidence hash entries still match. All five pull conflicts
are resolved, and the edits are left unstaged. No commit or push was made.
Existing build warnings about indentation and executable/writable linker
segments remain; they did not cause a build or test failure.

[Durable results and adjacent test logs](evidence/2026-11-14-knob-reconciliation/results.json)
record the exact identities and limits. Full pull-preservation records,
release metadata and temporary builds remain under
`tmp/review-knobs-20261114/`. No live installation or capture test is implied.


## Approved consolidation — November 14

The user selected the recommendation and requested commit and push. The default
package now uses the source-built CKN1 controls. `--capture-controls` remains a
compatible alias; only explicit `--legacy-knobs` builds the historical path.
The builder rejects a fixed-settings capture reference or an older USB input
without matching CKN1 metadata export. Claude's compiler/SDK portability and
real-ST-HAL model are retained, with durable success, failure and negative-control
regressions for the canonical sampler. No runtime camera behavior changed from
the prepared November 13 controls package: fresh capture, USB and combined
builds reproduce its binary bytes exactly.

Release publication is now manual. The historical request is disabled, tags
must match the source commit, existing assets cannot be replaced, and a partial
draft is published only after all required bytes are checked. The historical
release notes now mark it superseded and replace the unsafe timeout/read/retry
instructions with operation-matched completion and quiescence checks. The
published prerelease will receive this notes-only correction; its tag and
binaries remain unchanged. No new release is requested or automatically made
by the consolidation push.

[Consolidation results and test logs](evidence/2026-11-14-controls-consolidation/results.json)
record the checks and exact build identities. Hardware installation and physical
controls/timing/image qualification remain separate. Unrelated power-design,
PCB-readiness and label-artwork changes are preserved outside this commit.
