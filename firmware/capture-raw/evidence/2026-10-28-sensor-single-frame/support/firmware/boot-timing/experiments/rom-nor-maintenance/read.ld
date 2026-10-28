ENTRY(ROM_NOR_Read)
MEMORY { CODE (rx) : ORIGIN = 0x341B0000, LENGTH = 0x4000 }
SECTIONS {
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > CODE
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.text) <= 0x4000, "Code overlaps command record")
}
