"""Generate the human command transcript from offline native-SD events.

No device access. Input is the JSONL emitted by the frozen binary replay
adapter, with sample numbers relative to the beginning of the recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from human_semantics import Explainer

RATE = 500_000_000
TRIGGER_SAMPLE = 3_030_233_130
SOURCE_SHA = "2dfa9ccb1f2e0baea4d204c01366e1e75bf3d3a5d6aab9cf506d08f6fe73b057"


def timestamp(sample: int) -> str:
    return f"{(sample - TRIGGER_SAMPLE) / RATE:.9f}"


def escaped(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    events = [json.loads(line) for line in args.events.read_text().splitlines() if line.strip()]
    events.sort(key=lambda e: (e["start"], e["end"]))
    args.out.mkdir(parents=True, exist_ok=True)
    explain = Explainer()
    rows, invalid, read_data = [], [], []
    previous_start = None
    first_command = None
    last_command = None
    init_poll = 0
    for event in events:
        fields = event["fields"]
        event["description"] = event["text"]
        if event["type"] in ("command", "response") and event["error"]:
            invalid.append(event)
            continue
        meaning = explain.event(event)
        if event["type"] == "data_block" and event["text"].startswith("Read block "):
            assert not event["error"]
            # Keep protocol register content, but no photo payload previews.
            public_fields = {k: v for k, v in fields.items() if k != "preview"}
            if fields.get("bytes") == "8":
                public_fields["preview"] = fields.get("preview", "")
            else:
                meaning = meaning.split("; first bytes", 1)[0]
            read_data.append({"start_sample": event["start"], "end_sample": event["end"],
                              "logic_start_s": timestamp(event["start"]),
                              "duration_us": (event["end"]-event["start"])/500,
                              "fields": public_fields, "meaning": meaning})
        if event["type"] not in ("command", "response"):
            continue
        cmd = int(fields["command"])
        app = fields.get("application") == "yes"
        if event["type"] == "command":
            name = ("ACMD" if app else "CMD") + str(cmd)
            last_command = name
            if first_command is None:
                first_command = event["start"]
            raw = fields["argument"]
            if app and cmd == 41:
                init_poll += 1
                meaning = f"Initialization poll {init_poll}/64: " + meaning
            if cmd == 17:
                lba = int(raw, 16)
                if lba % 3730 == 0:
                    meaning += f"; first sector of fixed slot {lba // 3730} (project layout: 3,730 sectors/slot)"
            if cmd == 25:
                meaning += "; project slot 37, 3,730 sectors are observed in this recording"
        else:
            name = fields["response_type"] + " → " + str(last_command)
            raw = fields.get("value", fields.get("CID_CSD_120_bits", ""))
            if fields["response_type"] == "R2":
                raw = "0x" + fields["CID_CSD_120_bits"] + " [bits127:8]"
        row = {
            "number": len(rows) + 1, "start_sample": event["start"], "end_sample": event["end"],
            "logic_start_s": timestamp(event["start"]), "logic_end_s": timestamp(event["end"]),
            "since_cmd0_ms": (event["start"]-first_command)/500_000,
            "delta_previous_command_response_start_us": None if previous_start is None else (event["start"]-previous_start)/500,
            "duration_us": (event["end"]-event["start"])/500,
            "type": event["type"], "event": name, "raw": raw,
            "meaning": meaning, "fields": fields,
        }
        assert row["duration_us"] > 0
        assert previous_start is None or event["start"] > previous_start
        previous_start = event["start"]
        rows.append(row)

    commands = [r for r in rows if r["type"] == "command"]
    responses = [r for r in rows if r["type"] == "response"]
    assert len(commands) == 265 and len(responses) == 264 and init_poll == 64
    assert len(read_data) == 39
    assert len(invalid) == 1 and invalid[0]["fields"]["command"] == "63"
    assert commands[0]["event"] == "CMD0" and rows[1]["event"] == "CMD8"
    # Every command except no-response CMD0 has exactly one following response.
    for i, row in enumerate(rows):
        if row["type"] == "command" and row["event"] != "CMD0":
            assert rows[i+1]["type"] == "response"
            assert rows[i+1]["fields"]["command"] == row["fields"]["command"]
    assert all(r["fields"].get("crc") == "OK" for r in commands)
    assert all(r["fields"].get("crc") == "OK" or r["fields"]["response_type"] == "R3" for r in responses)
    assert responses[-1]["fields"]["value"] == "0x00000900"

    header = """# Session 0 — complete SD command/response transcript

Source: `Session 0.sal`, SHA-256 `""" + SOURCE_SHA + """`.
See [capture summary and validation](README.md), [individual write blocks](BLOCK-WRITES.md),
and [machine-readable command rows](commands.json).

Every genuine command and response is listed: **265 host commands + 264 card responses**.
CMD0 correctly has no response. All applicable command/response CRC7 checks pass;
R3 has no CRC7. The one malformed startup annotation is retained separately below.

**Time (s)** matches the saved Logic display: zero is its recorded trigger, not power-on,
reset release or CMD0. **Δ (µs)** is start-to-start from the previous row in this table;
it includes the previous packet's duration and intervening gaps. **Duration (µs)**
is first-to-last sampled bit, excluding the final bit's remaining clock period.
Exact sample indices and end timestamps are in `commands.json`.

CMD/response sampling uses rising CLK +16 ns at 500 MS/s. The 2 ns acquisition
resolution does not imply 2 ns absolute accuracy. DAT0 busy uses raw transitions
and can overlap command responses; it is not inserted into this sequential CMD table.
R1 state is the card state when the command arrived. READY_FOR_DATA in an early
R1 does not replace the power-up-complete bit in ACMD41's R3.

| # | Time (s) | Δ (µs) | Duration (µs) | Event | Argument / response | Meaning |
|---:|---:|---:|---:|---|---|---|
"""
    lines = [header.rstrip()]
    for row in rows:
        delta = row["delta_previous_command_response_start_us"]
        d = "—" if delta is None else f"{delta:.3f}"
        lines.append(f'| {row["number"]} | {row["logic_start_s"]} | {d} | {row["duration_us"]:.3f} | {row["event"]} | `{row["raw"]}` | {escaped(row["meaning"])} |')
    lines += ["", "## SCR data reply", "",
              "The ACMD51 R1 response is followed by this separate data packet on DAT0:", ""]
    scr = [r for r in read_data if r["fields"].get("bytes") == "8"]
    assert len(scr) == 1
    lines += [f'- At **{scr[0]["logic_start_s"]} s**, {scr[0]["duration_us"]:.3f} µs: {scr[0]["meaning"]}.',
              "", "The 38 CMD17 responses are likewise followed by 512-byte data packets.",
              "All 38 read packets passed CRC16. Their timing and fields (without image previews)",
              "are retained in `commands.json` under `read_data`.",
              "", "## Invalid startup annotation", ""]
    bad = invalid[0]
    lines += [f'The decoder emits an invalid `CMD63 0xFFFFFFFF` from **{timestamp(bad["start"])} s** to **{timestamp(bad["end"])} s**,',
              f'with received CRC7 `{bad["fields"]["crc_received"]}` versus calculated `{bad["fields"]["crc_calculated"]}`.',
              "It spans an initial clock gap and is a known decoder framing artifact. It is",
              "excluded from the genuine-command count and timing deltas, but preserved here",
              "and in `commands.json`; it is not evidence that the firmware sent CMD63.", ""]
    (args.out / "TRANSCRIPT.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    payload = {
        "source_sha256": SOURCE_SHA, "input_events_sha256": hashlib.sha256(args.events.read_bytes()).hexdigest(),
        "sample_rate_hz": RATE, "trigger_sample": TRIGGER_SAMPLE,
        "time_definition": "Logic display = (sample-trigger_sample)/sample_rate; delta is previous CMD/response start-to-start",
        "commands_and_responses": rows, "read_data": read_data, "invalid_annotations": invalid,
    }
    (args.out / "commands.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({"rows":len(rows), "commands":len(commands), "responses":len(responses),
                      "initialization_polls":init_poll, "read_packets":len(read_data),
                      "first":rows[0]["logic_start_s"], "last_end":rows[-1]["logic_end_s"]}))


if __name__ == "__main__":
    main()
