# NOR programmer v2: completion polling

This separate RAM helper preserves the original helper and command/status ABI.
It is not a general flash loader or production firmware. Hardware execution still
requires the existing exact-code/park/context/clock/cache/NOR ownership gates and
fresh current/desired data checks in `nor_bench.py`; this directory does not
authorize an upload or write.

Macronix MX25UM51245G PM2183 v1.6 (March 13, 2026), section 9-1, printed page 24,
recommends first confirming WIP is zero, then checking WEL. Figures 17 and 18 on
printed pages 34–35 show a fresh RDSR and continued polling when WEL remains one.
Source: <https://www.macronix.com/Lists/Datasheet/Attachments/9241/MX25UM51245G,%201.8V,%20512Mb,%20v1.6.pdf>.
The local MB1940 schematic, page 5, identifies U31 as `MX25UM51245GXDI00`;
datasheet Table 15 on printed page 32 maps its RDID to `C2 80 3A`, matching
the observed hardware INFO response. This is not the sibling MX66UW1G45G part.

The old `write_finished` accepted the first WIP-clear sample, read security, then
checked WEL in that same cached status byte. V2 requires a new RDSR transaction
after a WIP-clear observation and both WIP/WEL zero before security/error checks.
It does not require seeing WIP become one: short operations may finish before
the first read. WIP becoming one again invalidates the earlier clear observation.
There is no WRDI, reset, WREN, repeated program, or erase inside completion polling.

The existing 10 ms page/1 s erase budgets and one-million-poll backstop remain.
Completion at/after the deadline is rejected. Individual controller transfers
remain separately bounded, so a slow/failing transfer may overrun the enclosing
poll deadline before returning its existing controller error. Stuck WIP reports
15; WIP-clear but unconfirmed completion reports 16. Existing cleanup is unchanged
apart from diagnostic publication: it may issue WRDI only after its own bounded
WIP-clear check. A cleanup-cleared WEL does not turn a failed operation into success.
Full page and final-sector readback/CRC checks are unchanged.

The reported failures are consistent with observing WIP clear before a fresh WEL
confirmation. Neither the historical logs nor this datasheet establishes the
exact internal transition or status-bit sampling mechanism. Existing evidence does
not indicate stale controller FIFO data; pre/post-transfer empty-FIFO checks,
exact byte counts, TCF/!BUSY checks and all controller ordering remain unchanged.

Extra volatile evidence occupies 26 words at `0x341B4300`, separate from the
unchanged 56-word legacy status at `0x341B4100`. The build manifest gives its order.
Magic is `0x4E435032`, schema 1, command sequence must match, state is 1 running,
2 success or 3 failure, terminal is `0x4E43444E`. It counts WIP=0/WEL=1 observations
and preserves the first failure status/security before cleanup can overwrite the
legacy status. Such observations show a sampled state, not its physical cause.
Accept diagnostics only with matching fresh legacy terminal status and exact park.
`MAX_COMPLETE_CYCLES` includes completion polling through WEL confirmation.
The legacy `MAX_WIP_CYCLES` may now include WIP-clear/WEL-pending observations,
so it must not be interpreted as the exact time WIP first cleared in v2.

`test_completion.py` compiles the actual polling header plus extracted target
failure/completion/security-check functions for native tests. It covers immediate
completion, fresh-status requirements, WEL tails, a busy-again sequence, both
timeouts, stopped timer backstop, wraparound, transfer/security failures,
protection/failure bits and preserved first-failure evidence. A structural test
checks that transaction/preflight/write/verification routines and legacy ABI are
identical to the original. These are software control-flow tests, not hardware
qualification or a simulation of NOR internals.
