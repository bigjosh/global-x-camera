# Offline inrush analysis

`analyze_inrush.py` reads completed recorder outputs only. It has no instrument
imports or hardware commands. Every output must be a new path within this
campaign; historical recordings and analyses are read-only.

From the repository root:

```powershell
& 'C:/Users/joshd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tmp/bringup/inrush-20261105/analyze_inrush.py --trace tmp/bringup/inrush-20261105/RUN/trace --out tmp/bringup/inrush-20261105/analysis/RUN.json
```

The JSON has stream hashes and native-ID boundaries, onset selection, raw
0.25/1/5 ms metrics, threshold durations, range transitions and optional cycle
timing/energy. A sibling `.10us.csv` contains 10 us means and maxima from
1 ms before onset through 10 ms afterward. Native peak values remain in JSON.

- Recorder contract: `result.json` success plus no errors/cleanup errors,
  `sha256` for streams, `chunks.jsonl` with native `sample_id`,
  `sample_rate=2000000`, `decimate_factor=1`, `byte_offset`, `byte_count`.
  Analog files are little-endian float32; GPIO is little-bit-order packed u1;
  current range is the official binding's expanded u8 representation.
- OFF-to-ON range transitions locate the turn-on vicinity without assuming a
  15 s off time. Onset is the first current sample at least 20 mA from 10 us
  before to 50 ms after that transition. Without a usable range edge, a rising
  current threshold requires a preceding finite 1 ms mean below 100 uA.
- Multiple onset candidates require an explicit zero-based `--on-index`.
  `--onset-sample` provides an explicitly identified native sample ID; this
  does not turn an arbitrary timestamp into a qualified cold-start event.
- Static recordings without a startup deliberately do not get a fabricated
  onset. `load_trace()` and `metrics()` are importable for static windows.
- Default marker mode accepts one complete ten- or eleven-event train.
  `--markers 11` restricts analysis to the installed single-frame protocol.
  No or incomplete train is permitted for startup analysis; it disables
  full-cycle claims. Marker11 means first firmware observation of sensor FSM2.
- The plateau detector uses the finite final100ms current (below20mA), then
  finds ten consecutive1ms bins after marker10 within2mA of that mean and
  within2mA of each other. This accommodates the new reported3.3mA state.
  It is an analog signature, not a fresh MCU Standby flag proof.

## Historical validation only — November 5

`analysis-selfcheck/` was produced from existing October28 recordings. These
are not new bench runs and do not describe the U42-removed board.

| Recording | Validation |
|---|---|
| `power-ablation-20261028/fixed10a01` | Exact onset34457218, native peak7.872621059A, first5ms charge0.934421523459mC and energy3.675786681777mJ reproduced |
| `power-ablation-20261028/auto01` | Exact onset34245686, native peak7.902018547A, first5ms charge0.945246307314mC and energy3.730832916325mJ reproduced |
| `sensor-autostop-promote-20261028/candidate02/trace` | Exact onset34243416, all11 marker sample IDs, plateau35500000 and post5ms energy266.061169286456mJ reproduced |

Nine synthetic invariant tests pass: signed charge, native-ID alignment,
source-boundary rejection, NaN-integral rejection, variable dwell, ambiguous
multiple starts, missing markers, allowed overlap order and invalid precedence.

```powershell
Set-Location tmp/bringup/inrush-20261105
& 'C:/Users/joshd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest -v test_analyze_inrush.py
```

## Limits

Inputs are sampled at the JS110 source side. Current onset is not target
power-good or reset release. The first5ms, physical peak, negative transients,
insertion effects and clipping remain unqualified. No invalid/incomplete
analog window receives a charge or energy integral. Last GPIO/range chunks
are excluded because their terminal padding lacks an independent next ID.
GPIO phase timing does not establish component-only power, image integrity,
sensor frame count or MCU Standby. The waveform sources remain authoritative;
JSON keeps a bounded preview of unmatched pulses while the original full raw
streams and their hashes are retained.
