ENTRY(power_aba_entry)
MEMORY { PROBE (rwx) : ORIGIN = 0x343C4000, LENGTH = 0x2000 }
SECTIONS {
 .text : { *(.text*) *(.rodata*) } >PROBE
 .data : { *(.data*) } >PROBE
 .bss : { *(.bss*) *(COMMON) } >PROBE
 /DISCARD/ : { *(.comment*) *(.ARM.exidx*) *(.ARM.extab*) }
 ASSERT(SIZEOF(.data) == 0, "No runtime data initialization permitted")
 ASSERT(SIZEOF(.bss) == 0, "No implicit BSS permitted")
}
