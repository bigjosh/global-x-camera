ENTRY(Stage1_Reset_Handler)
MEMORY { PREFIX (rx) : ORIGIN = 0x34180400, LENGTH = 0x1C00 }
SECTIONS
{
    .isr_vector : { KEEP(*(.isr_vector)) } > PREFIX
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > PREFIX
    .data : { *(.data*) } > PREFIX
    .bss (NOLOAD) : { *(.bss*) *(COMMON) } > PREFIX
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.data) == 0, "Stage one has no initialized globals")
    ASSERT(SIZEOF(.bss) == 0, "Stage one has no zero-initialized globals")
    ASSERT(ADDR(.text) + SIZEOF(.text) <= 0x34182000, "Prefix overlaps stage-two NOR offset")
}
