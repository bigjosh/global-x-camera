# Rejected five-cycle raw recording

This recording is invalid for energy analysis: 513 packets were dropped and
each signal has a 5.591187-second gap. The original manifest remains
`finalized: false`, with failed coverage. The strict native analyzer rejected it
before reading the raw arrays. No gaps were filled, no data repaired and no
energy estimate from this recording is included in the baseline.

The gap lies in the commanded off interval before cycle 5, according to the
chunk timeline and control log. That observation does not override the global
coverage failure. The 64-packet nonblocking worker queue overflowed, consistent
with a worker, disk or scheduling stall; no per-write latency was recorded, so
the underlying cause is unproven. The subsequent accepted runs used separate
short recordings, an explicitly larger bounded queue and unchanged strict
finalization/coverage checks. More queue capacity is no guarantee against
logging failure, including failure to drain before shutdown.

The archive retains the original invalid manifest, diagnostic, compressed chunk
index and control/session records. Raw float streams remain local. The runner
source is retained for audit only; do not execute it from this archive.
`python replay.py` checks hashes, the original false finalization/drop count and
all three recorded gaps. It does not estimate energy or establish firmware
success, Standby entry or image integrity for any of these cycles.
