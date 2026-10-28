ENTRY(Stage1_Reset_Handler)
MEMORY { PREFIX (rx) : ORIGIN = 0x34180400, LENGTH = 0x1C00 }
SECTIONS
{
    .isr_vector : { KEEP(*(.isr_vector)) } > PREFIX
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) } > PREFIX
    .error_bridge 0x34181820 : { KEEP(*(.error_bridge)) } > PREFIX
    .error_text 0x34181840 : {
        _error_engine_start = .; KEEP(*(.error_text)) _error_engine_end = .;
        . = _error_engine_start + 1536; _error_copy_end = .;
    } > PREFIX
    ASSERT(SIZEOF(.error_bridge) <= 32, "Error bridge overflow")
    ASSERT(_error_engine_end <= _error_copy_end, "Error handler overflow")
    ASSERT(ADDR(.error_text) + SIZEOF(.error_text) <= 0x34182000, "Error handler overflow")
    .data : { *(.data*) } > PREFIX
    .bss (NOLOAD) : { *(.bss*) *(COMMON) } > PREFIX
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
    ASSERT(SIZEOF(.data) == 0, "Stage one has no initialized globals")
    ASSERT(SIZEOF(.bss) == 0, "Stage one has no zero-initialized globals")
    ASSERT(ADDR(.text) + SIZEOF(.text) <= 0x34182000, "Prefix overlaps stage-two NOR offset")
}
