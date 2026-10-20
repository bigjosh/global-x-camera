# Complete-cycle energy on the JS110 sample timeline

`js110_session.py --cycle-raw-dir NEW_DIRECTORY` opts into raw current,
voltage and power recording inside the existing single device owner. It does
not open a second driver, cycle power, use GPIO, or change suppression settings.
The ordinary helper and legacy summary flags retain their existing behavior.

The helper saves exact delivered float32 samples at 2 MHz, native sample IDs,
chunk CRCs, complete-file SHA-256 values, and a final manifest. It records
starting range/suppression/LSB-route settings and host-stamped range commands.
These command timestamps are diagnostics, not physical waveform edges.
The 4096 MiB default sample-file budget holds about 179 seconds at 24 MB/s.
Use a bounded session and ample local disk space. Budget exhaustion, queue
drops, disk errors or incomplete coverage invalidate the recording and follow
the helper's normal settings-restoration path. Preserve the session log too.
The files are local bench data; do not automatically add multi-GB raw captures
to the public repository.

## Measurement procedure

1. First qualify the exact firmware's completed save, idle storage and terminal
   state, plus the effective recovery path. Low current does not prove a saved
   image or safe shutdown. Ordinary completion proofs are lost in Standby.
2. With one owner and the known CN8 → JS110 → target route, start recording
   before the separately authorized power cycle. Keep the debugger quiet during
   the measured interval. Retain enough off baseline, startup and terminal
   plateau. A fixed 2 A range avoids *automatic* range transitions but is not a
   current limit or a guarantee against initial range-switch suppression or
   saturation. Inspect peak current and source voltage. An auto-range capture
   with substituted/interpolated samples is a different measurement condition.
3. Keep recording through at least the configured plateau confirmation time,
   then stop the helper normally. Do not power-cycle again until storage is
   independently known idle. Repeat cycles can share one recording; give each
   its own nonoverlapping native-sample window and terminal evidence.
4. Run `cycle_energy.py` after the manifest is finalized. It validates file
   identities/coverage, rejects nonfinite data in each cycle, checks an observed
   off baseline, locates positive current onset, and walks backward from the
   window end to find a sustained plateau. Thus an idle gap followed by more
   activity is not selected as completion.

Example offline invocation:

```powershell
python firmware/capture-sd/cycle_energy.py `
  --recording tmp/bringup/cycle-raw `
  --spec tmp/bringup/cycle-spec.json `
  --out tmp/bringup/cycle-energy.json
```

Example specification structure (**thresholds and sample IDs are illustrative,
not qualified settings for this board**):

```json
{
  "criteria": {
    "bin_s": 0.001,
    "off_baseline_s": 0.5,
    "off_abs_max_a": 0.0001,
    "onset_a": 0.02,
    "pretrigger_s": 0.1,
    "plateau_min_s": 1.0,
    "plateau_mean_min_a": 0.001,
    "plateau_mean_max_a": 0.01,
    "plateau_peak_abs_max_a": 0.015,
    "plateau_mean_span_a": 0.002,
    "current_valid_abs_max_a": 1.8
  },
  "cycles": [{
    "name": "cycle-01",
    "start_sample_id": 1000000,
    "end_sample_id": 11000000,
    "terminal_state_qualified": true,
    "terminal_evidence": "cycle-01-terminal-proof.json"
  }]
}
```

The analyzer hashes the external evidence but does not interpret it. The bench
owner must validate that proof against the exact firmware and cycle before
attesting `terminal_state_qualified`. Sample windows come from the recording's
native timeline, not from UTC. `chunks.jsonl` provides coverage endpoints and
coarse extrema; the raw `.f32` files provide the waveform for selecting windows.
An eventual successful proof does not establish that an earlier current-level
transition marked completion. In the v50 awake baseline, final uncached frame
validation can already draw the same current as the later idle park; its
detected plateau therefore cannot bound complete-cycle energy. Use a uniquely
qualified terminal transition, or retain the result as a current-level
comparison with `completion_boundary_qualified: false`.

When the debugger is disconnected and terminal verification is unavailable,
`--allow-unqualified-plateau` permits **signature-only** analysis of windows
explicitly marked `"terminal_state_qualified": false`. A context/evidence file
is still required and hashed. All raw-integrity, finite-data, baseline, onset,
measurement-limit and sustained-plateau checks remain active. Results explicitly
set terminal/completion qualification and complete-cycle-energy claims to false;
the mode does not infer SBF, a saved file, or Standby from a familiar current
trace. Without this opt-in the same window is rejected. Keep this analysis
separate from earlier verified cycles and from any later card inspection.

## What the result establishes

The primary result integrates driver's synchronized power samples through the
first required duration of the terminal plateau. It separately reports:

- pretrigger charge energy, onset-to-plateau energy, and plateau confirmation
  energy;
- whole-window energy, peak delivered current, minimum source voltage, and
  plateau mean current/power;
- current-threshold and plateau-bin boundaries, with native sample resolution;
- optional baseline subtraction, explicitly conditional on stationary
  background load.

This removes the earlier coarse host/UTC placement uncertainty. It does **not**
turn a current threshold into a physical target-power-good signal: JS110 voltage
measures IN+, which remains powered while its output current-range switch is
off. Activity above the off threshold before the pretrigger causes rejection;
still smaller current before pretrigger cannot be proven absent. Whole-window
energy is also retained so that charge is visible without a boundary claim.
No automatic interpolation of NaN samples or saturation correction is allowed.
Finite output alone does not rule out the driver's configured suppression
interpolation. The current-range validity threshold is a caller-specified
qualification limit, not a software clipping detector.

The CN8 sense/USB bypass paths and independently powered debugger remain outside
the measured input boundary. These results are board-input comparisons, not a
fully isolated production-camera energy specification. No JS GPIO marker wire
is currently assumed connected. The installed official driver supports GPI
streams on native sample IDs, but adding them would require a separately
qualified voltage-safe wire and shared-I/O configuration.

## Compact evidence and exported figures

After strict raw analysis succeeds, `cycle_plot.py export` validates the raw
archive again and binds the selected analysis by its SHA-256. It exports each
current, source-voltage and power sample into native-ID bins containing count,
signed sum, minimum and maximum. Bins split exactly at integration boundaries;
the exporter checks all four reported segment integrals against these sums.
The default view includes the pretrigger selected by the analysis,
the entire activity interval, and at least the required plateau confirmation
or a three-second terminal tail, whichever is longer. It also exports a
separate two-millisecond inrush view. No sample-picking decimation is used.

```powershell
python firmware/capture-sd/cycle_plot.py export `
  --raw tmp/bringup/cycle-raw `
  --analysis tmp/bringup/cycle-energy.json `
  --cycle 0 --out tmp/bringup/cycle-compact.json.gz

python firmware/capture-sd/cycle_plot.py plot `
  --input tmp/bringup/baseline-compact.json.gz tmp/bringup/cycle-compact.json.gz `
  --out tmp/bringup/cold-cycle-comparison.png
```

Export uses NumPy; rendering additionally needs Matplotlib. PNG and SVG outputs
are supported by Matplotlib. Existing outputs are never overwritten. Plot time
zero is the observed current threshold; dotted lines mark the selected terminal
plateau boundary. Neither the plot nor the energy analysis assigns exposure,
capture, compression or SD-write phases from host timestamps. The baseline
awake state and a final Standby state must be labeled distinctly. Different
scene sizes or compression workloads must accompany any comparison.

For a compact repository archive, retain:

- the exact analysis and window/criterion specification for each run;
- `compact.json.gz`, which preserves the plotted bins and checked segment sums;
- the original raw manifest, optionally compressed chunk index, and their
  original hashes;
- the matching terminal qualification, firmware identities and saved file
  metadata, without private image or card-sector contents;
- the recorder/analyzer/exporter source and tests, and exported PNG/SVG.

This set can replay aggregate energy and the figure without the multi-GB raw
samples. It **cannot** independently rerun the raw onset/plateau search:
within-bin sample order is intentionally absent. The original raw files remain
local, bound by their SHA-256 and per-chunk CRCs. A hash is provenance, not a
replacement for the bytes when raw-detector replay is required.
