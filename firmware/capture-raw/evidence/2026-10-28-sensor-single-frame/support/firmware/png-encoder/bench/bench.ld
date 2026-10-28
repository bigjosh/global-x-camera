ENTRY(png_bench_prepare)
MEMORY { BENCH (rwx) : ORIGIN = 0x34320000, LENGTH = 0x80000 }
SECTIONS {
  .text : { KEEP(*(.entry)) *(.text*) *(.rodata*) . = ALIGN(4); } > BENCH
  .data : { *(.data*) . = ALIGN(4); } > BENCH
  _image_end = .;
  .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) . = ALIGN(8); _ebss = .; } > BENCH
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
ASSERT(_image_end <= 0x34340000, "Benchmark executable exceeds 128 KiB")
ASSERT(_ebss <= 0x343A0000, "Benchmark workspace overlaps high stack")
