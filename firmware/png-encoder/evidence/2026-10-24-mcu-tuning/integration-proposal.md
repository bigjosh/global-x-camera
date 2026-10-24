# Optional MVE conversion and compressor integration proposal

This is a proposal, not an installed SAVE implementation. The experiments in
[comparison.md](comparison.md) establish compute-only results on the retained
RAW fixture. They do not establish integrated SD throughput, full-cycle energy,
autonomous capture, error recovery or Standby behavior for these changes.

## Encoder organization

Keep the public `png16_encode` and `png16_encode_timed` APIs unchanged. Add an
internal row-conversion module with a portable scalar backend and an explicitly
selected Cortex-M55 MVE backend. Leave the scalar backend as the default.
Both produce the existing filter byte and big-endian `sample << 6` pixels,
support NONE/SUB, reject samples above 1023 before emitting that row, and stay
inside the existing conversion timer. Byte-aligned input/output and scalar
tails must remain supported without overreads or wide pointer casts.

The tested vector routine uses eight samples per group. Its SUB implementation
reads a second, in-bounds vector of preceding samples. The caller must provide
disjoint source and scratch storage. Batched validation may leave different
scratch bytes on a rejected row; it must not emit that row. The PNG format,
`sBIT=10`, output callback lifetime and bounded workspace remain unchanged.

Use explicit per-translation-unit build settings. The row module can use O2 and
MVE; the compressor can use O2 with `-mgeneral-regs-only`. Keep control,
filesystem and driver code at their separately qualified optimization setting
and prohibit accidental FP/vector instructions in their generated code. Keep
the hard-float ABI consistent across the module, retain
`-mno-unaligned-access`, record all unit flags and hashes in the manifest, and
check both the standalone 40 KiB module limit and the tighter integrated NOR
allocation: SAVE occupies `0x6000..0xE000`, only 32 KiB before the late completion
module. The actual integrated builder/manifest bounds and SRAM/stack limits
must all pass; a 33–40 KiB standalone build does not fit that NOR layout. Do not
turn the entire capture/boot build into an O2 experiment as a side effect.

Literal-only Huffman, hoisted locals and batch8 are separate decisions from
the row backend. If mode 3 is selected for SAVE, update the SAVE mode gate,
builder choices and exact default-mode proofs together; the current production
SAVE gate accepts only modes 0–2. Preserve old mode meanings. Compression
choice must be based on total save time and energy as well as encoder cycles
and resulting bytes, using representative scenes.

## Restore the caller's context

The compute harness returns to a top-level, exact park. Production `save_entry`
returns to a still-live receiver/save-loader C caller. Clearing CONTROL to zero
unconditionally at that boundary would discard an inherited active FP context.
Do not copy the compute harness's zero-only policy directly into production.

For an optional MVE SAVE module:

1. Before C initialization, retain the entry CONTROL, CPACR, FPCCR, MSP and
   MSPLIM. Preserve the ABI's eight-byte stack alignment and callee-saved
   registers. Validate Thread mode, privileged MSP use, interrupt masks,
   inactive lazy FP state and the existing cache/clock/storage prerequisites.
   Supported inherited CONTROL values may contain only the FPCA/SFPA bits;
   do not silently adopt a different privilege or stack mode.
2. Grant only CPACR CP10/CP11 after those checks, preserving every other bit.
   Use DSB/ISB and readback. Record ownership; a failed prerequisite must not
   change permissions. Compile the initialization and guard code so it cannot
   use FP/MVE before the grant.
3. Let `save_main` complete its ordinary filesystem/card and cache cleanup,
   including failure paths. Leave the terminal word clear when it returns.
4. In integer-only assembly, after every SAVE C frame has unwound, verify the
   expected stack, inactive caches, LSPACT=0, Thread/mask state and the exact
   owned permission grant. Restore the **original** CONTROL FP state, then
   the original CPACR with barriers and readback. A bench caller that entered
   at CONTROL=0 returns at zero; a supported normal caller that entered with
   FPCA/SFPA active retains those bits and its ABI-preserved register state.
5. Publish a versioned context proof and DONE only after that restoration.
   Preserve any earlier error. If final context cannot be proved, fail closed
   without treating the SAVE as successful, resetting the target or guessing
   that a possibly active storage operation is safe to interrupt.

Do not hide normalization inside the row function or an ordinary C cleanup
routine, where the compiler or caller can still have live FP/vector state.
Do not weaken the host's strict CONTROL=0 benchmark park requirement. Existing
normal late-loader/peripheral guards already accept supported FPCA/SFPA bits;
the new build should additionally require its exact context-extension proof.
The entry/exit policy must explicitly distinguish a permission grant owned by
this invocation from inherited state.

The SAVE report currently publishes DONE inside `save_main`, before its C
return and `save_entry` epilogue. Moving that publication is therefore a real
protocol change, not merely adding an intrinsic to the converter. Update the
manifest, host validator, late completion gates and failure tests together.
Historical binaries and their frozen validators must retain their identities.

## Qualification before selecting a default

Retain the row boundary/alignment/invalid-sample tests and full PNG byte/pixel
equivalence tests. Test disabled, full and partial incoming CPACR permissions,
unchanged unrelated permission bits, failed prerequisites, inherited FP state,
lazy-FP refusal, callback failures and post-C proof failures. Inspect the
generated cleanup code; a host semantic model is not an ARM context test.

Then qualify a new immutable integrated build in this order: RAM SAVE with
full file readback and exact return-context proof; autonomous capture/save with
full pixel comparison; failure paths; and the existing repeated cold-cycle,
recovery and Standby checks. Measure full-cycle energy only after the storage
and completion proofs pass. Keep the known production image recoverable until
those checks are complete.

A separate scalar control compiled from the same compressor source is needed
to attribute a timing change to MVE. Hoisting the mode-3 literal loop changes
the compiler's large inlined `tdefl_compress` function, including code generated
for other modes. The local-O2 scalar and MVE builds had identical relocatable
miniz instructions, while the earlier pre-hoist O2 build did not. This rules
out an ABI-induced miniz instruction change in that comparison; it does not
alone establish the cause of a measured timing difference or rule out linked
code/data placement and cache effects.
