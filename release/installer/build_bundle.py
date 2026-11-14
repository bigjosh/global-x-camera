"""Build a deterministic standalone installer ZIP; never publishes or accesses hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

HERE = Path(__file__).resolve().parent
TOP = "global-x-camera-installer-r2-v1"


def build(destination):
    from camera_install import validate_assets
    from camera_recovery import load_profiles
    validate_assets()
    load_profiles(HERE / "assets/profiles")
    paths = [HERE / name for name in (
        "Install.command", "camera_install.py", "camera_recovery.py", "camera_nor.py",
        "README.md", "requirements.txt", "build_bundle.py",
    )]
    paths += sorted(HERE.glob("test_camera_*.py"))
    paths += sorted(p for p in (HERE / "assets").rglob("*") if p.is_file())
    items = {p.relative_to(HERE).as_posix(): p.read_bytes() for p in paths}
    items["SHA256SUMS"] = "".join(
        hashlib.sha256(data).hexdigest() + "  " + name + "\n"
        for name, data in sorted(items.items())
    ).encode()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Choose a new output path; published installers are not overwritten")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(items.items()):
            info = zipfile.ZipInfo(f"{TOP}/{name}", (2026, 11, 14, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if name == "Install.command" else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    data = destination.read_bytes()
    result = dict(file=destination.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  files=len(items), firmware_tag="knobs-2026-11-14-r2", hardware_tested=False)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    build(p.parse_args().output)
