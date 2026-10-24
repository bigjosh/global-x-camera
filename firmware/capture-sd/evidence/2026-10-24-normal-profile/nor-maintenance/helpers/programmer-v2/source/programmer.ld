ENTRY(ROM_NOR_Programmer)
MEMORY { CODE (rx) : ORIGIN = 0x341E0000, LENGTH = 0x10000 }
SECTIONS {
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > CODE
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.text) <= 0x10000, "Code exceeds reserved RAM")
}
