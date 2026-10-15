# Template expanded by capture.ps1. All addresses below are SRAM.
set pagination off
set confirm off
set remotetimeout 15
cd @OUTPUT@
set logging file gdb-capture.log
set logging overwrite on
set logging enabled on
file "@ELF@"
target remote 127.0.0.1:61234
monitor reset
load
set $sp = *(unsigned int*)0x34180400
set $pc = Reset_Handler
# Success loop in the pinned capture_app.c, after diagnostics and buffer freeze.
break capture_app.c:292
break capture_fail
break assert_failed
break Default_Handler
continue
bt
print g_capture_stage
print g_capture_ready
print g_frame_count
print g_vsync_count
print g_capture_min
print g_capture_max
print g_capture_sum
print/x g_capture_hash
print g_capture_elapsed_ms
print g_pipe_error_count
print g_dcmipp_error_count
print g_csi_line_error_count
print g_final_frame_errors
print/x g_dcmipp_error_flags
if g_capture_ready != 1 || g_capture_stage != 5 || g_final_frame_errors != 0
  echo Capture did not meet completion checks. Inspect diagnostics and UART log.\n
  disconnect
  quit 1
end
dump binary memory frame-640x480-y8.raw g_capture_frame g_capture_frame+307200
# Return to development ROM; no persistent firmware was installed.
monitor reset
disconnect
quit
