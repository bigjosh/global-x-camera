.syntax unified
.thumb
.section .entry,"ax",%progbits
.global late_completion_entry
.thumb_func
late_completion_entry:
    /* No startup/BSS/cache/stack mutation. Called after SAVE has returned. */
    b status_led_complete_sleep
