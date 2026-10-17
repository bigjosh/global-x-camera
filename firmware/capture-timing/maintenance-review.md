# Post-capture maintenance transition review

Offline review, October 17, 2026. Root owns all hardware operations. This records a proposed, reversible RAM-only transition; successful hardware verification must be recorded separately before relying on it for unattended NOR updates.

## Why CONTROL is 0x0C

On Cortex-M55, CONTROL bit2 is FPCA (active floating-point/MVE context) and bit3 is SFPA (that state belongs to the Secure world). Neither indicates unprivileged execution or use of PSP; those are bits0/1. Discarding FPCA/SFPA is appropriate when intentionally abandoning the completed capture application for an integer-only maintenance program. It would be incorrect if the application were expected to resume with its previous FP/MVE context. [Arm Cortex-M55 Devices Generic User Guide, CONTROL, pp49–50](https://documentation-service.arm.com/static/6622c155fabc8c11c7b534b4).

First require that no lazy state save is pending: read FPCCR.LSPACT (bit0 at Secure address `0xE000EF34`) and require zero. Lazy preservation can reserve a stack frame whose contents have not yet been saved. Do not force-clear that condition to satisfy a preflight check. [Armv8-M Exception Model User Guide, floating-point and MVE support](https://community.arm.com/cfs-file/__key/communityserver-discussions-components-files/471/armv8_2D00_m_5F00_exception_5F00_model_5F00_user_5F00_guide_5F00_107706_5F00_0100_5F00_01_5F00_en.pdf).

## Reviewed layout and preconditions

The v9 `capture-small-v9-20261017` build has a 15,324-byte raw payload, initialized data ending at `0x34183FDC`, BSS ending at `0x341840D8`, and a reserved stack at `0x3419B000–0x3419C000`. The frozen cache helper at `0x34190000–0x34190093` and its status at `0x34190400` are separate. Its reviewed disassembly is stackless and contains no FP/MVE instruction. This layout finding does not automatically apply to a larger future build.

Before redirecting execution, confirm:

- The capture has reached its completed idle loop, with DMA/sensor capture stopped. There is no active NOR operation.
- Halted XPSR.IPSR is zero: Thread mode, not an interrupt/fault handler.
- CONTROL has only the expected FP flags; nPRIV/SPSEL are zero, FAULTMASK is zero, and FPCCR.LSPACT is zero.
- D-cache is off and has not been used by this cold-boot path. I-cache may be on.
- The cache helper bytes are identical to any prior execution at that address, or that code region has not executed since a genuine cold boot. A byte-for-byte debug readback alone does not prove cached instructions match modified RAM.

## Recommended sequence

1. Save the completed capture diagnostics, registers, and frame before reusing RAM.
2. Clear the helper's old status, download and verify the exact frozen helper, then execute it. It masks normal interrupts, removes MSPLIM, disables I-cache allocation and invalidates I-cache with barriers.
3. Require a fresh `CACH` status, halt at its known idle PC, and independently verify CCR.I/C cache bits zero, MSPLIM zero and PRIMASK one.
4. Set CONTROL to zero through the debugger and read it back. Also verify PRIMASK remains one, FAULTMASK zero and IPSR zero. If the debugger cannot reliably change that register, use a separately reviewed integer-only `MSR CONTROL`/`ISB` trampoline after caches are prepared; do not relax the frozen NOR helper's context check.
5. Run the frozen NOR programmer **INFO** operation first. Keep all its exact ROM-clock, PLL1, XSPI mux/controller, timer and idle-state guards. Require clean completion, successful cleanup, expected NOR identity, and no write-attempt/uncertainty flag.
6. Only after successful read-only qualification should the existing verified NOR-write workflow be used. Never halt/reset/power-cycle an active or uncertain NOR operation. Do not return to the abandoned application context.

The Cortex-M55 can retain cache lookup capability after CCR cache-allocation bits are cleared. The helper also invalidates instruction cache, which is essential here; merely observing CCR.IC=0 would not make arbitrary replacement of previously cached code safe. The no-D-cache-use precondition remains part of this specific workflow. [Arm Cortex-M55 software development guidance](https://developer.arm.com/community/arm-community-blogs/b/architectures-and-processors-blog/posts/armv8_2d00_m-based-processor-software-development-hints-and-tips).

## Recovery gate alternatives

The RAM request at `0x341F0F00` was observed by the root bench owner to be cleared by ROM during hardware reset, so it is not a qualified reset-persistent gate.

A gate based solely on DHCSR.C_DEBUGEN identifies debugger presence, not an explicit one-shot maintenance request. Its behavior across the exact reset route would need testing, and an accidentally retained debug-enable state could change a timing run. Prefer the verified post-capture maintenance entry above before adding that dependency.

A backup-register request could be suitable if the selected register is demonstrably unused and retained across the intended reset, with explicit request clearing and cold-boot behavior. No such register has been selected or modified in this review. Neither alternative warrants relaxing cache, execution-context, NOR-idle, or write-verification guards.
