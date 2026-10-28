ENTRY(isolated_entry)
SECTIONS {
 . = 0x34300000;
 .vectors : { KEEP(*(.vectors)) }
 .text : { *(.text*) *(.rodata*) }
 .data : { *(.data*) }
 .bss : { *(.bss*) *(COMMON) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(. < 0x34310000,"Code overlaps workload buffer")
 ASSERT(SIZEOF(.bss)==0,"No uninitialized globals")
}
