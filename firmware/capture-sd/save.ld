ENTRY(save_entry)
MEMORY { SAVE (rwx) : ORIGIN = 0x34320000, LENGTH = 0x80000 }
SECTIONS {
  .text : { KEEP(*(.entry)) KEEP(*(.text.save_bench_entry))
    *(.text*) *(.rodata*) . = ALIGN(4); } >SAVE
  .data : { *(.data*) . = ALIGN(4); } >SAVE
  _image_end = .;
  .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) . = ALIGN(8); _ebss = .; } >SAVE
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }
}
ASSERT(_image_end <= 0x3432A000, "Save executable exceeds 40 KiB NOR budget")
ASSERT(_ebss <= 0x343A0000, "Save workspace overlaps reserved 64 KiB stack")
