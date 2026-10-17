# Render @ELF@ and @OUTPUT@ as absolute paths with forward slashes.
# This validates the payload's GPIO behavior through ST-LINK; it is NOT an
# autonomous-boot timing measurement. Nothing is written to NOR or OTP.
set pagination off
set confirm off
set remotetimeout 15
cd @OUTPUT@
set logging file validate-ram.log
set logging overwrite on
set logging enabled on
file "@ELF@"
target remote 127.0.0.1:61234
monitor reset
load
set $sp = *(unsigned int*)0x34180400
set $pc = Reset_Handler
set $markers_reached = 0
break boot_markers_ready
commands 1
  silent
  set $markers_reached = 1
end
break Fault_Handler
continue
info registers pc sp xpsr
set $vtor = *(unsigned int*)0xE000ED08
set $gpio_clocks = *(unsigned int*)0x5602825C
set $d_mode = *(unsigned int*)0x56020C00
set $d_type = *(unsigned int*)0x56020C04
set $d_pull = *(unsigned int*)0x56020C0C
set $d_input = *(unsigned int*)0x56020C10
set $d_output = *(unsigned int*)0x56020C14
set $e_mode = *(unsigned int*)0x56021000
set $e_type = *(unsigned int*)0x56021004
set $e_pull = *(unsigned int*)0x5602100C
set $e_input = *(unsigned int*)0x56021010
set $e_output = *(unsigned int*)0x56021014
printf "markers_reached=%d VTOR=0x%08x AHB4ENR=0x%08x\n", $markers_reached, $vtor, $gpio_clocks
printf "GPIOD MODER=0x%08x OTYPER=0x%08x PUPDR=0x%08x IDR=0x%08x ODR=0x%08x\n", $d_mode, $d_type, $d_pull, $d_input, $d_output
printf "GPIOE MODER=0x%08x OTYPER=0x%08x PUPDR=0x%08x IDR=0x%08x ODR=0x%08x\n", $e_mode, $e_type, $e_pull, $e_input, $e_output
set $valid = $markers_reached == 1 && $vtor == 0x34180400 && ($gpio_clocks & 0x18) == 0x18
set $valid = $valid && ($d_mode & 3) == 1 && ($e_mode & 3) == 1
set $valid = $valid && ($d_type & 1) == 0 && ($e_type & 1) == 0
set $valid = $valid && ($d_pull & 3) == 0 && ($e_pull & 3) == 0
set $valid = $valid && ($d_output & 1) == 1 && ($e_output & 1) == 1
set $valid = $valid && ($d_input & 1) == 1 && ($e_input & 1) == 1
if !$valid
  echo RAM GPIO validation FAILED; inspect register values and PC.\n
  monitor reset
  disconnect
  quit 1
end
echo RAM GPIO validation PASSED. Returning MCU to development ROM.\n
monitor reset
disconnect
quit 0
