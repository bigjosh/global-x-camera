"""Offline PD12 overlays on frozen legacy or explicitly pinned profile builds.

Never modifies their inputs or invokes hardware. Outputs are new directories.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "firmware/capture-timing"))
from build_raw10 import checked_manifest, compile_sources, make_image, inspect_image, sha, replace, write_manifest
import importlib.util
spec = importlib.util.spec_from_file_location("capture_storage_builder", HERE.parent / "build.py")
capture_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_builder)

BASELINES = {
    "standby": "7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63",
    "awake": "9ffc2c1cbaacf9f60258343ac6a061b35fb62f8b62b42c1a5b50ccc5f432f5cd",
}
MODULE_SHA = "91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844"
EVENTS = {
    1: "receiver main entry; first stage and sensor START already completed",
    2: "first sensor STROBE rising IRQ observed; not exact physical exposure edge",
    3: "first complete frame IRQ observed",
    4: "SAVE module entered; beginning target timing",
    5: "SD initialization completed successfully",
    6: "FAT32 mount completed successfully",
    7: "PNG encoding completed; final callback buffer can still need flushing",
    8: "photo_fs_finish completed: closed/renamed PNG and card-ready checks",
    9: "SD deinit, cache clean/disable, profile-selected validation and final snapshots complete; DONE follows",
    10: "immediately before Standby WFI, or awake diagnostic completion park; intent only",
}

def symbols(folder):
    return {m[2]: int(m[1], 16) for m in re.finditer(
        r"^([0-9a-fA-F]+)\s+\w\s+(\S+)$", (folder / "symbols.txt").read_text(), re.M)}

def copied_sources(original, out, manifest):
    out.mkdir(parents=True, exist_ok=False)
    sources = []
    for path in manifest["sources"]:
        src = (ROOT / path).resolve()
        relative = src.relative_to(original.resolve())
        dst = out / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        sources.append(dst)
    return sources

def markers(out, sources):
    for name in ("phase_gpio.c", "phase_gpio.h"):
        dst = out / name
        dst.write_bytes((HERE / name).read_bytes())
        sources.append(dst)

def flags_for(manifest, original, out):
    return [f"-I{out}"] + [f.replace(str(original), str(out)) for f in manifest["compile_flags"]]

def patch(path, old, new, expected=1):
    path.write_text(replace(path.read_text(encoding="utf-8"), old, new, expected=expected), encoding="utf-8")

def phase_metadata():
    return dict(pin="PD12", header="CN15.21 / CN14.1 (Arduino D8)",
        idle_level=0, nominal_cpu_hz=400000000, pulse_high_cycles_per_id=200,
        nominal_high_us_per_id=0.5, poll_limit=4096, events=EVENTS,
        timing_limit="Diagnostic software observations; interrupt latency and pulse-call overhead apply. "
                     "Widths need external qualification; event10 does not itself prove Standby.")

def build_module(original, out, expected_sha=MODULE_SHA):
    md = checked_manifest(original)
    assert sha((original / "save.bin").read_bytes()) == expected_sha
    assert md["binary_sha256"] == expected_sha and md["data_cache_enabled"]
    sources = copied_sources(original, out, md)
    markers(out, sources)
    path = out / "save_main.c"
    patch(path, '#include "png16.h"', '#include "png16.h"\n#include "phase_gpio.h"')
    patch(path, "    int result=-203;", "    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(4U);\n    int result=-203;")
    patch(path, "    if(result) goto done;\n    report[P_STAGE]=3;", "    if(result) goto done;\n    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(5U);\n    report[P_STAGE]=3;")
    patch(path, "    if(result) goto done;\n    if(op==SAVE_OP_SAVE) result=save_image", "    if(result) goto done;\n    if(op==SAVE_OP_SAVE) (void)phase_gpio_emit(6U);\n    if(op==SAVE_OP_SAVE) result=save_image")
    patch(path, "    if(png_result) return png_result;", "    if(png_result) return png_result;\n    (void)phase_gpio_emit(7U);")
    patch(path, "    if((result=photo_fs_finish())) return result;", "    if((result=photo_fs_finish())) return result;\n    (void)phase_gpio_emit(8U);")
    patch(path, "    pair(P_COMPLETE_LO,clock_now());", "    if(op==SAVE_OP_SAVE && !result) (void)phase_gpio_emit(9U);\n    pair(P_COMPLETE_LO,clock_now());")
    flags = flags_for(md, original, out)
    raw, size = compile_sources(out, [s for s in sources if s.suffix in (".c", ".S") and "vendor" not in s.parts],
                                flags, out / "save.ld", "save", libc=True)
    sym = symbols(out)
    assert sym["save_entry"] == 0x34320000 and len(raw) % 4 == 0
    assert len(raw) <= 0x8000 and sym["_ebss"] <= 0x343A0000
    md = copy.deepcopy(md)
    md.update(hardware_status="untested", binary_bytes=len(raw), binary_sha256=sha(raw),
        entry_address=hex(sym["save_entry"] | 1), bench_entry_address=hex(sym["save_bench_entry"] | 1),
        park_address=hex(sym["save_park"]), bss_start=hex(sym["_sbss"]), bss_end=hex(sym["_ebss"]),
        buffer_address=hex(sym["output_buffer"]), read_buffer_address=hex(sym["scratch"]),
        compile_flags=flags, size=size, phase_markers=phase_metadata(), uninstrumented_module_sha256=expected_sha)
    write_manifest(out, md, sources)
    return md, raw

def build_late(base, out, rdir, module_header):
    original = base / "late"
    md = checked_manifest(original)
    sources = copied_sources(original, out, md)
    markers(out, sources)
    (out / "save_module_config.h").write_bytes(module_header.read_bytes())
    path = out / "completion.c"
    patch(path, '#include "status_leds.h"', '#include "status_leds.h"\n#include "phase_gpio.h"')
    patch(path, "    publish(LPC_STATE_ARMED);\n    __DSB(); __ISB();", "    publish(LPC_STATE_ARMED);\n    (void)phase_gpio_emit(10U);\n    __DSB(); __ISB();")
    flags = flags_for(md, original, out)
    raw, size = compile_sources(out, [s for s in sources if s.suffix in (".c", ".S")], flags, out / "late.ld", "late")
    sym = symbols(out)
    assert sym["late_completion_entry"] == 0x343C0000 and len(raw) <= 8192 and len(raw) % 4 == 0
    row = re.search(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+\s", size, re.M)
    assert row and int(row[2]) == 0 and int(row[3]) == 0
    md = copy.deepcopy(md)
    md.update(hardware_status="untested", binary_bytes=len(raw), binary_sha256=sha(raw), crc32=hex(zlib.crc32(raw)),
              sleep_idle_address=hex(sym["status_led_sleep_idle"]), failure_park_address=hex(sym["low_power_failure_idle"]),
              return_park_address=hex(sym["low_power_return_idle"]), size=size, compile_flags=flags,
              section_sizes=dict(text=int(row[1]), data=0, bss=0), phase_markers=phase_metadata())
    write_manifest(out, md, sources)
    keys = ("flash_offset", "load_address", "entry_address", "binary_bytes", "binary_sha256", "crc32",
            "loader_proof_address", "sleep_idle_address", "failure_park_address", "return_park_address",
            "no_initialized_data_or_bss", "section_sizes")
    identity = {k: md[k] for k in keys}
    identity.update(manifest_path=str(out / "manifest.json"), manifest_sha256=sha((out / "manifest.json").read_bytes()))
    (rdir / "late_config.h").write_text(
        f"#define LATE_FLASH_OFFSET 57344U\n#define LATE_LOAD_ADDRESS 0x343c0000U\n"
        f"#define LATE_ENTRY_ADDRESS 0x343c0001U\n#define LATE_BYTES {len(raw)}U\n"
        f"#define LATE_CRC32 0x{zlib.crc32(raw):08x}U\n")
    return raw, identity

def build(base, module, out, mode, expected_base_sha=None, expected_module_sha=None):
    base, module, out = base.resolve(), module.resolve(), out.resolve()
    pm = checked_manifest(base / "staged")
    rm = checked_manifest(base / "receiver")
    old_sector = (base / "staged/capture_sector_0.bin").read_bytes()
    old_prefix = (base / "staged/stage1.bin").read_bytes()
    if (expected_base_sha is None) != (expected_module_sha is None):
        raise ValueError("Explicit base and module identities must be supplied together")
    pinned_base = expected_base_sha or BASELINES[mode]
    pinned_module = expected_module_sha or MODULE_SHA
    assert sha(old_sector) == pinned_base and pm["program_sha256"] == pinned_base
    assert sha(old_prefix) == pm["stage1_raw_sha256"]
    assert sha((base / "receiver/capture.bin").read_bytes()) == rm["raw_sha256"]
    if expected_base_sha:
        module_manifest = checked_manifest(module)
        assert module_manifest.get("report_schema") == 2
        assert rm.get("diagnostics_profile") in ("normal", "diagnostic")
        assert module_manifest["diagnostics_profile"] == rm["diagnostics_profile"] == pm["diagnostics_profile"]
        assert rm["capture_sd"]["module_sha256"] == pinned_module
        assert bool(rm["capture_sd"]["awake_completion"]) == (mode == "awake")
        if mode == "standby":
            assert rm["low_power"]["mode"] == "standby"
    out.mkdir(parents=True, exist_ok=False)
    md, module_raw = build_module(module, out / "module", pinned_module)
    rdir, pdir = out / "receiver", out / "staged"
    sources = copied_sources(base / "receiver", rdir, rm)
    markers(rdir, sources)
    (rdir / "module-save.bin").write_bytes(module_raw)
    (rdir / "module-manifest.json").write_bytes((out / "module/manifest.json").read_bytes())
    config = rdir / "save_module_config.h"
    config.write_text(f"#define SAVE_FLASH_OFFSET 24576U\n#define SAVE_LOAD_ADDRESS 0x34320000U\n"
                      f"#define SAVE_BYTES {len(module_raw)}U\n#define SAVE_CRC32 0x{zlib.crc32(module_raw):08x}U\n"
                      f"#define SAVE_DEFAULT_MODE {md['default_mode']}U\n")
    path = rdir / "capture.c"
    patch(path, '#include "status_leds.h"', '#include "status_leds.h"\n#include "phase_gpio.h"')
    patch(path, "  fast_init();\n  event(2);", "  fast_init();\n  check(0xD0,!phase_gpio_init());\n  (void)phase_gpio_emit(1U);\n  event(2);")
    patch(path, "    if(fast_strobes==1U) status_led_proof_phase(STATUS_LED_ACQUIRE,LED_P_BLUE_CYCLE);",
          "    if(fast_strobes==1U) {\n      status_led_proof_phase(STATUS_LED_ACQUIRE,LED_P_BLUE_CYCLE);\n      (void)phase_gpio_emit(2U);\n    }")
    patch(path, "      FAST[31]=fast_strobes;", "      FAST[31]=fast_strobes;\n      (void)phase_gpio_emit(3U);")
    late_raw, late_identity = None, None
    if mode == "standby":
        late_raw, late_identity = build_late(base, out / "late", rdir, config)
    else:
        sleep = rdir / "sleep.c"
        patch(sleep, '#include "status_leds.h"', '#include "status_leds.h"\n#include "phase_gpio.h"')
        patch(sleep, '  __asm volatile(', '  (void)phase_gpio_emit(10U);\n  __asm volatile(')
    # Explicit diagnostic padding avoids downstream prefix immediate-size
    # optimizations moving literal addresses used by early recovery. Awake
    # uses the already-qualified v59 receiver length; standby needs four bytes.
    # Data remains one final SystemCoreClock word. Identity assertions below
    # remain authoritative; no early-guard bytes or literals may change.
    if mode == "awake":
        # Full diagnostics needs 64 more bytes than the normal/legacy layout.
        # Both end with the sole mutable SystemCoreClock word, and the prefix
        # guard identity is verified after linking rather than inferred here.
        data_address = 0x34303D04 if rm.get("diagnostics_profile") == "diagnostic" else 0x34303CC4
        patch(rdir / "capture.ld", "  .data :",
              f"  .data 0x{data_address:08X} : /* Fixed profile layout; final clock word. */")
    else:
        patch(rdir / "capture.ld", "    *(.rodata*)        /* .rodata* sections (constants, strings, etc.) */",
              "    *(.rodata*)        /* .rodata* sections (constants, strings, etc.) */\n"
              "    LONG(0); /* Explicit diagnostic layout padding, included in CRC. */")
    flags = flags_for(rm, base / "receiver", rdir)
    raw, size = compile_sources(rdir, [s for s in sources if s.suffix in (".c", ".s", ".S")],
                                flags, rdir / "capture.ld", "capture", libc=True)
    assert len(raw) <= 0x4000 and len(raw) % 4 == 0
    sym = symbols(rdir)
    rm = copy.deepcopy(rm)
    rm.update(hardware_status="untested", raw_bytes=len(raw), raw_sha256=sha(raw), size=size,
              entry_point=hex(struct.unpack_from("<I", raw, 4)[0]), compile_flags=flags,
              failure_park_address=hex(sym["fast_failure_idle"]), capture_source_path=str(path),
              phase_markers=phase_metadata(), uninstrumented_sector_sha256=pinned_base)
    rm["capture_sd"].update(module_bytes=len(module_raw), module_sha256=sha(module_raw))
    if late_identity:
        rm["low_power"].update(late_module=late_identity, loader_failure_park_address=hex(sym["late_completion_failure_idle"]))
        rm["sleep_idle_address"] = late_identity["sleep_idle_address"]
    else:
        rm["sleep_idle_address"] = hex(sym["status_led_sleep_idle"])
    write_manifest(rdir, rm, sources)
    psources = copied_sources(base / "staged", pdir, pm)
    pflags = [f for f in flags_for(pm, base / "staged", pdir)
              if not f.startswith(("-DSTAGE2_BYTES=", "-DSTAGE2_EXPECTED_CRC32="))]
    pflags += [f"-DSTAGE2_BYTES={len(raw)}U", f"-DSTAGE2_EXPECTED_CRC32=0x{zlib.crc32(raw):08x}U"]
    prefix, psize = compile_sources(pdir, [s for s in psources if s.suffix in (".c", ".S")],
                                    pflags, pdir / "stage1.ld", "stage1")
    offsets = capture_builder.check_recovery_identity(pdir, prefix, old_prefix, len(raw))
    assert symbols(pdir)["recovery_gpio_park"] == 0x3418078C
    first = next((i for i, (x, y) in enumerate(zip(prefix, old_prefix)) if x != y), min(len(prefix), len(old_prefix)))
    boot = make_image(prefix)
    sector = capture_builder.pack_sector(old_sector, boot, raw, module_raw, late_raw)
    (pdir / "stage1_boot.bin").write_bytes(boot)
    (pdir / "stage2.bin").write_bytes(raw)
    (pdir / "capture_sector_0.bin").write_bytes(sector)
    pm = copy.deepcopy(pm)
    pm.update(hardware_status="untested", stage1=inspect_image(boot), size=psize, compile_flags=pflags,
              stage1_raw_bytes=len(prefix), stage1_raw_sha256=sha(prefix), stage2_bytes=len(raw),
              stage2_sha256=sha(raw), stage2_crc32=hex(zlib.crc32(raw)),
              stage2_build_manifest=str(rdir / "manifest.json"),
              stage2_manifest_sha256=sha((rdir / "manifest.json").read_bytes()),
              program_sha256=sha(sector), phase_markers=phase_metadata(),
              uninstrumented_sector_sha256=pinned_base)
    pm["capture_sd"].update(module_bytes=len(module_raw), module_sha256=sha(module_raw),
                            unchanged_prefix_leading_bytes=first, checked_recovery_literal_offsets=offsets)
    if late_identity:
        pm["low_power"] = copy.deepcopy(rm["low_power"])
    write_manifest(pdir, pm, psources)
    identity = dict(mode=mode, out=str(out), sector_sha256=sha(sector), receiver_bytes=len(raw),
                    receiver_growth_bytes=len(raw)-len((base / "receiver/capture.bin").read_bytes()),
                    prefix_sha256=sha(prefix), unchanged_prefix_bytes=first,
                    module_bytes=len(module_raw), module_sha256=sha(module_raw),
                    module_manifest=str(out / "module/manifest.json"),
                    recovery_literals_verified=offsets, phase_markers=phase_metadata(),
                    builder_sha256=sha(Path(__file__).read_bytes()))
    (out / "phase-build.json").write_text(json.dumps(identity, indent=2)+"\n")
    return identity

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=BASELINES, required=True)
    parser.add_argument("--expected-base-sha256", help="Explicit profile-aware input sector identity")
    parser.add_argument("--expected-module-sha256", help="Explicit profile-aware input module identity")
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.module, args.out, args.mode,
                          args.expected_base_sha256, args.expected_module_sha256), indent=2))

if __name__ == "__main__":
    main()
