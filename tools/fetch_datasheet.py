"""Download an unchanged source document and record its provenance.

Usage: python tools/fetch_datasheet.py URL RELATIVE_PDF --parts PARTS --title TITLE
       [--source-page URL] [--note NOTE]
Paths are relative to datasheets/. PDF content is checked before it is saved.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1] / "datasheets"

def get_bytes(url):
    """Use the Windows certificate store via system curl when available."""
    curl = shutil.which("curl.exe") if os.name == "nt" else None
    if curl:
        with tempfile.TemporaryDirectory(prefix="camera-doc-") as temporary:
            target = Path(temporary) / "download"
            result = subprocess.run(
                [curl, "--fail", "--location", "--silent", "--show-error",
                 "--retry", "1", "--connect-timeout", "15", "--max-time", "90",
                 "--user-agent", "Mozilla/5.0", "--output", str(target),
                 "--write-out", "%{url_effective}", url],
                capture_output=True, text=True, timeout=200, check=False)
            if result.returncode:
                raise RuntimeError(f"curl {result.returncode}: {result.stderr.strip()}")
            return target.read_bytes(), result.stdout.strip()
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read(), response.url

def fetch(url, relative_path, parts, title, source_page=None, note=""):
    target = (ROOT / relative_path).resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Output must stay in datasheets/")
    target.parent.mkdir(parents=True, exist_ok=True)
    data, final_url = get_bytes(url)
    if not data.lstrip().startswith(b"%PDF-"):
        raise ValueError(f"Response is not a PDF: {url}")
    pdf = PdfReader(BytesIO(data))
    page_count = len(pdf.pages)
    if page_count < 1:
        raise ValueError("Empty PDF")
    first_page = (pdf.pages[0].extract_text() or "")
    target.write_bytes(data)
    record = {
        "path": target.relative_to(ROOT).as_posix(), "title": title,
        "parts": parts, "source_url": url, "resolved_url": final_url,
        "source_page": source_page, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "bytes": len(data), "pages": page_count,
        "sha256": hashlib.sha256(data).hexdigest(), "note": note,
        "first_page_excerpt": " ".join(first_page.split())[:1600],
    }
    target.with_suffix(target.suffix + ".source.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=True))
    return record

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("relative_path")
    parser.add_argument("--parts", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-page")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    fetch(args.url, args.relative_path, args.parts, args.title, args.source_page, args.note)
