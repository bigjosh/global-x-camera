# Extended SRAM requirements for RAW10 bring-up

Offline source review, October 17, 2026. No hardware access or memory writes were performed by this research agent. Sources: local RM0486 Rev4, DS14791 Rev10, and pinned STM32N6 CMSIS/HAL headers.

## Memory map and startup

| Secure range | RAM | Size |
|---|---|---|
| 0x34200000–0x3426FFFF | AXISRAM3 | 448 KiB |
| 0x34270000–0x342DFFFF | AXISRAM4 | 448 KiB |
| 0x342E0000–0x3434FFFF | AXISRAM5 | 448 KiB |
| 0x34350000–0x343BFFFF | AXISRAM6 | 448 KiB |
| 0x343C0000–0x343FFFFF | AXISRAM7 / CACHEAXI RAM | 256 KiB |

RM0486 §10.4 pp293–294 states that banks3–6 default to shutdown: writes have no effect and reads return zero. The documented exit order is (1) clear RAMCFG bank CR.SRAMSD, (2) read back that register or wait40ns, (3) enable the bank through RCC_MEMENR, after which it is accessible. Enable the RAMCFG register interface clock before configuring it. `HAL_RAMCFG_EnableAXISRAM()` only clears SRAMSD; it does not enable the RCC bank clock. Do not reset or shut down an in-use bank.

The SRAM3–6 clock is `sysd_ck`, not the SRAM1/2 `sysb_ck`. With ROM CFGR1.SYSSWS=3, sysd comes from IC11. Prove its source/divider/enable or configure the unused channel while all its clients remain idle. The known PLL1 nominal1.2GHz divided by4 supplies300MHz without modifying the active CPU/system/CSI clock channels. Record the actual IC11CFGR, DIVENR, MEMENR, MEMRSTR and RAMCFG_CR values.

SYSCFG_NPU_ICNCR.INTERLEAVING_ACTIVE defaults0. Guard this state when using the contiguous bank map above. RM0486 requires interleaving disabled before shutting down a subset of these banks. This bring-up does not need an interleaving change.

Bank7 defaults to internal SRAM and has no bank3–6-style SRAMSD control. Its RCC gate is CACHEAXIRAMEN. It shares memory with CACHEAXI, so verify CACHEAXI is not enabled before storing diagnostics there. In particular, stage-one trace/status writes relocated into bank7 must wait until this memory is accessible; those writes can precede ordinary application initialization.

## Security and layout

RM0486 §7.4.3–4 says the default RISAF region accepts only secure, privileged, CID1 transactions. The capture firmware already attributes the DCMIPP master to secure+privileged CID1. CPU access and successful DMA need separate verification; do not infer one from the other. RISAF4/5/6 protect entry ports to the NPU RAM interconnect, rather than one instance per physical RAM bank. If partitions are ever changed, the manual requires identical partitioning on all three. Bank7 has RISAF8. No broad permission changes are needed for the documented default region and the matching master attributes.

A16-bit-per-pixel1120×1364 buffer occupies3,055,360bytes, ending at0x342E9F00 when based at0x34000000. It overwrites the old prefix/code/trace addresses in SRAM2. Therefore move every still-live stage2 instruction, vector, constant, global, stack and diagnostic region above that end before arming capture. The old prefix may be overwritten only after its final branch, with no later calls into its code/data. Check linker symbols and fixed-address helpers, not just the frame array declaration.

Suggested acceptance checks: bank power/clock readback; bounded CPU sentinel write/read at each used bank boundary before START, avoiding executable/stack ranges; no overlap in link map; preserve D-cache-off assumption; first-frame completeness and native RAW10 range validation; no new RIF illegal-access or memory/DMA errors. These are implementation checks, not extra user wiring requirements.

## Implementation review

Reviewed `raw10_memory.c` and the frozen v24b generated prefix on October17. No blocking issue was found in the bank power/readback/clock sequence or in moving diagnostic writes until after bank7 is available. RM0486 §12.7.1 confirms that `CACHEAXI_CR1.EN=0` keeps SRAM7 active; merely enabling the CACHEAXI register/bus clock does not select cache mode. The implementation preserves the already-enabled matching IC11 profile, rejects cache/interleave mismatches, probes each destination bank, and leaves faults awake with low-address diagnostics. It also clears/verifies the relocated maintenance helper148bytes and status64bytes before handoff, satisfying the helper's explicit empty-memory precondition. This was an offline review, not proof of successful capture or DMA permissions.
