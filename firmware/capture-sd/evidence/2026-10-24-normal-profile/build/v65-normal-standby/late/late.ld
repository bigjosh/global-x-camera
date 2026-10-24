ENTRY(late_completion_entry)
MEMORY { LATE (rx) : ORIGIN = 0x343C0000, LENGTH = 0x2000 }
SECTIONS {
  .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) . = ALIGN(4); } > LATE
  .data : { *(.data*) } > LATE
  .bss (NOLOAD) : { *(.bss*) *(COMMON) } > LATE
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }
}
ASSERT(SIZEOF(.data) == 0, "Late completion has no initialized data")
ASSERT(SIZEOF(.bss) == 0, "Late completion has no BSS/startup dependency")
ASSERT(SIZEOF(.text) <= 0x2000, "Late completion exceeds reserved NOR/RAM")
