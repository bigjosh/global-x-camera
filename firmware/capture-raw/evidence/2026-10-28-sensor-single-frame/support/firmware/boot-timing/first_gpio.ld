ENTRY(Reset_Handler)

/* Boot ROM's 1 KiB STM32 image header precedes this payload at 0x34180000.
 * Reserve a small, separate stack in the same secure AXISRAM2 download area.
 */
MEMORY
{
    PAYLOAD (rx) : ORIGIN = 0x34180400, LENGTH = 0x800
    STACK   (rw) : ORIGIN = 0x34180C00, LENGTH = 0x400
}
_sstack = ORIGIN(STACK);
_estack = ORIGIN(STACK) + LENGTH(STACK);

SECTIONS
{
    .isr_vector : { KEEP(*(.isr_vector)) } > PAYLOAD
    .text : { *(.text.Reset_Handler) *(.text*) *(.rodata*) . = ALIGN(4); } > PAYLOAD
    _payload_end = .;
    .stack (NOLOAD) : { . = . + LENGTH(STACK); } > STACK
    /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(ADDR(.isr_vector) == 0x34180400, "FSBL vector base moved")
ASSERT(SIZEOF(.isr_vector) == 64, "Expected 16 core vectors")
ASSERT(_payload_end <= ORIGIN(STACK), "Payload overlaps stack")
ASSERT((_estack & 7) == 0, "Stack must be 8-byte aligned")
