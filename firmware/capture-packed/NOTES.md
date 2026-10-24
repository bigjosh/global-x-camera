# Packed capture decisions

## 2026-10-24  Carry unchanged RAW10 as opaque bytes through the receiver

**Why:** the sensor already transmitted packed ten-bit samples; the ordinary CSI/DCMIPP path expanded them to 16-bit RAM words. Keeping sensor depth 10 while assigning packet type `0x30`, accepting BPP8 transport and filtering that type preserved all packed bytes without a CPU conversion. Two independent decoders matched every sample against the ordinary capture, saving 1,145,760 frame bytes (37.5%).
**Rejected:** treating `P0PPCR.PAD` as a packing control; dropping the low two bits; assuming register names alone proved the combined sensor/receiver behavior.
**Evidence:** commit `cff6da2c`; [configuration and qualification](README.md#configuration-that-preserves-the-packed-bytes); [frozen experiment](evidence/2026-10-24-packed-raw10/).
**Provenance:** migrated 2026-10-24 from measured native/packed deterministic comparisons and the recorded manual review.

## 2026-10-24  Normalize only experiment-owned floating-point context

**Why:** the first native control captured correctly but failed its final park check because the HAL clock calculation set floating-point context flags. The revised top-level RAM experiment records and clears its own inactive FP state before a non-returning park. That narrowly qualified cleanup cannot safely substitute for preserving a normal caller's context.
**Rejected:** weakening the strict completion gate or copying the top-level cleanup into a returning SAVE function.
**Evidence:** commit `cff6da2c`; [original refusal and correction](README.md#experiment-and-recovery); [PNG MVE integration constraint](../png-encoder/NOTES.md#2026-10-24--keep-the-faster-huffmanmve-path-an-explicit-pipeline-candidate).
**Provenance:** migrated 2026-10-24 from the preserved failed v3 control and successful v4 experiments.
