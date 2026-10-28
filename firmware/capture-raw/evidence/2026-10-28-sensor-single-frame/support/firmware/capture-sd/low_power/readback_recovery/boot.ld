ENTRY(readback_boot_entry)
MEMORY { CODE (rx) : ORIGIN = 0x341E0000, LENGTH = 0x8000 }
SECTIONS {
    .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) . = ALIGN(4); } > CODE
    .data : { *(.data*) } > CODE
    .bss : { *(.bss*) *(COMMON) } > CODE
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.text) <= 0x8000, "Low SRAM code overflow")
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "No static state")
}
