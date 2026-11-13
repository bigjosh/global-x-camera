.syntax unified
.thumb
.section .text.patch,"ax",%progbits
.global blink_redirect
.thumb_func
blink_redirect:
 b.w 0x34181840
