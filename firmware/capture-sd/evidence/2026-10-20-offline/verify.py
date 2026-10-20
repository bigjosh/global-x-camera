"""Verify this offline-only archive; never access hardware."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/"validation.json").read_text())
for record in data["files"]:
    raw=(HERE/record["file"]).read_bytes()
    assert len(raw)==record["bytes"], record["file"]
    assert hashlib.sha256(raw).hexdigest()==record["sha256"], record["file"]
print(f"Verified {len(data['files'])} archived files. Hardware remains unqualified.")
