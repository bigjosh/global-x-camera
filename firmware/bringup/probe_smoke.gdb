# Expanded by probe_smoke.ps1. Load only SRAM; no flash/OTP operations.
set pagination off
set confirm off
set remotetimeout 15
cd @OUTPUT@
set logging file gdb-probe-smoke.log
set logging overwrite on
set logging enabled on
file "@ELF@"
target remote 127.0.0.1:61234
# Exercise the physical NRST wire while the Saleae is already recording.
monitor reset hardware
load
set $sp = *(unsigned int*)0x34180400
set $pc = Reset_Handler
break app_run
commands 1
  silent
  set $entry_hit = 1
end
break assert_failed
break Default_Handler
set $entry_hit = 0
continue
if $entry_hit != 1
  echo Failed to reach app_run.\n
  monitor reset
  disconnect
  quit 1
end
delete breakpoints
# Startup has now initialized BSS; select the optional GPIO-only test.
set g_probe_smoke_mode = 1
break probe_smoke_complete
break assert_failed
break Default_Handler
continue
bt
print g_probe_smoke_done
if g_probe_smoke_done != 1
  echo GPIO stimulus did not complete.\n
  monitor reset
  disconnect
  quit 1
end
# Return to development ROM; the test never persisted firmware.
monitor reset
disconnect
quit
