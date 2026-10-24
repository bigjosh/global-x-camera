.syntax unified
.thumb
.section .entry,"ax",%progbits
.global save_entry
.thumb_func
save_entry:
    cpsid i
    push {r4,r5,r6,lr}
    mov r4,r0
    mov r5,r1
    mrs r6,msplim
    ldr r0,=0x343A0000
    msr msplim,r0
    /* The bottom canary and MSPLIM are always present. Bulk watermark fill
     * and later scanning are diagnostic-only, preserving the caller frame. */
    ldr r2,=0x5354414B
    str r2,[r0]
#if CAPTURE_DIAGNOSTICS
    mov r1,sp
    subs r1,#64
3:  cmp r0,r1
    bcs 4f
    str r2,[r0],#4
    b 3b
4:
#endif
    ldr r0,=_sbss
    ldr r1,=_ebss
    movs r2,#0
1:  cmp r0,r1
    bcs 2f
    str r2,[r0],#4
    b 1b
2:  mov r0,r4
    mov r1,r5
    bl save_main
    msr msplim,r6
    pop {r4,r5,r6,pc}

.section .text.save_bench_entry,"ax",%progbits
.global save_bench_entry
.thumb_func
save_bench_entry:
    cpsid i
    movs r0,#0
    msr control,r0
    msr msplim,r0
    ldr sp,=0x343B0000
    ldr r2,=0x343F9F00
    ldr r0,[r2,#4]
    orr r0,r0,#0x80000000
    ldr r1,[r2,#8]
    bl save_entry
.global save_park
save_park:
    b save_park
