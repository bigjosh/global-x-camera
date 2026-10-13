"""Validate downloaded PDFs and regenerate the part-to-document catalog."""
import hashlib
import json
from pathlib import Path
import re
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "datasheets"

ALIASES = {
    "STM32N657X0H3Q": ["STM32N657", "STM32N6"],
    "CAM-5G0-079CLR": ["CAM-5G0-079CLR", "VD55G0"],
    "TPS62132RGTR": ["TPS62132", "TPS6213x"],
    "TPS62825DMQR": ["TPS62825", "TPS6282x"],
    "TLV70033DDCT": ["TLV700"], "TLV70028DDCR": ["TLV700"],
    "NCP115AMX120TCG": ["NCP115"], "TPS22918DBVT": ["TPS22918"],
    "RV-3028-C8-32.768kHz-1PPM-TA-QC": ["RV-3028-C8"],
    "LIS2DW12TR": ["LIS2DW12"], "W25Q128JVPIQ": ["W25Q128JV"],
    "MX30LF2G18AC-TI": ["MX30LF2G18AC"],
    "BM28B0.6-30DS/2-0.35V(51)": ["BM28B0.6-30DS", "BM28"],
    "1N4148W-13-F": ["1N4148W"],
}

def normalize(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

def esc(value):
    return str(value).replace("|", "\\|").replace("\n", " ")

def main():
    inventory = json.loads((LIB / "parts-inventory.json").read_text(encoding="utf-8"))
    records, errors = [], []
    for path in sorted(LIB.rglob("*.pdf.source.json")):
        if "_work" in path.parts:
            continue
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        pdf_path = LIB / record["path"]
        data = pdf_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            errors.append(f"Hash mismatch: {record['path']}")
        pdf = PdfReader(pdf_path)
        if len(pdf.pages) != record["pages"]:
            errors.append(f"Page count mismatch: {record['path']}")
        records.append(record)
    recorded = {r["path"] for r in records}
    for pdf in LIB.rglob("*.pdf"):
        if "_work" not in pdf.parts and pdf.relative_to(LIB).as_posix() not in recorded:
            errors.append(f"Missing provenance: {pdf.relative_to(LIB)}")
    coverage = []
    for row in inventory["bom_rows"]:
        mpn = row.get("Manufacturer Part Number")
        if not mpn:
            continue
        aliases = [normalize(x) for x in [mpn] + ALIASES.get(mpn, [])]
        docs = [r for r in records if any(alias in normalize(r.get("parts", "")) for alias in aliases)]
        primary = [r["path"] for r in docs if any(term in r["title"].lower()
                   for term in ["datasheet", "data sheet", "drawing", "specification", "module interface"])]
        coverage.append({"references": row["Designator"], "mpn": mpn,
                         "manufacturer_as_bom": row.get("Manufacturer Name", ""),
                         "documents": [r["path"] for r in docs], "primary_documents": primary})
    generic = [r for r in inventory["bom_rows"] if not r.get("Manufacturer Part Number")]
    output = {"project": "Global X Camera", "collected_date": "2026-09-05",
              "pdf_count": len(records), "total_bytes": sum(r["bytes"] for r in records),
              "validation_errors": errors, "parts": coverage, "documents": records}
    (LIB / "manifest.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# Global X Camera document library", "",
             "Initially collected 2026-09-05 from the supplied BOM, EDIF netlist, and specification; candidate documents have been added during subsequent design work. "
             "The source PDFs are stored unchanged. This is a document collection and input inventory, not a completed electrical or footprint review.", "",
             f"**{len(records)} PDFs; {len(coverage)} named BOM part entries; "
             f"{len(inventory['edif_instances'])} EDIF instances; {len(inventory['edif_nets'])} nets.** "
             f"Archive size: {sum(r['bytes'] for r in records)/1048576:.1f} MiB.", "",
             "Start with the part coverage table below. Each document has an adjacent `.pdf.source.json` "
             "record containing its source and resolved URLs, retrieval time, page count, SHA-256 hash, "
             "and any variant or source caveat. [manifest.json](manifest.json) indexes the full library. "
             "[parts-inventory.json](parts-inventory.json) preserves the BOM fields and EDIF identifiers/connectivity.", "",
             "## Coverage and remaining inputs", "",
             "- Datasheets and directly relevant hardware, package, layout, programming, and errata documents are included where available.",
             "- Generic resistors, capacitors, and inductors have no selected manufacturer part numbers. "
             "Their exact datasheets and operating curves cannot be chosen yet. General design references are labeled separately.",
             "- CR2032 identifies a cell type, not a selected battery manufacturer. The Energizer sheet is a reference candidate, not a BOM decision.",
             "- The Kyocera exact-MPN specification is a historical manufacturer-authored copy hosted on a TI forum. "
             "A current official Kyocera series sheet is also included; the two have different scope.",
             "- D2's UMW/LCSC stock-code document uses SS34B as the SMB order code and SS34 as the marking. "
             "See [power/discrete coverage notes](discretes/coverage-notes.md) before purchasing or choosing a land pattern.",
             "- The exact CAM-5G0-079CLR STEP archive was located but could not be downloaded in this session. "
             "Its verified manufacturer link and the available mechanical dimensions are recorded in [camera coverage notes](camera/README.md).",
             "- See [schematic reconstruction inputs](SCHEMATIC-RECONSTRUCTION.md) for what can be recovered from the EDIF and what must be resolved.", "",
             "Further notes: [processor document editions](processor/README.md), "
             "[memory/RTC variants](memory/coverage-notes.json), and [independent document QA](coverage-review.md).", "",
             "## Named BOM parts", "", "| References | Part number | Manufacturer in BOM | Local documents |", "| --- | --- | --- | --- |"]
    for part in sorted(coverage, key=lambda p: p["references"]):
        docs = "<br>".join(f"[{Path(p).stem}]({p})" for p in part["documents"]) or "**Download coverage pending**"
        manufacturer = part["manufacturer_as_bom"] or "Not specified in BOM; see document notes"
        lines.append(f"| {esc(part['references'])} | {esc(part['mpn'])} | {esc(manufacturer)} | {docs} |")
    lines += ["", "## Parts without manufacturer part numbers", "",
              "The original BOM groups several references with different package/rating fields. "
              "This table preserves those groups; it does not assign a grouped rating or footprint to individual components.", "",
              "| References | Description / value | Package field | Voltage rating field |", "| --- | --- | --- | --- |"]
    for row in generic:
        lines.append("| " + " | ".join(esc(value) for value in [row["Designator"], row.get("Specification", ""),
                     row.get("Package", row.get("Package or Case Code", "")), row.get("Voltage Rating", "")]) + " |")
    lines += ["", "Test pads are bare PCB features and have no component datasheet. "
              "The Tag-Connect document defines its pad/hole geometry; the project still needs its chosen signal-to-contact assignment verified.", "",
              "## Document sources", "", "| Local document | Pages | Source | Notes |", "| --- | ---: | --- | --- |"]
    for r in records:
        lines.append(f"| [{esc(r['title'])}]({r['path']}) | {r['pages']} | [Download source]({r['source_url']}) | {esc(r.get('note',''))} |")
    lines += ["", "## Refresh and verification", "",
              "The tools in `../tools/` can rebuild the inventory and index. Downloads require Python with `pypdf`; "
              "the Windows download helper uses system curl with TLS certificate verification enabled. "
              "Re-running `index_datasheets.py` verifies every archived PDF against its recorded hash and page count. "
              "The unchanged BOM, netlist, and specification remain the source inputs.", ""]
    (LIB / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pdfs": len(records), "named_parts": len(coverage),
                      "parts_without_documents": [p["mpn"] for p in coverage if not p["documents"]],
                      "parts_without_primary_documents": [p["mpn"] for p in coverage if not p["primary_documents"]],
                      "validation_errors": errors}, indent=2))
    if errors:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
