"""Export user messages and final answers from a Codex JSONL conversation.

Tool payloads, hidden reasoning, system/developer instructions, progress messages,
and injected app context are excluded. The result is historical evidence, not
the current specification. Supply an explicit source and destination.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def export(source: Path, destination: Path) -> dict:
    raw = source.read_bytes()
    messages = []
    malformed = 0
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        payload = record.get("payload", {})
        if record.get("type") != "response_item" or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role not in ("user", "assistant"):
            continue
        if role == "assistant" and payload.get("phase") != "final_answer":
            continue
        body = "\n".join(c.get("text", "") for c in payload.get("content", []))
        if role == "user":
            if body.startswith(("# AGENTS.md instructions", "<environment_context>", "<subagent_notification>")):
                continue
            for tag in ("in-app-browser-context", "external_codex_apps_open_page", "environment_context"):
                body = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", "", body, flags=re.S)
            body = body.strip()
            if not body or body.startswith("<") and not body.startswith("<send_user_message_question_reply>"):
                continue
        messages.append({"role": role, "timestamp": record.get("timestamp"),
                         "source_line": line_number, "text": body})
    destination.parent.mkdir(parents=True, exist_ok=True)
    heading = ("# October 12–13 project review conversation evidence\n\n"
               "Historical evidence exported during consolidation on October 13, 2026. "
               "User messages and assistant final answers are retained in order; tool outputs, "
               "hidden reasoning, instructions and progress updates are excluded. "
               "Assistant proposals and dated stock observations are not user approvals or current stock guarantees. "
               "For current decisions, use [the decision register](../../../docs/decisions/2026-10-13-project-baseline.md).\n\n")
    chunks = [heading]
    for i, message in enumerate(messages, 1):
        chunks.append(f"## Message {i:03d} — {message['role']} — {message['timestamp']}\n\n"
                      f"Original source line: {message['source_line']}.\n\n{message['text']}\n\n")
    destination.write_text("".join(chunks), encoding="utf-8", newline="\n")
    metadata = {"source_filename": source.name, "source_sha256_at_export": hashlib.sha256(raw).hexdigest(),
                "source_bytes_at_export": len(raw), "messages": len(messages),
                "malformed_lines_skipped": malformed,
                "scope": "User messages and final answers through the current consolidation request; source may continue growing.",
                "entries": [{k: v for k, v in m.items() if k != "text"} for m in messages]}
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {k: v for k, v in metadata.items() if k != "entries"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.destination), indent=2))
