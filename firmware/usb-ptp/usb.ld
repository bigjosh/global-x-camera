ENTRY(usb_entry)
SECTIONS {
 . = 0x34300000;
 .vectors : { KEEP(*(.vectors)) }
 .text : { *(.text.entry) *(.text*) *(.rodata*) }
 .data : { *(.data*) }
 . = ALIGN(4);
 __bss_start__ = .;
 .bss (NOLOAD) : { *(.bss*) *(COMMON) }
 . = ALIGN(4);
 __bss_end__ = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(. < 0x343E0000,"USB code/data overlaps stack or status")
}
