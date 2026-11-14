/* Fixed entry veneers are independently checked by the package builder. */
.syntax unified
.thumb
.section .selector_entry,"ax",%progbits
.global usb_selector
.type usb_selector,%function
.thumb_func
usb_selector:
 b.w usb_selector_body
.size usb_selector,.-usb_selector
.section .controls_entry,"ax",%progbits
.global capture_controls_sensor_entry
.type capture_controls_sensor_entry,%function
.thumb_func
capture_controls_sensor_entry:
 b.w capture_controls_sensor_apply
.size capture_controls_sensor_entry,.-capture_controls_sensor_entry
