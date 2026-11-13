ENTRY(blink_main)
SECTIONS {
 . = 0x34181840;
 .text : { KEEP(*(.text.entry)) KEEP(*(.text.blink_main)) *(.text*) *(.rodata*) }
 .data : { *(.data*) }
 .bss (NOLOAD) : { *(.bss*) *(COMMON) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(blink_main == 0x34181840, "Blink entry moved")
 ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "No initialized/uninitialized globals allowed")
 ASSERT(. <= 0x34181df0, "Blink code overlaps early HOLD hook")
}
