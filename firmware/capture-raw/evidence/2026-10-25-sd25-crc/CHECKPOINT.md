# 25 MHz CRC investigation checkpoint

October 25, 2026, approximately 05:04 UTC. This is an experimental result,
not promotion of a new installed firmware profile.

The full SD probe map exposed signal errors consistent with a clock-integrity
problem: failed reads advance all four data lanes by one or three nibbles,
and write traces contain narrow clock pulses. See [pre-resistor signal evidence](README.md) and
[post-resistor evidence](POST_RESISTOR.md). The analog cause remains inferred.

## Tests and changes

- An unchanged 25 MHz pattern write and a separate NEGEDGE write completed.
  Sustained reads failed with both phases. Intermediate GPIO speeds 1 and 2
  also failed; none of those changes alone qualified 25 MHz.
- A later 12.5 MHz read also failed with the new probes attached. The earlier
  12.5 MHz baseline remains evidence for its original physical configuration.
- The user added **27 ohms in series with CLK, approximately halfway between
  the Nucleo and carrier**. This is the actual tested placement; placement
  close to CN3.3 was recommended but has not been performed.
- With that resistor and 25 MHz / four-bit / NEGEDGE / GPIO speed3 / unchanged
  compensation, two complete previously written slots (3 and 4) read back
  without CRC errors. Every image byte matched the original camera RAM:
  1,909,600 bytes per image, plus valid GXR2/GXRE markers and metadata layout.
- A new full pattern write to slot 5 completed with idle/deinitialized card
  proof. Its trace contains no observed 4/8/12 ns clock pulses; all 3,730
  packets matched the original RAM at 0/+4 ns sampling, all 14,920 lane CRCs
  passed and each first DAT0 status indicated acceptance. Its subsequent SD
  readback has not yet been performed at this checkpoint.
- CMD/CH3 became unobservable after resistor insertion. Possible changed
  probe loading and the retained -4 ns decode ambiguity limit attribution.

No NOR write or card erase occurred. The installed v23 image remains four-bit
12.5 MHz, sector SHA-256
`bb31867394a4e0d0fb9ab3f9fa96d0d16ffc7256e2a274db74be4f11f9cfdc14`.
The latest RAM image is `ram-pattern25-negedge`, SHA-256
`f95fe25e33618e7537c3b4c258848becdcbc94cd6e0b236883bdf5de9054d7cd`.
Its final slot-5 capture proof reports result0, media_idle1, initialized0,
controller_owned0 and cleanup_error0. The target is powered in an awake
terminal, with caches off; COM8 is closed, BREAK released and no helper active.

## Pending qualification

Hardware tests are paused for the requested removal of SD signal probes
CH1/2/3/4/5/7 at the breakout. Keep CH0/NRST, CH6/PE6, ground, SD wires and the
27 ohm resistor unchanged. Removal has **not yet been confirmed**. Next verify
reads and fresh normal/long-exposure writes without the probes, including
both PIO and IDMA paths and full source-RAM equality. Cold boot / Standby and
energy measurements for a promoted 25 MHz image remain pending.

The source adds guarded RAM-only phase/slew diagnostics; defaults rebuild
byte-identically. 98 RAW tests, 11 actual-driver test groups and six offline
decoder tests passed. The proposed flash-promotion patch remains unapplied.

Private exact builds, captures, operation proofs and readback comparisons are
under `tmp/bringup/sd25-crc-20261025`. `FREEZE.json` binds the sanitized signal
reports and decoder sources. Bulk captures, card/instrument identifiers,
user paths and images were not copied into this public evidence directory.
