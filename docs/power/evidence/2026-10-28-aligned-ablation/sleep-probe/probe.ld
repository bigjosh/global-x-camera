ENTRY(power_sleep_entry)
SECTIONS {
 . = 0x343C1000;
 .text : { *(.text*) *(.rodata*) }
 .data : { *(.data*) }
 .bss : { *(.bss*) *(COMMON) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(. < 0x343C2000, "Probe overlaps fixed proof")
}
