# Correction: shallow-sleep recovery interpretation

Recorded October 28, 2026, after reviewing the runtime and early recovery source.

The initial explanation that the temporary sleep probe disabled an existing
UART interrupt-driven software-reset listener was unsupported. No such
listener was identified in the normal capture runtime. The established
recovery mechanism instead uses the observed ST-LINK BREAK-to-NRST behavior,
then polls the C0 pulse pattern in the early boot prefix. See the
[VCP recovery design](../../../../firmware/capture-timing/recovery_vcp/README.md).

The measurement facts are unchanged: the temporary stub masked interrupts,
requested shallow WFI with `DBG_SLEEP` clear, and produced a lower current
plateau. The first post-window HOTPLUG read failed before retrieving proof.
UART/BREAK and hardware-reset attempts did not restore verified AP1 access;
a cold cycle with the UART pattern restored the exact early park. No live WFI
PC, retained sleep proof or unchanged-register qualification was recovered.

The cause of those warm recovery failures remains unresolved. Interrupt
masking must not be presented as a proven cause. The lower plateau remains an
externally observed sleep-path result, not a qualified sleep or CPU-isolation
measurement. Subsequent diagnostics use finite timer wake-up and an awake
terminal proof rather than relying on indefinite sleep and later debugger
access.

This is a separate interpretation correction. It does not overwrite prior
measurement artifacts, recorded results, or their integrity manifest.
