.syntax unified
.thumb
.section .text.hook,"ax",%progbits
.global usb_boot_hook
.type usb_boot_hook,%function
.thumb_func
usb_boot_hook:
 dsb
 push {r0-r12,lr}
 mrs r0,APSR
 push {r0,r1}
 bl usb_selector_load
 pop {r0,r1}
 msr APSR_nzcvqg,r0
 pop {r0-r12,lr}
 dsb
 b.w 0x34180E2A
.size usb_boot_hook,.-usb_boot_hook
