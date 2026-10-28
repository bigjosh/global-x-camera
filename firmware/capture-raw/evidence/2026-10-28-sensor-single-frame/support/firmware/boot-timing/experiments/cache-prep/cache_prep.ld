ENTRY(Cache_Prep)
MEMORY { CODE (rx) : ORIGIN = 0x34190000, LENGTH = 0x400 }
SECTIONS {
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > CODE
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.text) <= 0x400, "Cache prep exceeds reserved code area")
}
