# Final save-time and energy comparison — October 20, 2026

The selected v8b fast-loop PNG encoder saved the same frame in **1.6831–1.6842 seconds**, producing **919,353 bytes**. Its save-duration energy is bounded at **0.7675–0.8129 J** across the two runs, under the timing and measurement assumptions below. The complete transferred PNG was independently decoded and every pixel matched the source frame; the readback evidence is archived separately.

| Candidate / mode | Runs | COMPLETE time | PNG bytes | Save-duration energy bounds across runs |
|---|---:|---:|---:|---:|
| v7 true stored DEFLATE | 2 | 1.9541–1.9616 s | 3,080,000 | 0.9585–0.9774 J |
| v7 original fast compression, no filter | 2 | 2.0899–2.1387 s | 746,618 | 0.9056–0.9829 J |
| **v8b fast-loop compression, no filter** | **2** | **1.6831–1.6842 s** | **919,353** | **0.7675–0.8129 J** |
| v8b true stored DEFLATE | 1 | 2.3158 s | 3,080,000 | 1.1307–1.1820 J |

These are observed runs on one image and one powered, already-used card. They are not confidence intervals, worst-case SD latency, cold-card initialization measurements, or a lifetime energy specification. Different module hashes are kept separate. In particular, v8b also uses strict-alignment compiler settings; it is not a pure matcher-only timing experiment.

## Evidence and replay

- `comparison.json`: 21 strict successful v5/v6/v7/v8 runs in five distinct module/configuration groups. Each report is tied to the exact request, frame FNV, module hash, successful filesystem/card state, final CPU context, and cache evidence.
- `fixed-duration-bounds.json`: all-placement energy bounds for the 18 runs that report COMPLETE. The three legacy v5 runs retain host-bracket energy and legacy TOTAL timing; they are explicitly excluded from COMPLETE analysis.
- `summary.json`: compact numeric results for all 21 runs.
- `spec.json`: original workspace replay specification. Its paths document the local analysis inputs; the private RAW frame is intentionally not included in the public archive.
- `replay_energy.py`: portable energy replay using the archive's exact operation JSONs, frozen analysis code, and compressed finalized power log. It does not open instruments or require image pixels.

From the archive root:

```text
python energy-analysis/replay_energy.py
```

The portable replay checks all 21 archived result hashes and successful report invariants against the recorded frame FNV, decompresses and hashes the original power log, verifies finalization/contiguous finite power samples, then recomputes the host-bracket energy and all 18 COMPLETE bounds. The recorded RAW SHA is provenance; it cannot be re-derived without the private RAW file.

Final raw power-log SHA-256:

```text
a78b316350d47d6d0cf6666317db02bd1369651909edc126deab5392b20f82e9
```

Source-frame SHA-256:

```text
5bf987c93eb0db31c916c8d8eeb996a32504f447170f5232d097d776fb9c844c
```

Selected module SHA-256:

```text
91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844
```

The stream stopped cleanly. All recorded power samples are finite and contiguous, with zero dropped chunks. The separate current stream has 71 nonfinite startup samples; this analysis integrates the driver's power channel directly and does not multiply averaged current and voltage. Full session metadata remains in the archived log.

## What the energy bounds mean

The first analysis integrates the entire recorded host interval from immediately before launching the save helper through detection of its fresh terminal status. Those intervals contain command setup and status-polling tails. They must not be called exact target-save energy. Different polling tails made the v7 stored mode appear better than compression in that coarse comparison.

The secondary analysis uses COMPLETE cycles divided by the reported **400 MHz** CPU clock as a fixed duration. It includes **every possible placement** of that duration within the host interval enlarged by an explicitly assumed **±50 ms UTC alignment uncertainty**. Each power chunk retains its sum, minimum and maximum. Partial-chunk bounds and all slope-change positions are evaluated, rather than choosing a waveform feature, favorable alignment, or sampling a grid. This removes much of the polling-tail ambiguity without claiming synchronized electrical markers.

The maximum observed driver mapping residual among these runs is about 12 ms, inside the chosen 50 ms uncertainty. That observation does not establish an external absolute synchronization guarantee. COMPLETE includes the module's cache cleanup and uncached frame recheck; it excludes its entry setup and final return. Legacy TOTAL has a different scope.

These bounds cover recorded-sample aggregation and the stated temporal assumptions. They do not include calibration error, clipping, CPU clock error, or any board current bypassing the Joulescope. No baseline subtraction is used in the COMPLETE bounds. The archived host comparison also retains explicitly conditional baseline calculations, which are not total measured board energy.

## Qualification limits

The O2 experiment is excluded: its functional save report succeeded, but the strict final context check rejected compiler-induced FPCA/SFPA state. That state was inspected and normalized only after a fresh successful terminal proof and inactive lazy preservation. O3 was never executed. Their results do not contribute to these comparisons.

Seven independent mathematical/negative tests cover the sliding bounds, including negative power, decimation, fractional starts, all permutations of small sample chunks, and dense cross-checks of randomized chunk bounds. Six comparison tests cover successful fresh terminal requirements, frame/cache/card rejection, grouping, legacy timing metadata, and host versus target time scopes. The analysis received a separate agent review.
