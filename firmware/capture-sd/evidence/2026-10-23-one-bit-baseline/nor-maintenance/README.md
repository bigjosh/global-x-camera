# NOR WEL failure and explicit repair

The first v61b installation stopped on the frozen programmer's post-program
WEL-clear check at page `0x4200`. The failure remains recorded as result 16;
successful cleanup and later readback do not turn that operation into a pass.
The last command before the check was the `0x2B` security-register read. Final
status/security zero are cleanup results, not the original WEL observation.

Fresh INFO confirmed an idle controller and flash. The full partial read showed
sectors 0–3 matched v61b, page `0x4200` matched too, the next page was incomplete,
and offset `0x5000` onward still matched v59. Root authorized one repair from
those exact current bytes. It used the same frozen helper and unchanged
CRC, idle, WEL and readback guards. Independent full 64 KiB readback then matched
v61b exactly; the following 4 KiB also remained unchanged. No automatic retry or
reset was used. These facts do not establish why WEL was observed set.

[incident.json](incident.json) records the identities and interpretation.
[operations/](operations/) retains the original logs, statuses and byte evidence;
[helpers/](helpers/) retains both frozen RAM helpers and their source identities.
This archive contains NOR firmware bytes, not camera pixels or SD file contents.
The bench owner was root; archive assembly and validation were offline.

Run `python replay.py` here to verify all manifest hashes and repeat the partial,
repaired and following-guard comparisons. The manifest binds the archived
evidence, not an independent physical measurement or a guarantee against
recurrence. Future v60 installation or v59 restoration evidence is separate.
