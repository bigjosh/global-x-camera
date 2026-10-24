# Fine timing and cycle-energy analysis

`fine_timing.py` reads a schema-2 automatic SAVE maintenance report and its
original 512-byte report. It checks the raw field values, successful terminal
state, required normal/diagnostic checks, cache/media state, PNG timing validity
and nested counters before producing an exact disjoint partition of COMPLETE.
`test_fine_timing.py` tests the nesting and rejection behavior offline.

Use the source maintenance directory that contains `result.json` and
`storage-report.bin`, for example:

```text
python fine_timing.py --maintenance <directory> --trial-status provisional --out <analysis.json>
```

An optional `--receiver-result` binds a separately collected receiver result.
If its post-maintenance RCP2 header is invalid, the analysis omits receiver
timings and requires the trial to remain provisional. The first awake trial
(`awake01`, IMG00066.PNG) has this limitation due to an address overlap with
the LED proof; it must not become the final normal-profile baseline. Its intact
SAVE report can still characterize the new nested timers provisionally.

The disjoint table separates input conversion/validation/filter, compressor
work including Adler, PNG framing including CRC, and synchronous callbacks.
It does not claim a pure compression-match-loop measurement. Output callback
time includes copying into the 32 KiB buffer and blocking SD flushes; encoding
does not proceed concurrently. The original inner callback timer is evidence
only, not another additive category. P_FINISH includes P_FLUSH, so commit/close
is P_FINISH minus P_FLUSH. All residuals must be nonnegative and all components
must sum exactly in integer CPU cycles before conversion using nominal 400 MHz.
The file-opening category includes free-space checking and filename search
(`f_getfree`, `f_stat`, `f_open`); it does not preallocate the file's clusters.

Full PNG readback and every-pixel comparison are separate evidence. Normal
profile intentionally reports skipped hashes as zero; successful timing alone
does not establish frame identity. `image_readback_verified` stays false in
this timing output until a separately documented verification addendum binds
the file and RAW identities.

The corrected `awake02` record uses v64 normal awake. Its RCP2 proof is valid,
and the separate `verification-addendum.json` records successful readback of
IMG00067.PNG: all PNG chunk CRCs and all 1,527,680 pixels match the retained
RAW samples shifted left by six. The image is 1,452,183 bytes. Image payloads
are not included here.

At nominal 400 MHz, the SAVE COMPLETE interval is 1,701.197 ms. Its principal
disjoint parts are 109.758 ms card initialization, 60.287 ms free-space/name/open,
131.504 ms conversion/check/filter, 786.468 ms DEFLATE including Adler,
33.871 ms PNG framing/CRC, 552.292 ms synchronous output callbacks, and
23.718 ms final flush plus commit/close. The JSON retains all smaller terms and
checks that they sum exactly. Callback time includes buffering and blocking
SD operations; CPU compression does not run concurrently with these writes.

`receiver_timing.py` separately partitions valid RCP2 post-frame processing
through SAVE entry using the same DWT counter. For awake02 this is 70.209 ms:
sensor STOP takes 34.901 ms, NOR module read plus CRC 7.247 ms, and the interval
from loader CRC completion to SAVE P_BEGIN 27.801 ms. The latter includes
loader tail/I-cache disable, entry setup, zeroing 300,472 bytes of BSS, and
report initialization. It is not a pure BSS measurement. The 27.801 ms repeats
the provisional awake01 result exactly in CPU cycles. The new BSS loop crosses
a 32-byte address boundary while the earlier v60 loop fits within one; with
I-cache disabled, instruction-fetch/alignment sensitivity is a possible future
experiment, not an established explanation. No optimization was applied for
this observation.

The external source-ordered GPIO observations put frame IRQ to SAVE marker at
70.730 ms, and SAVE marker4 to marker9 at 1,713.519 ms. The latter is about
0.724% longer than nominal-DWT COMPLETE, despite nearby boundaries. This is a
clock/boundary consistency warning, not a calibrated CPU frequency. Do not
combine the external milliseconds and nominal CPU milliseconds as if they
were one time base. Pulse widths failed the strict decoder; the original
failure is preserved, and labels are explicitly inferred from the ten ordered
edges, exact firmware call order, and independent successful execution proof.

Run `python replay.py` from any working directory to reproduce the compact
phase, receiver and fine timing results and the separate image-verification
metadata. It does not decode image pixels or access the bench.

`comparison-awake.json` compares this trial with the earlier v60c awake trial
using external Saleae intervals only: frame IRQ to SAVE changes from 453.950 to
70.730 ms; commit completion to marker9 from 445.112 to 0.128 ms; reset release
to the awake checkpoint from 2,727.543 to 1,829.000 ms. These are different frame
contents and firmware layouts, not a controlled same-frame profile-only test.
PNG sizes are similar (1,458,185 versus 1,452,183 bytes), which does not make the
images or card latency identical. The source changes explain which diagnostics
were removed, but the table does not attribute every observed difference to
those removals. It makes no awake complete-cycle energy comparison.

The three final v66c Standby trials are now in `energy/`: median **1.061503 J**
and **2.057802 s** from observed current onset through the qualified quiet-tail
boundary, with ranges 0.992903–1.080464 J and 1.933433–2.082825 s. Each plateau
has fresh SBF/early-park evidence plus a separately recorded owner reset/power
history attestation. The original SBF reader's `trial_entry_proven=false`
remains untouched. The energy README separates the one-second confirmation
tail, bench measurement boundary, analog settling and prior-baseline limits.

`phase-summary.json` keeps the three external GPIO timelines separate from
the awake CPU-cycle partition. The representative median-energy trial is
standby03: first STROBE IRQ occurs 22.684 ms after reset, frame IRQ to SAVE is
72.988 ms, SD initialization 98.100 ms, mount 1.519 ms, mount-to-PNG-return
1,799.104 ms, final flush/commit 24.317 ms, final checks 0.128 ms, and the late
loader/peripheral-shutdown interval to the pre-WFI checkpoint 13.602 ms.
The exact first-STROBE value and all ranges are retained in the JSON; interrupt
observations are not exact exposure-edge measurements.

The native-sample analysis uses the existing
`firmware/capture-sd/cycle_energy.py` and `cycle_plot.py` workflow with each
finalized raw recording, explicit off/current-onset/quiet-tail search windows,
actual programmed-sector hash and separately attested terminal qualification.
Keep three trials separate. Preserve all finite-sample, sequence, gap and
dropped-chunk guards. Archive compact count/sum/min/max bins and raw/index
identities, not camera pixels or multi-gigabyte raw streams.

Current onset through the observed low-power plateau is a board-input energy
boundary, not an exact reset, exposure or WFI timestamp. Native current and
power samples share the JS clock; Saleae phase markers have a separate clock
and are not implicitly synchronized. The awake plateau is ambiguous for
completion timing, so it cannot independently define a complete-cycle energy
endpoint. No full-cycle energy claim is made here for either awake trial.
The first v65 Standby attempt saved IMG00068.PNG but was rejected by a stale
schema-1 check in the late-loader guard before teardown. It remains a separate
failed completion trial, not a Standby energy baseline. The three corrected
v66c trials are recorded separately and exclude that failed completion.
