"""Catalog unchanged Flux downloads and audit their exported coverage."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from inventory_parts import names, parse_edif, walk

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "imports" / "flux" / "2026-09-05"


def edif_summary(path):
    tree = parse_edif(path.read_text(encoding="utf-8-sig"))
    instances = {names(i[1])[0]: names(i[1])[1] for i in walk(tree, "instance")}
    cells = {names(i[1])[1]: next(walk(i, "cellRef"))[1] for i in walk(tree, "instance")}
    port_names = {names(c[1])[0]: {names(p[1])[0]: names(p[1])[1] for p in walk(c, "port")}
                  for c in walk(tree, "cell")}
    nets = {}
    for net in walk(tree, "net"):
        connections = []
        for port in walk(net, "portRef"):
            ref = next(walk(port, "instanceRef"))[1]
            connections.append([instances[ref], port[1]])
        nets[names(net[1])[1]] = sorted(connections)
    display_nets = {net: sorted([ref, port_names[cells[ref]][port]] for ref, port in pins)
                    for net, pins in nets.items()}
    return {"instances": cells, "nets": nets, "display_nets": display_nets,
            "counts": {"instances": len(instances), "nets": len(nets),
                       "endpoints": sum(len(p) for p in nets.values())}}


def main():
    native = json.loads((SNAPSHOT / "bigjosh-global-x-camera.flx").read_text(encoding="utf-8"))
    original = edif_summary(ROOT / "netlist.edif")
    fresh = edif_summary(SNAPSHOT / "bigjosh-global-x-camera.edif")
    xml = ET.parse(SNAPSHOT / "global-x-camera.ipc2581c").getroot()
    ns = {"i": xml.tag.split("}")[0][1:]}
    components = [e.attrib for e in xml.findall(".//i:Component", ns)]
    net_sets = [e for e in xml.findall(".//i:Set", ns) if e.get("net")]
    net_names = sorted({e.get("net") for e in net_sets})
    pin_records = [e.attrib for s in net_sets for e in s.findall(".//i:PinRef", ns)]
    generic_pins = sorted({e["componentRef"] for e in pin_records if e.get("pin") == "~"})
    synthetic = [e["refDes"] for e in components if e["refDes"].startswith("NOREF_")]
    ipc_refs = {e["refDes"] for e in components if e["refDes"] not in synthetic}
    bom_file = next(SNAPSHOT.glob("*BOM*.zip"))
    with zipfile.ZipFile(bom_file) as archive:
        if archive.testzip() is not None:
            raise ValueError("BOM ZIP failed CRC validation")
        bom_members = archive.namelist()
    audit = {
        "original_edif": original["counts"],
        "fresh_edif": fresh["counts"],
        "edif_instance_cell_assignments_equal": original["instances"] == fresh["instances"],
        "edif_net_names_and_endpoint_memberships_equal": original["nets"] == fresh["nets"],
        "edif_net_names_and_display_port_multisets_equal": original["display_nets"] == fresh["display_nets"],
        "edif_non_J3_endpoint_memberships_equal": {
            n: [p for p in pins if p[0] != "J3"] for n, pins in original["nets"].items()
        } == {n: [p for p in pins if p[0] != "J3"] for n, pins in fresh["nets"].items()},
        "edif_identifier_differences": [
            {"net": net,
             "old_only": sorted(map(list, {tuple(p) for p in original["nets"].get(net, [])} - {tuple(p) for p in fresh["nets"].get(net, [])})),
             "fresh_only": sorted(map(list, {tuple(p) for p in fresh["nets"].get(net, [])} - {tuple(p) for p in original["nets"].get(net, [])}))}
            for net in sorted(set(original["nets"]) | set(fresh["nets"]))
            if original["nets"].get(net) != fresh["nets"].get(net)
        ],
        "edif_comparison_note": "All observed endpoint differences concern J3 aliases (&__N / ~_N), whose native terminals have the repeated name '~'. Export-generated suffixes are not established physical pin numbers. This difference does not by itself establish a changed circuit or equivalent connector wiring; reconcile against native UUID/pin mapping and IPC geometry.",
        "fresh_edif_switches": sorted(r for r in fresh["instances"] if r.startswith("SW")),
        "ipc2581": {
            "root_tag": xml.tag, "root_attributes": xml.attrib,
            "component_records": len(components), "synthetic_root_component_refs": synthetic,
            "non_synthetic_component_count": len(ipc_refs),
            "edif_refs_absent_from_ipc_components": sorted(set(fresh["instances"]) - ipc_refs),
            "ipc_refs_absent_from_edif": sorted(ipc_refs - set(fresh["instances"])),
            "package_count": len(xml.findall(".//i:Package", ns)),
            "net_names": net_names, "net_names_equal_edif": set(net_names) == set(fresh["nets"]),
            "net_assigned_pinref_record_count": len(pin_records),
            "components_with_ambiguous_tilde_pinrefs": generic_pins,
            "stackups": [e.attrib for e in xml.findall(".//i:Stackup", ns)],
            "limitations": [
                "Valid XML was parsed; this is not IPC schema or electrical validation.",
                "Nets are represented by Set/@net and descendant Pad/PinRef records.",
                "Repeated geometry across layers duplicates PinRef records; counts are not unique endpoints.",
                "PinRef uses logical names, including repeated '~' connector names. A complete pin-level connectivity comparison requires geometry/native pin mapping.",
                "Component mountType values have not been validated; retain native package data and manufacturer drawings."
            ]
        },
        "bom_zip_members": bom_members,
    }
    (SNAPSHOT / "export-audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    files = []
    for name, kind in [
        ("bigjosh-global-x-camera.flx", "Flux project (.flx)"),
        ("global-x-camera.ipc2581c", "IPC-2581C (.ipc2581c)"),
        (bom_file.name, "Bill of Materials (.zip)"),
        ("bigjosh-global-x-camera.edif", "Schematic Netlist (.edif)"),
    ]:
        path = SNAPSHOT / name
        files.append({"file": name, "export_menu_item": kind, "bytes": path.stat().st_size,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "download_file_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
    manifest = {
        "source_project_url": "https://www.flux.ai/bigjosh/global-x-camera~2a",
        "retrieved_on": "2026-09-05", "method": "Flux project Export menu in authenticated Chrome session",
        "source_exports_modified": False,
        "native_metadata": {k: native.get(k) for k in ["name", "slug", "short_id", "latestActionRecordUid", "updated_at"]},
        "timestamp_note": "Download modification times are local filesystem evidence, not a guarantee of a shared export revision. Native metadata is retained in its original representation.",
        "files": files,
    }
    (SNAPSHOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(files), "fresh_edif": audit["fresh_edif"],
                      "edif_connections_equal": audit["edif_net_names_and_endpoint_memberships_equal"],
                      "ipc_components": len(ipc_refs), "ipc_net_names": len(net_names),
                      "ipc_missing_refs": audit["ipc2581"]["edif_refs_absent_from_ipc_components"],
                      "ipc_ambiguous_pinrefs": generic_pins}, indent=2))


if __name__ == "__main__":
    main()
