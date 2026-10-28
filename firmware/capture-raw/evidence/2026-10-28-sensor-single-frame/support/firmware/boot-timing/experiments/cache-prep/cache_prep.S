/* RAM-only diagnostic. Enter with a working secure privileged debug session.
 * Clear the stack limit before C can use the existing valid MSP. */
.syntax unified
.thumb
.section .text.entry,"ax",%progbits
.global Cache_Prep
.type Cache_Prep,%function
.thumb_func
Cache_Prep:
    cpsid i
    mrs r0, MSPLIM
    movs r1, #0
    msr MSPLIM, r1
    b.w cache_prep_body
.size Cache_Prep, .-Cache_Prep
