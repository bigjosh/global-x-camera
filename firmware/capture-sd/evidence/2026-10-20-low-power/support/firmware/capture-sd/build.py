"""Build capture/storage variants from the frozen v45b sources; no hardware."""
import argparse
import copy
import json
from pathlib import Path
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "capture-timing"))
from build_raw10 import (ROOT, VENDOR, checked_manifest, compile_sources, make_image,
                        inspect_image, sha, write_manifest, replace)

BASE_SECTOR = "2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2"
BASE_PREFIX = "a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a"
BASE_RECEIVER = "478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac"
MODULE_OFFSET = 0x6000
LATE_OFFSET = 0xE000
LATE_ADDRESS = 0x343C0000
LATE_MAX_BYTES = 0x2000
STAGE2_LENGTH_INSTRUCTION_OFFSET = 0xAFE


def symbol(folder, name):
    text = (folder / "symbols.txt").read_text(encoding="utf-8")
    match = re.search(r"^([0-9a-fA-F]+) [Tt] " + re.escape(name) + r"$", text, re.M)
    if not match:
        raise ValueError("Missing symbol " + name)
    return int(match[1], 16)


def decode_stage2_length(prefix):
    # T32 MOVW r3,#imm16 at 0x34180EFE follows the recovery branch and SRAM
    # expansion. The former 0xB00 cutoff bisected this four-byte instruction:
    # crossing 16 KiB changes its first halfword as well as its second.
    h1, h2 = struct.unpack_from("<HH", prefix, STAGE2_LENGTH_INSTRUCTION_OFFSET)
    assert h1 & 0xFBF0 == 0xF240 and h2 & 0x8F00 == 0x0300, "Expected MOVW r3,#imm16"
    return ((h1 & 15) << 12) | (((h1 >> 10) & 1) << 11) | \
           (((h2 >> 12) & 7) << 8) | (h2 & 255)


def check_recovery_identity(folder, prefix, original, stage2_bytes):
    # Prove every byte before the complete first variable instruction, its
    # opcode/register/immediate, and all out-of-line literals used by the guard.
    limit=STAGE2_LENGTH_INSTRUCTION_OFFSET
    assert prefix[:limit]==original[:limit]
    assert decode_stage2_length(prefix)==stage2_bytes
    listing=(folder/"stage1.lst").read_text()
    assert re.search(r"34180a76:.*\bbl\s+3418078c <recovery_gpio_park>",listing)
    literals=set()
    for line in listing.splitlines():
        m=re.match(r"([0-9a-f]+):.*\[pc,.*@ \(([0-9a-f]+)",line)
        if m and 0x34180790<=int(m[1],16)<=0x34180A76:
            offset=int(m[2],16)-0x34180400
            assert 0<=offset<=len(prefix)-4
            assert prefix[offset:offset+4]==original[offset:offset+4]
            literals.add(offset)
    assert len(literals)>=10
    return sorted(literals)


def completion_metadata(manifest, awake, module_enabled):
    """Replace inherited LED/sleep descriptions with this variant's behavior."""
    manifest["completion_policy"] = (
        "awake diagnostic park" if awake else "CPU WFI; not regulator-off")
    led = manifest["status_leds"]
    led["green_start"] = (
        "save loader after complete-frame validation and sensor STOP; SD write phase"
        if module_enabled else "reserved helper; no storage write caller")
    led["completion"] = (
        "all off; " + ("awake NOP/branch park" if awake else "ordinary CPU WFI") +
        (" after successful SD save, sync, card-ready check and module return"
         if module_enabled else " after complete-frame validation and sensor STOP"))
    led["sleep"] = (
        "not entered; awake diagnostic completion, no regulator or rail shutdown"
        if awake else
        "CPU-only ordinary sleep; no deep sleep, regulator hold release or rail shutdown")
    led["sleep_state"] = 2 if awake else 1


def pack_sector(original, boot, receiver, module=None, late=None):
    """Validate disjoint flash regions before constructing the one-sector image."""
    assert len(original) == 65536 and 0 < len(boot) <= 0x2000
    assert 0 < len(receiver) <= MODULE_OFFSET - 0x2000
    if module is not None:
        limit = LATE_OFFSET if late is not None else 65536
        assert 0 < len(module) <= limit - MODULE_OFFSET and len(module) % 4 == 0
    if late is not None:
        assert module is not None and 0 < len(late) <= LATE_MAX_BYTES
        assert len(late) % 4 == 0
    sector = bytearray(original)
    sector[:len(boot)] = boot
    sector[0x2000:MODULE_OFFSET] = b"\xff" * (MODULE_OFFSET - 0x2000)
    sector[0x2000:0x2000 + len(receiver)] = receiver
    if module is not None:
        sector[MODULE_OFFSET:] = b"\xff" * (65536 - MODULE_OFFSET)
        sector[MODULE_OFFSET:MODULE_OFFSET + len(module)] = module
    if late is not None:
        sector[LATE_OFFSET:LATE_OFFSET + len(late)] = late
    assert len(sector) == 65536
    return sector


def build_late(out, rdir, mode, delay_us):
    """Build stateless completion code, loaded after SAVE into unused high SRAM."""
    ldir = out / "late"
    ldir.mkdir()
    sources = []
    for name in ("completion.c", "completion.h", "peripherals.c", "peripherals.h",
                 "late_entry.S", "late.ld"):
        dst = ldir / name
        dst.write_bytes((HERE / "low_power" / name).read_bytes())
        sources.append(dst)
    for name in ("status_leds.h", "save_protocol.h", "photo_fs.h",
                 "sd_card.h", "save_module_config.h"):
        dst = ldir / name
        dst.write_bytes((rdir / name).read_bytes())
        sources.append(dst)
    drivers = VENDOR / "STM32Cube_FW_N6/Drivers"
    flags = ["-mcpu=cortex-m55", "-mthumb", "-mcmse", "-mfpu=fpv5-d16",
             "-mfloat-abi=hard", "-Os", "-g3", "-ffunction-sections",
             "-fdata-sections", "-fno-builtin", "-ffreestanding", "-flto",
             "-mno-unaligned-access", "-DSTM32N657xx", "-Wall", "-Wextra", "-Werror",
             f"-I{ldir}", f"-I{drivers / 'CMSIS/Include'}",
             f"-I{drivers / 'CMSIS/Device/ST/STM32N6xx/Include'}",
             f"-DLOW_POWER_MODE={('peripherals-off','sleep','stop','standby').index(mode)}",
             f"-DLOW_POWER_ENTRY_DELAY_US={delay_us}U"]
    raw, size = compile_sources(ldir, [s for s in sources if s.suffix in (".c", ".S")],
                                flags, ldir / "late.ld", "late")
    assert 0 < len(raw) <= LATE_MAX_BYTES and len(raw) % 4 == 0
    size_row = re.search(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+\s", size, re.M)
    assert size_row and int(size_row[2]) == 0 and int(size_row[3]) == 0
    sections = dict(text=int(size_row[1]), data=0, bss=0)
    assert symbol(ldir, "late_completion_entry") == LATE_ADDRESS
    metadata = dict(flash_offset=LATE_OFFSET, load_address=hex(LATE_ADDRESS),
                    entry_address=hex(LATE_ADDRESS | 1), binary_bytes=len(raw),
                    binary_sha256=sha(raw), crc32=hex(zlib.crc32(raw)),
                    loader_proof_address="0x343f9b00",
                    sleep_idle_address=hex(symbol(ldir, "status_led_sleep_idle")),
                    failure_park_address=hex(symbol(ldir, "low_power_failure_idle")),
                    no_initialized_data_or_bss=True, section_sizes=sections)
    if mode != "peripherals-off":
        metadata["return_park_address"] = hex(symbol(ldir, "low_power_return_idle"))
    manifest = dict(schema=1, hardware_status="untested", mode=mode,
                    entry_delay_us=delay_us, binary_file="late.bin", size=size,
                    compile_flags=flags, **metadata)
    write_manifest(ldir, manifest, sources)
    metadata.update(manifest_path=str(ldir / "manifest.json"),
                    manifest_sha256=sha((ldir / "manifest.json").read_bytes()))
    header = rdir / "late_config.h"
    header.write_text(
        f"#define LATE_FLASH_OFFSET {LATE_OFFSET}U\n"
        f"#define LATE_LOAD_ADDRESS 0x{LATE_ADDRESS:08x}U\n"
        f"#define LATE_ENTRY_ADDRESS 0x{LATE_ADDRESS | 1:08x}U\n"
        f"#define LATE_BYTES {len(raw)}U\n"
        f"#define LATE_CRC32 0x{zlib.crc32(raw):08x}U\n", encoding="utf-8")
    return raw, metadata, header


def capture_save_handoff(text, completion_enabled):
    late_ownership = (
        "  ((volatile uint32_t *)0x343F9B00U)[0]=0x4C504C31U;\n"
        if completion_enabled else "")
    return replace(text, "  event(40);\n  status_led_complete_sleep();",
                   "  extern int photo_save_load(void);\n"
                   "  /* Publish ownership before legacy capture-complete. */\n" +
                   late_ownership +
                   "  ((volatile uint32_t *)0x343F9E00U)[11]=0U;\n"
                   "  ((volatile uint32_t *)0x343F9E00U)[0]=0x534C4431U;\n"
                   "  __DMB();\n  event(40);\n"
                   "  int save_result=photo_save_load();\n"
                   "  if(save_result) fail(0xB0,save_result);\n"
                   "  status_led_complete_sleep();")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--awake", action="store_true", help="Diagnostic completion without WFI")
    p.add_argument("--completion", choices=("peripherals-off", "sleep", "stop", "standby"),
                   help="Experimental post-save peripheral shutdown and selected MCU state")
    p.add_argument("--entry-delay-us", type=int, default=0,
                   help="Qualification-only delay before low-power entry, 0..1000000")
    p.add_argument("--module", type=Path)
    a = p.parse_args()
    if a.completion and (a.awake or not a.module):
        p.error("--completion requires --module and cannot be combined with --awake")
    if not 0 <= a.entry_delay_us <= 1000000 or (a.entry_delay_us and not a.completion):
        p.error("--entry-delay-us requires --completion and must be 0..1000000")
    # Bulk completion code is loaded after SAVE; it must not inflate the
    # pre-capture receiver transfer and consume the first-frame timing margin.
    module_offset = MODULE_OFFSET
    base, out = a.base.resolve(), a.out.resolve()
    rm, pm = [checked_manifest(base / sub) for sub in ("receiver", "staged")]
    original = (base / "staged/capture_sector_0.bin").read_bytes()
    old_prefix = (base / "staged/stage1.bin").read_bytes()
    assert sha(original) == BASE_SECTOR and sha(old_prefix) == BASE_PREFIX
    assert sha((base / "receiver/capture.bin").read_bytes()) == BASE_RECEIVER
    out.mkdir(parents=True, exist_ok=False)
    rdir, pdir = out / "receiver", out / "staged"
    rdir.mkdir(); pdir.mkdir()
    sources = []
    for path in rm["sources"]:
        src = ROOT / path
        dst = rdir / src.name
        raw = src.read_bytes()
        if src.name == "sleep.c" and a.completion:
            raw = (HERE / "low_power/late_loader.c").read_bytes()
        elif src.name == "sleep.c" and a.awake:
            text = raw.decode("utf-8")
            text = replace(text, '"wfi\\n"', '"nop\\n"')
            text = replace(text, "STATUS_LED_PROOF[LED_P_SLEEP_STATE] = 1U;",
                           "STATUS_LED_PROOF[LED_P_SLEEP_STATE] = 2U;")
            text = replace(text, "/* Prepared; CPU context proves WFI. */",
                           "/* Prepared for the awake diagnostic completion park. */")
            raw = text.encode()
        if src.name == "capture.c" and a.module:
            raw = capture_save_handoff(raw.decode("utf-8"), bool(a.completion)).encode()
        dst.write_bytes(raw); sources.append(dst)
    if a.completion:
        for name in ("save_protocol.h", "photo_fs.h", "sd_card.h"):
            dst = rdir / name
            dst.write_bytes((a.module / name).read_bytes())
            sources.append(dst)
    module = None
    md = None
    if a.module:
        md = json.loads((a.module / "manifest.json").read_text())
        for path, expected in md["sources"].items():
            assert sha((ROOT / path).read_bytes()) == expected, path
        module = (a.module / "save.bin").read_bytes()
        assert sha(module) == md["binary_sha256"]
        assert len(module) == md["binary_bytes"] and len(module)%4==0
        assert 0 < len(module) <= 65536 - module_offset
        assert int(md["load_address"],0)==0x34320000
        assert int(md["entry_address"],0)==0x34320001
        assert 0x34320000+len(module)<=int(md["bss_start"],0)<=int(md["bss_end"],0)<=0x343A0000
        assert int(md["stack_floor"],0)==0x343A0000 and int(md["stack_top"],0)==0x343B0000
        assert md["default_mode"] in (0,1,2)
        for name in ("manifest.json","save.bin"):
            target=rdir/("module-"+name)
            target.write_bytes((a.module/name).read_bytes())
            sources.append(target)
        for name in ("save_loader.c",):
            dst = rdir / name
            dst.write_bytes((HERE / name).read_bytes()); sources.append(dst)
        header = rdir / "save_module_config.h"
        header.write_text(
            f"#define SAVE_FLASH_OFFSET {module_offset}U\n"
            f"#define SAVE_LOAD_ADDRESS 0x34320000U\n"
            f"#define SAVE_BYTES {len(module)}U\n"
            f"#define SAVE_CRC32 0x{zlib.crc32(module):08x}U\n"
            f"#define SAVE_DEFAULT_MODE {md['default_mode']}U\n", encoding="utf-8")
        sources.append(header)
    late = None
    late_metadata = None
    if a.completion:
        late, late_metadata, late_header = build_late(
            out, rdir, a.completion, a.entry_delay_us)
        sources.append(late_header)
        assert len(module) <= LATE_OFFSET - module_offset
    flags = list(rm["compile_flags"]) + [f"-I{rdir}"]
    raw, size = compile_sources(rdir, [s for s in sources if s.suffix in (".c", ".s", ".S")],
                                flags, rdir / "capture.ld", "capture", libc=True)
    assert len(raw) + 0x2000 <= module_offset
    sp, entry = struct.unpack_from("<II", raw)
    assert sp == 0x343B0000 and 0x34300000 <= entry - 1 < 0x34300000 + len(raw)
    manifest = copy.deepcopy(rm)
    receiver_unchanged = sha(raw) == BASE_RECEIVER
    capture_sd = dict(
        enabled=bool(module), awake_completion=a.awake,
        module_offset=module_offset if module else None,
        module_bytes=len(module) if module else 0,
        module_sha256=sha(module) if module else None,
        module_data_cache_enabled=bool(md and md.get("data_cache_enabled", False)),
        module_load_phase="after completed capture and sensor STOP" if module else None)
    manifest.update(raw_bytes=len(raw), raw_sha256=sha(raw), size=size, entry_point=hex(entry),
                    hardware_status="untested", compile_flags=flags,
                    failure_park_address=hex(symbol(rdir, "fast_failure_idle")),
                    sleep_idle_address=(late_metadata["sleep_idle_address"] if a.completion
                                        else hex(symbol(rdir, "status_led_sleep_idle"))),
                    capture_source_path=str(rdir / "capture.c"),
                    base_receiver_sha256=BASE_RECEIVER,
                    base_receiver_manifest_sha256=sha((base / "receiver/manifest.json").read_bytes()),
                    receiver_byte_identical_to_v45b=receiver_unchanged,
                    capture_sd=copy.deepcopy(capture_sd))
    manifest["parameters"]["first_frame_qualification"] = (
        "pending hardware qualification of this exact capture/storage variant")
    manifest.setdefault("generator_inputs", {})[str(HERE.relative_to(ROOT) / "build.py")] = sha(
        Path(__file__).read_bytes())
    completion_metadata(manifest, a.awake, bool(module))
    if a.completion:
        manifest["completion_policy"] = a.completion + "; experimental, not hardware qualified"
        manifest["low_power"] = dict(mode=a.completion, proof_address="0x343f9c00",
                                    proof_max_bytes=512, recovery_requires_reset=True,
                                    entry_delay_us=a.entry_delay_us,
                                    sram_lost=a.completion == "standby",
                                    late_module=copy.deepcopy(late_metadata),
                                    loader_failure_park_address=hex(symbol(
                                        rdir, "late_completion_failure_idle")))
        manifest["status_leds"].update(
            completion=f"all off after successful SD save; {a.completion}",
            sleep=f"experimental {a.completion}; see low_power proof and qualification",
            sleep_state=None)
    receiver_led_metadata = copy.deepcopy(manifest["status_leds"])
    write_manifest(rdir, manifest, sources)
    psources = []
    for path in pm["sources"]:
        src = ROOT / path; dst = pdir / src.name
        dst.write_bytes(src.read_bytes()); psources.append(dst)
    pflags = [f for f in pm["compile_flags"]
              if not f.startswith(("-DSTAGE2_BYTES=", "-DSTAGE2_EXPECTED_CRC32="))]
    pflags += [f"-DSTAGE2_BYTES={len(raw)}U",
               f"-DSTAGE2_EXPECTED_CRC32=0x{zlib.crc32(raw):08x}U", f"-I{pdir}"]
    prefix, size = compile_sources(pdir, [s for s in psources if s.suffix in (".c", ".S")],
                                   pflags, pdir / "stage1.ld", "stage1")
    park = symbol(pdir, "recovery_gpio_park")
    # Entire early guard, including its literals and completion park, is frozen.
    first_difference = next((i for i, (x, y) in enumerate(zip(prefix, old_prefix))
                             if x != y), min(len(prefix), len(old_prefix)))
    assert park == 0x3418078C and first_difference >= STAGE2_LENGTH_INSTRUCTION_OFFSET
    recovery_literals=check_recovery_identity(pdir,prefix,old_prefix,len(raw))
    boot = make_image(prefix)
    assert len(boot) <= 0x2000
    sector = pack_sector(original, boot, raw, module, late)
    (pdir / "stage1_boot.bin").write_bytes(boot)
    (pdir / "stage2.bin").write_bytes(raw)
    (pdir / "capture_sector_0.bin").write_bytes(sector)
    manifest = copy.deepcopy(pm)
    manifest.update(hardware_status="untested", stage1=inspect_image(boot), size=size,
                    stage1_raw_bytes=len(prefix), stage1_raw_sha256=sha(prefix),
                    stage2_bytes=len(raw), stage2_sha256=sha(raw),
                    stage2_crc32=hex(zlib.crc32(raw)), compile_flags=pflags,
                    stage2_build_manifest=str(rdir / "manifest.json"),
                    stage2_manifest_sha256=sha((rdir / "manifest.json").read_bytes()),
                    program_sha256=sha(sector),
                    receiver_byte_identical_to_v44=receiver_unchanged,
                    receiver_byte_identical_to_v45b=receiver_unchanged,
                    base_receiver_sha256=BASE_RECEIVER,
                    # Legacy completion_metadata below mutates this mapping.
                    # Keep the receiver's new-mode description independent.
                    status_leds=copy.deepcopy(receiver_led_metadata),
                    capture_sd=dict(capture_sd,
                                    unchanged_prefix_leading_bytes=first_difference,
                                    checked_recovery_literal_offsets=recovery_literals))
    completion_metadata(manifest, a.awake, bool(module))
    if a.completion:
        manifest["completion_policy"] = a.completion + "; experimental, not hardware qualified"
        manifest["low_power"] = dict(mode=a.completion, proof_address="0x343f9c00",
                                    proof_max_bytes=512, recovery_requires_reset=True,
                                    entry_delay_us=a.entry_delay_us,
                                    sram_lost=a.completion == "standby",
                                    late_module=copy.deepcopy(late_metadata),
                                    loader_failure_park_address=hex(symbol(
                                        rdir, "late_completion_failure_idle")))
        manifest["status_leds"] = copy.deepcopy(receiver_led_metadata)
    manifest["recovery_gpio"].update(
        receiver_unchanged=receiver_unchanged,
        receiver_comparison="exact v45b receiver binary",
        clock_qualification=(
            "Unchanged v45b 40000-cycle observation deadline at nominal 400 MHz; "
            "not a total boot-latency or all-state recovery guarantee"),
        external_drive=(
            "PE1 diode interface remains supported; no connected external drive assumed. "
            "Current bench recovery uses ST-LINK VCP on PE6."),
        source_compatibility=(
            "Early PE1/PE6 guard, park and referenced literals match v45b; "
            "later receiver length/CRC constants can change"))
    manifest["recovery_vcp"].update(
        pattern=(
            "Three complete bounded LOW pulses separated by bounded HIGH intervals; "
            "pulse detector, not UART byte decoding"),
        recommended_request_byte="0xc0",
        reference_waveforms=(
            "1 Mbaud 8N1: 0xC0 gives nominal 7 us LOW/3 us HIGH; "
            "0x00 gives 9 us LOW/1 us HIGH with less sampling margin"),
        qualification=(
            "Early guard matches v45b, which reached verified cold/warm recovery parks; "
            "later warm requests also failed. This exact integrated image is untested."))
    manifest.setdefault("generator_inputs", {})[str(HERE.relative_to(ROOT) / "build.py")] = sha(
        Path(__file__).read_bytes())
    write_manifest(pdir, manifest, psources)
    print(json.dumps(dict(out=str(out), receiver_bytes=len(raw), prefix_sha256=sha(prefix),
                          sector_sha256=sha(sector), unchanged_prefix_bytes=first_difference)))


if __name__ == "__main__":
    main()
