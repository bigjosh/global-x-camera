"""Extract original BOM columns and EDIF connectivity without inventing pin numbers."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def parse_edif(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, root = [], None
    for token in tokens:
        if token == "(":
            value = []
            if stack:
                stack[-1].append(value)
            else:
                root = value
            stack.append(value)
        elif token == ")":
            stack.pop()
        else:
            stack[-1].append(token[1:-1] if token.startswith('"') else token)
    if stack:
        raise ValueError("Unclosed EDIF lists")
    return root

def walk(tree, kind):
    if isinstance(tree, list):
        if tree and tree[0] == kind:
            yield tree
        for child in tree:
            if isinstance(child, list):
                yield from walk(child, kind)

def names(item):
    return (item[1], item[2]) if isinstance(item, list) and item[0] == "rename" else (item, item)

def main():
    output = ROOT / "datasheets"
    output.mkdir(exist_ok=True)
    lines = (ROOT / "bom.txt").read_text(encoding="utf-8-sig").splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("Designator"))
    spans = [(m.start(), m.end()) for m in re.finditer(r'-+', lines[header_index + 1])]
    headers = [lines[header_index][start:end].strip() for start, end in spans]
    rows = []
    for line in lines[header_index + 2:]:
        if line.strip():
            row = {name: line[start:end].strip() for name, (start, end) in zip(headers, spans)}
            rows.append({key: value for key, value in row.items() if value})
    tree = parse_edif((ROOT / "netlist.edif").read_text(encoding="utf-8-sig"))
    instances = []
    for instance in walk(tree, "instance"):
        identifier, reference = names(instance[1])
        cell = next(walk(instance, "cellRef"))[1]
        instances.append({"id": identifier, "reference": reference, "cell": cell})
    nets = []
    for net in walk(tree, "net"):
        identifier, name = names(net[1])
        pins = []
        for port in walk(net, "portRef"):
            reference = next(walk(port, "instanceRef"), None)
            pins.append({"port": port[1], "instance": reference[1] if reference else None})
        nets.append({"id": identifier, "name": name, "connections": pins})
    cells = []
    for cell in walk(tree, "cell"):
        identifier, name = names(cell[1])
        definitions = []
        for port in walk(cell, "port"):
            port_id, port_name = names(port[1])
            direction = next(walk(port, "direction"), ["direction", None])[1]
            definitions.append({"id": port_id, "name": port_name, "direction": direction})
        cells.append({"id": identifier, "name": name,
                      "ports": [p["name"] for p in definitions], "port_definitions": definitions})
    by_instance = {instance["id"]: instance for instance in instances}
    by_cell = {cell["id"]: cell for cell in cells}
    errors = []
    endpoint_nets = {}
    for net in nets:
        for connection in net["connections"]:
            instance = by_instance.get(connection["instance"])
            cell = by_cell.get(instance["cell"]) if instance else None
            if not cell or connection["port"] not in {p["id"] for p in cell["port_definitions"]}:
                errors.append({"net": net["name"], "unresolved_connection": connection})
            key = (connection["instance"], connection["port"])
            if key in endpoint_nets and endpoint_nets[key] != net["id"]:
                errors.append({"connection_on_multiple_nets": connection})
            endpoint_nets[key] = net["id"]
    data = {"source_files": ["bom.txt", "netlist.edif"], "bom_rows": rows,
            "edif_instances": instances, "edif_cells": cells, "edif_nets": nets,
            "edif_property_count": len(list(walk(tree, "property"))),
            "edif_port_implementation_count": len(list(walk(tree, "portImplementation"))),
            "connectivity_validation": {"connected_endpoints": len(endpoint_nets), "errors": errors}}
    (output / "parts-inventory.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"BOM: {len(rows)} rows; EDIF: {len(instances)} instances, {len(nets)} nets")
    print(f"EDIF endpoint validation: {len(endpoint_nets)} unique endpoints; {len(errors)} unresolved or conflicting entries")
    for row in rows:
        if row.get("Manufacturer Part Number") or not row["Designator"].startswith(("C", "R", "TP")):
            print(json.dumps({k: row.get(k, "") for k in ["Designator", "Manufacturer Part Number", "Manufacturer Name", "Datasheet URL", "Machine Datasheet URL", "Specification"]}, ensure_ascii=True))

if __name__ == "__main__":
    main()
