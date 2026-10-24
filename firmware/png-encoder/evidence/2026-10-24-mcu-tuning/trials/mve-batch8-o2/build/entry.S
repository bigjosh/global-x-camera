.syntax unified
.thumb
.section .entry,"ax",%progbits
.global png_bench_prepare
.thumb_func
png_bench_prepare:
    cpsid i
    movs r0,#0
    msr msplim,r0
    ldr sp,=0x343B0000
    ldr r0,=0x343A0000
    msr msplim,r0
    bl png_bench_prepare_main
    ldr r0,=0x52454144
    bl png_bench_finalize
.global png_bench_ready_park
png_bench_ready_park:
1:  b.n 1b
.balign 4
.global png_bench_run
.thumb_func
png_bench_run:
    cpsid i
    movs r0,#0
    msr msplim,r0
    ldr sp,=0x343B0000
    ldr r0,=0x343A0000
    msr msplim,r0
    bl png_bench_run_main
    ldr r0,=0x444F4E45
    bl png_bench_finalize
.global png_bench_done_park
png_bench_done_park:
2:  b.n 2b
.ltorg

/* Integer-only post-C epilogue. No FP/MVE value is live beyond the C call.
 * R0 is the terminal value; LR returns directly to the exact high park. */
.global png_bench_finalize
.thumb_func
png_bench_finalize:
    ldr r1,=0x343E0000
    mrs r2,control
    str r2,[r1,#296] /* reserved0: actual CONTROL after all C returned */
    str r2,[r1,#76]  /* final_control before any attempted normalization */
    /* Never adopt FP/vector state that was already active on entry. */
    ldr r3,[r1,#60] /* initial_control */
    cmp r3,#0
    bne .Lcontext_bad
    ldr r3,[r1,#56] /* initial_ccr */
    tst r3,#0x30000
    bne .Lcontext_bad
    ldr r3,[r1,#68] /* initial_fpccr */
    tst r3,#1
    bne .Lcontext_bad
    mrs r3,msp
    str r3,[r1,#304] /* reserved2: post-C MSP */
    ldr r12,=0x343B0000
    cmp r3,r12
    bne .Lcontext_bad
    mrs r3,msplim
    str r3,[r1,#308] /* reserved3: post-C MSPLIM */
    ldr r12,=0x343A0000
    cmp r3,r12
    bne .Lcontext_bad
    bic r3,r2,#12
    cmp r3,#0
    bne .Lcontext_bad
    mrs r3,ipsr
    str r3,[r1,#80]
    cmp r3,#0
    bne .Lcontext_bad
    mrs r3,primask
    str r3,[r1,#84]
    cmp r3,#1
    bne .Lcontext_bad
    mrs r3,faultmask
    str r3,[r1,#88]
    cmp r3,#0
    bne .Lcontext_bad
    ldr r3,=0xE000EF34
    ldr r3,[r3]
    str r3,[r1,#92]
    tst r3,#1
    bne .Lcontext_bad
    ldr r3,=0xE000ED14
    ldr r3,[r3]
    str r3,[r1,#72]
    tst r3,#0x30000
    bne .Lcontext_bad
    ldr r3,=0xE000ED88
    ldr r3,[r3]
    str r3,[r1,#312] /* reserved4: CPACR at publication */
    ldr r12,[r1,#320] /* reserved6: prerequisite completed, CPACR owned */
    cmp r12,#1
    bne .Lcontext_bad
    ldr r12,[r1,#316] /* reserved5: initial CPACR */
    orr r12,r12,#0x00F00000
    cmp r3,r12
    bne .Lcontext_bad
    movs r2,#0
    msr control,r2
    isb
    mrs r2,control
    str r2,[r1,#76]
    cmp r2,#0
    bne .Lcontext_bad
    /* All C/vector state is gone and CONTROL0 is verified. Restore permission. */
    ldr r12,=0xE000ED88
    ldr r3,[r1,#316]
    str r3,[r12]
    dsb
    isb
    ldr r2,[r12]
    str r2,[r1,#324] /* reserved7: observed restored CPACR */
    cmp r2,r3
    bne .Lcontext_bad
    ldr r3,=0x4D564531 /* MVE1: verified post-C normalization + CPACR restore */
    str r3,[r1,#300]
    b .Lcontext_publish
.Lcontext_bad:
    ldr r3,[r1,#24]
    cmp r3,#0
    bne .Lcontext_preserve_error
    movs r3,#11
    str r3,[r1,#24] /* PB_BAD_FINAL_CONTEXT, preserve earlier error */
.Lcontext_preserve_error:
    movs r3,#3
    str r3,[r1,#12] /* PB_STATE_FAILED */
    ldr r3,=0x4D564546 /* MVEF: context remains unnormalized */
    str r3,[r1,#300]
.Lcontext_publish:
    dsb
    str r0,[r1,#508] /* READY/DONE only after all checks + normalization */
    dsb
    bx lr
.ltorg
