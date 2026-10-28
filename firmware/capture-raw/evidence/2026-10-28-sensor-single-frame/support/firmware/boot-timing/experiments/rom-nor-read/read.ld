ENTRY(ROM_NOR_Read)
MEMORY { CODE (rx) : ORIGIN = 0x341A0000, LENGTH = 0x400 }
SECTIONS {
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > CODE
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.text) <= 0x400, "Code overlaps status record")
}
