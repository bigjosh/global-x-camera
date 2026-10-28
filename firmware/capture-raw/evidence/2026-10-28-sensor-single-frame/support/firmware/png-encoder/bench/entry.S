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
.global png_bench_done_park
png_bench_done_park:
2:  b.n 2b
.ltorg
