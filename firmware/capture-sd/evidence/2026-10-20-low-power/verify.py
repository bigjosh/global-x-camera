"""Verify this archive's bytes, recipes and four-payload layout offline."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify(root):
    root = root.resolve()
    plan = json.loads((root / "archive-plan.json").read_text(encoding="utf-8"))
    require(plan["schema"] == 2, "Unknown archive schema")
    entries = plan["source_index"]
    expected = {e["archived_path"] for e in entries}
    require(len(expected) == len(entries), "Duplicate archive path")
    found = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    found = {p for p in found if "__pycache__" not in Path(p).parts}
    require(found-{"archive-plan.json"} == expected, "Missing or unlisted archive files")
    origins = {}
    total = 0
    for entry in entries:
        path = (root / entry["archived_path"]).resolve()
        require(path.is_relative_to(root), "Archive path escapes root")
        raw = path.read_bytes()
        require(len(raw) == entry["archived_bytes"] and
                digest(raw) == entry["archived_sha256"], "Hash mismatch: " + str(path))
        if entry.get("encoding") == "gzip":
            unpacked = gzip.decompress(raw)
            require(len(unpacked) == entry["original_bytes"] and
                    digest(unpacked) == entry["original_sha256"],
                    "Decompressed primary input differs")
        origins.setdefault(entry["original_path"].replace("\\", "/"), []).append(entry)
        total += len(raw)
    require(total == plan["archive_bytes"], "Archive byte count differs")
    payloads, manifests = {}, {}
    for name, recipe in plan["recipe"].items():
        path = root / recipe["binary"]
        raw = path.read_bytes()
        payloads[name] = raw
        require(digest(raw) == recipe["binary_sha256"] == plan["build_identity"][name],
                "Binary identity mismatch: " + name)
        require(all(not re.search(r"[A-Za-z]:[\\/]|tmp[\\/]", flag)
                    for flag in recipe["compile_flags"] if "${ARCHIVE}" not in flag),
                "Nonportable compile flag")
        require(all((root / source).is_file() for source in recipe["sources"]),
                "Missing recipe translation unit")
        require((root / recipe["linker"]).is_file(), "Missing recipe linker script")
        manifest = json.loads((path.parent / "manifest.json").read_text())
        manifests[name] = manifest
        for original, checksum in {**manifest["sources"],
                                   **manifest.get("generator_inputs", {})}.items():
            matches = origins.get(original.replace("\\", "/"), [])
            require(any(e["original_sha256"] == checksum ==
                        e["archived_sha256"] for e in matches),
                    "Frozen input is not preserved: " + original)
    require(set(payloads) == {"prefix", "receiver", "module", "late"}, "Four payloads required")
    pm, rm, mm, lm = (manifests[n] for n in ("prefix", "receiver", "module", "late"))
    p, r, m, late = (payloads[n] for n in ("prefix", "receiver", "module", "late"))
    boot = (root / "build/prefix/stage1_boot.bin").read_bytes()
    sector = (root / "build/prefix/capture_sector_0.bin").read_bytes()
    require(len(sector) == 65536 and digest(sector) == pm["program_sha256"] ==
            plan["build_identity"]["sector"], "Sector identity mismatch")
    require(sector[:len(boot)] == boot and len(boot) <= 0x2000, "ROM wrapper differs")
    require(boot[0x400:0x400+len(p)] == p and len(p) == pm["stage1_raw_bytes"] == 5140,
            "Raw prefix differs from ROM wrapper")
    for offset, raw, end in ((0x2000, r, 0x6000), (0x6000, m, 0xE000),
                             (0xE000, late, 65536)):
        require(0 < len(raw) <= end-offset, "Payload overlap")
        require(sector[offset:offset+len(raw)] == raw, "Sector payload mismatch")
        require(sector[offset+len(raw):end] == b"\xff"*(end-offset-len(raw)),
                "Unexpected non-FF unused payload range")
    require(digest(r) == rm["raw_sha256"] == pm["stage2_sha256"] and
            len(r) == rm["raw_bytes"] == pm["stage2_bytes"] and
            zlib.crc32(r) == int(pm["stage2_crc32"], 0), "Receiver binding differs")
    require(digest(m) == mm["binary_sha256"] and len(m) == mm["binary_bytes"] == 27420,
            "Module binding differs")
    require(int(mm["load_address"], 0) == 0x34320000 and
            0x34320000+len(m) <= int(mm["bss_start"], 0) <=
            int(mm["bss_end"], 0) <= 0x343A0000 and
            int(mm["stack_floor"], 0) == 0x343A0000 and
            int(mm["stack_top"], 0) == 0x343B0000, "Module/stack bounds differ")
    require(digest(late) == lm["binary_sha256"] and len(late) == lm["binary_bytes"] and
            len(late) % 4 == 0 and 0 < len(late) <= 8192 and
            int(lm["load_address"], 0) == 0x343C0000 and
            int(lm["entry_address"], 0) == 0x343C0001 and
            lm["flash_offset"] == 0xE000 and
            zlib.crc32(late) == int(lm["crc32"], 0) and
            lm["section_sizes"] == dict(text=len(late), data=0, bss=0) and
            lm["no_initialized_data_or_bss"], "Late module geometry/CRC differs")
    require(pm["low_power"]["late_module"] == rm["low_power"]["late_module"] and
            pm["low_power"]["late_module"]["binary_sha256"] == digest(late) and
            pm["low_power"]["late_module"]["manifest_sha256"] ==
            digest((root/"build/late/manifest.json").read_bytes()), "Late manifest binding differs")
    header = (root / "build/receiver/late_config.h").read_text()
    config = {k: int(v, 0) for k, v in re.findall(
        r"^#define (LATE_[A-Z_0-9]+) (0x[0-9a-f]+|[0-9]+)U$", header, re.M)}
    require(config == dict(LATE_FLASH_OFFSET=0xE000, LATE_LOAD_ADDRESS=0x343C0000,
                           LATE_ENTRY_ADDRESS=0x343C0001, LATE_BYTES=len(late),
                           LATE_CRC32=zlib.crc32(late)), "Late compiled constants differ")
    reference = (root / "reference/v45b-stage1.bin").read_bytes()
    require(digest(reference) ==
            "a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a",
            "Recovery reference changed")
    require(p[:0xAFE] == reference[:0xAFE], "Early recovery code changed")
    h1, h2 = struct.unpack_from("<HH", p, 0xAFE)
    receiver_length = ((h1 & 15) << 12) | (((h1 >> 10) & 1) << 11) | \
                      (((h2 >> 12) & 7) << 8) | (h2 & 255)
    require(h1 & 0xFBF0 == 0xF240 and h2 & 0x8F00 == 0x0300 and
            receiver_length == len(r), "Receiver MOVW instruction differs")
    require(p[0x38C:0x38E] == bytes.fromhex("fee7"), "Recovery park changed")
    listing = (root / "build/prefix/stage1.lst").read_text()
    literals = set()
    for line in listing.splitlines():
        match = re.match(r"([0-9a-f]+):.*\[pc,.*@ \(([0-9a-f]+)", line)
        if match and 0x34180790 <= int(match[1], 16) <= 0x34180A76:
            offset = int(match[2], 16)-0x34180400
            require(0 <= offset <= len(p)-4 and
                    p[offset:offset+4] == reference[offset:offset+4],
                    "Early recovery literal changed")
            literals.add(offset)
    require(len(literals) >= 20, "Incomplete recovery literal review")
    require(plan["privacy"]["camera_images"] is False and
            plan["privacy"]["sd_contents"] is False and
            plan["privacy"]["other_raw_instrument_streams"] is False,
            "Unexpected private/raw payload policy")
    for name,recipe in plan.get("auxiliary_recipes",{}).items():
        require(name == "readback-bridge" and recipe["loaded_into_nor"] is False,
                "Unknown auxiliary payload")
        code=(root/recipe["binary"]).read_bytes()
        bm=json.loads((root/"build/readback-bridge/manifest.json").read_text())
        require(len(code) == bm["binary_bytes"] == 1324
                and digest(code) == bm["binary_sha256"] == recipe["binary_sha256"] ==
                "9d0a4553845dbf033264bde3629e2601aac561799cac9e34ed841f32485abdb6"
                and bm["load"] == 0x341E0000 and bm["entry"] == 0x341E0001
                and bm["park"] == 0x341E0016 and code[0x16:0x18] == b"\xfe\xe7",
                "RAM-only bridge identity/layout differs")
        require(all(not bm[key] for key in ("sd_commands","nor_commands","reset","power_switch")),
                "RAM bridge scope changed")
        for source,want in bm["source_hashes"].items():
            require(digest((root/"build/readback-bridge"/source).read_bytes()) == want,
                    "RAM bridge input differs")
        require((root/"build/readback-bridge/raw10_memory.c").read_bytes() ==
                (root/"build/prefix/raw10_memory.c").read_bytes(),
                "RAM bridge does not reuse the frozen initializer")
        require(all((root/source).is_file() for source in recipe["sources"])
                and (root/recipe["linker"]).is_file(), "RAM bridge recipe incomplete")
    if plan["qualification"].get("standby_entry"):
        programmed = json.loads((root/"results/v59-nor-write/verified.json").read_text())
        require(programmed["byte_for_byte_match"] and programmed["bytes"] == 65536
                and programmed["sha256"] == digest(sector), "Installed image differs")
        guard_sha = digest((root/"support/firmware/capture-timing/recovery_gpio/check_park.py").read_bytes())
        reader_sha = digest((root/"support/firmware/capture-sd/low_power/read_standby_flag.py").read_bytes())
        records = plan["qualification"]["evidence"]
        require(len(records) == plan["qualification"]["observed_trials"] >= 1,
                "Standby observation count differs")
        for record in records:
            park_bytes = (root/record["recovery"]).read_bytes()
            park = json.loads(park_bytes)
            flags = json.loads((root/record["standby_flag"]).read_text())
            require(park["passed"] and flags["passed"] and flags["sbf"]
                    and flags["cpucr"] & 512 and flags["pdds"],
                    "Missing hardware Standby flag")
            require(park["prefix_sha256"] == flags["prefix_sha256"] == digest(p),
                    "Measured recovery prefix differs")
            require(flags["guard_script_sha256"] == guard_sha
                    and flags["reader_script_sha256"] == reader_sha,
                    "Measured proof reader source differs")
            require(flags["prior_park_result_sha256"] == digest(park_bytes)
                    and flags["fresh_park_result"] == park
                    and flags["guard_before"] == flags["guard_after"],
                    "Recovery proof changed during flag read")
            require(not flags["cpucr_written"] and not flags["reset_or_power_changed"]
                    and not flags["ram_writes"] and not flags["nor_commands"]
                    and not flags["trial_entry_proven"],
                    "Historical flag scope changed")
            require(park["context"]["PC"] == 0x3418078C
                    and park["context"]["CONTROL"] == 0
                    and park["context"]["PRIMASK"] == 1
                    and park["ccr"] & ((1 << 16) | (1 << 17)) == 0
                    and park["vcp_status"]["request"] == 1
                    and park["vcp_status"]["source_bits"] == 2
                    and park["vcp_status"]["good_pulses"] >= 3
                    and park["vcp_status"]["bad_pulses"] == 0,
                    "Measured recovery gate differs")
    if plan["qualification"].get("readback_bridge_hardware_qualified"):
        rr=root/"results/standby-png-readback"
        read=json.loads((rr/"verified.json").read_text())
        bootstrap=json.loads((rr/"bootstrap/verified.json").read_text())
        bp=bootstrap["proof"]
        require(bp["magic"] == 0x52425231 and bp["nonce"] and bp["result"] == 0
                and bp["stage"] == 3 and bp["terminal"] == 0x5242444E
                and bp["memory_result"] == 0 and bp["ccr"] & 0x30000 == 0
                and bootstrap["bridge_sha256"] ==
                plan["auxiliary_recipes"]["readback-bridge"]["binary_sha256"]
                and bootstrap["early_recovery"]["prefix_sha256"] == digest(p),
                "Hardware RAM bridge proof differs")
        require(read["read_only"] and not read["nor_image_changed"]
                and not read["raw_frame_comparison"], "File readback scope differs")
        require({f["name"] for f in read["files"]} ==
                {"IMG00001.PNG","IMG00038.PNG","IMG00039.PNG",
                 "IMG00040.PNG","IMG00041.PNG","IMG00042.PNG"},
                "File readback set differs")
        for f in read["files"]:
            folder=rr/Path(f["name"]).stem
            require(json.loads((folder/"verified.json").read_text()) == f
                    and f["all_png_chunk_crcs_valid"] and f["complete_independent_decode"]
                    and f["all_samples_10bit_left_aligned"]
                    and not f["exact_capture_pixel_comparison"]
                    and f["pixels"] == 1527680 and f["readonly_card_writes"] == 0,
                    "File decode/integrity evidence differs")
            offset=0
            for number in range(f["read_chunks"]):
                chunk=json.loads((folder/f"chunk-{number:02d}/verified.json").read_text())
                q,c,fs,s = (chunk[k] for k in ("request","card","filesystem","report"))
                require(s["operation"] == q["operation"] == 3
                        and s["nonce"] == q["nonce"] and s["nonce"]
                        and q["name"] == f["name"] and q["offset"] == offset
                        and s["result"] == 0 and s["terminal"] == 0x444F4E45
                        and s["media_idle"] == c["media_idle"] == 1
                        and not any(c[k] for k in ("written_sectors","write_cycles","error",
                                                  "initialized","controller_owned"))
                        and not fs["fat_result"] and not fs["bytes_written"]
                        and chunk["context"]["registers"]["PC"] == 0x3432006E
                        and chunk["module_sha256"] == digest(m),
                        "READ chunk qualification differs")
                offset += s["read_bytes"]
            require(offset == f["bytes"], "READ chunk total differs")
        old=next(f for f in read["files"] if f["name"] == "IMG00001.PNG")
        require(old["known_file_hash_matched"] and old["sha256"] ==
                "466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330",
                "Previously saved file changed")
    if plan["qualification"].get("final_target_state"):
        final=json.loads((root/plan["qualification"]["final_target_state"]).read_text())
        require(final["sector_sha256"] == digest(sector) and final["js110"]["ok"]
                and final["js110"]["range"] == final["js110"]["starting_range"] == 128
                and final["js110"]["restore_error"] is None
                and final["uart_closed"] and final["break_released"]
                and final["no_active_storage_helper"]
                and not final["final_filename_readback_verified"],
                "Final bench release/scope differs")
    return dict(files=len(entries), bytes=total, identity=plan["build_identity"],
                early_recovery_literals=len(literals), qualification=plan["qualification"],
                hardware_accessed=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path(__file__).parent)
    print(json.dumps(verify(parser.parse_args().archive), indent=2))
