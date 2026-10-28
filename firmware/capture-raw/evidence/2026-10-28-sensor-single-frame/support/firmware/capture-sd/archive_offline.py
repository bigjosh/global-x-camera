"""Archive a fixed allowlist of offline builds and failed-access logs; no hardware."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"evidence/2026-10-20-offline"
FILES={
    "module.bin":"tmp/bringup/save-module-v4-20261020/save.bin",
    "module-manifest.json":"tmp/bringup/save-module-v4-20261020/manifest.json",
    "v47b-sector.bin":"tmp/bringup/capture-sd-v47b-build-20261020/staged/capture_sector_0.bin",
    "v47b-staged-manifest.json":"tmp/bringup/capture-sd-v47b-build-20261020/staged/manifest.json",
    "v47b-receiver-manifest.json":"tmp/bringup/capture-sd-v47b-build-20261020/receiver/manifest.json",
    "v47b-capture.c":"tmp/bringup/capture-sd-v47b-build-20261020/receiver/capture.c",
    "v47b-save_loader.c":"tmp/bringup/capture-sd-v47b-build-20261020/receiver/save_loader.c",
    "v47b-save_module_config.h":"tmp/bringup/capture-sd-v47b-build-20261020/receiver/save_module_config.h",
    "v46-sector.bin":"tmp/bringup/capture-sd-v46-awake-20261020/staged/capture_sector_0.bin",
    "v46-staged-manifest.json":"tmp/bringup/capture-sd-v46-awake-20261020/staged/manifest.json",
    "png-host-comparison.json":"tmp/bringup/png16-host-20261020/report.json",
    "recovery-04-cli.log":"tmp/bringup/capture-sd-20261020/v45b-recovery-04/cli-01.log",
    "recovery-04-calls.jsonl":"tmp/bringup/capture-sd-20261020/v45b-recovery-04/calls.jsonl",
}
EXPECTED={
    "module.bin":"6661d3b54ea9b1c10d6618b0e9da30a9791a12beda09987aac3f2b315fa5f4ba",
    "v47b-sector.bin":"93f1ed2687bb5a128b74d6ea43df7f564330c882e8e5bd9b932d454c8b091231",
    "v46-sector.bin":"3f64bb86b73c44ba403a2a150f058eb0daf661c4b1ac41e6ca4634073bdd7cae",
}

def digest(data): return hashlib.sha256(data).hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,relative in FILES.items():
        source=ROOT/relative
        data=source.read_bytes()
        if name in EXPECTED and digest(data)!=EXPECTED[name]:
            raise ValueError("Unreviewed build changed: "+name)
        target=OUT/name
        if target.exists() and target.read_bytes()!=data:
            raise ValueError("Existing archive differs: "+name)
        target.write_bytes(data)
        records.append(dict(file=name,source=relative,bytes=len(data),sha256=digest(data)))
    # Select only the terminal restoration record, not a whole instrument log.
    events=[json.loads(line) for line in (ROOT/"tmp/bringup/capture-sd-20261020-js.jsonl").read_text().splitlines()]
    stopped=[x for x in events if x.get("event")=="stopped"][-1]
    assert stopped["ok"] and stopped["range"]==128
    data=(json.dumps(stopped,indent=2)+"\n").encode()
    (OUT/"js-stopped.json").write_bytes(data)
    records.append(dict(file="js-stopped.json",bytes=len(data),sha256=digest(data)))
    validation=dict(
        hardware_status="blocked before programming; offline evidence only",
        installed_image="v45b unchanged; not reread this pass",
        physical_sd_write_or_format=False,
        tests=dict(png=11,fatfs=14,sd_protocol_cases=13,ram_runner=8,maintenance=20,
                   energy_analysis=10,joulescope_helpers=22),
        build_checks=dict(module_warnings_as_errors=True,
                          integrated_receiver_prefix_build=True,
                          early_recovery_identity=True),
        archived_camera_images=False,archived_sd_contents=False,files=records)
    (OUT/"validation.json").write_text(json.dumps(validation,indent=2)+"\n")
    print(json.dumps(dict(archived=len(records),directory=str(OUT))))

if __name__=="__main__": main()
