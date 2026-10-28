"""Guarded, read-only SD smoke execution; root bench owner only.

Default is offline plan validation. --execute performs bounded SWD RAM access.
Never resets, switches power, sends a NOR command or writes any SD sector.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "firmware/boot-timing"))
from nor_bench import Bench

FIELDS = """magic schema words result stage old_msp old_msplim control ipsr cpu_ccr
cfgr1 cfgr2 pll1cfgr1 pll1cfgr2 pll1cfgr3 ic1cfgr ic2cfgr divenr ahb4enr ahb5enr
ahb5rstr ccipr8 pwr_svmcr2_before pwr_svmcr2_after gpioc_moder_before gpioc_idr_before
gpioe_moder_before gpioe_idr_before gpioc_idr_settled gpioe_idr_settled gpioc_moder_af
gpioc_afr0 gpioc_pupdr gpioe_moder_input gpioe_pupdr dwt_begin dwt_end request_max_hz
kernel_hz current_sd_hz clkcr last_command last_argument last_sta last_respcmd
last_r1 command_count records_used records_dropped ocr rca cid0 cid1 cid2 cid3
csd0 csd1 csd2 csd3 csd_version sector_count_low sector_count_high read_count
read_words read_cycles read_sta read_crc0 read_crc1 read_crc2 read_crc3 read_crc4
read_crc5 read_match_mask card_status fail_stage fail_command fail_sta cleanup""".split()
APPROVED_SHA = "790b240b4246d61daf6361da67cb2bca6084d666897902e0bfd1dc9555c03db6"
LOAD, ENTRY, PARK = 0x341E0000, 0x341E0001, 0x341E05E4
STATUS, REQUEST, RECORDS, DATA = 0x341B4100, 0x341B4000, 0x341B4400, 0x341C0000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_build(build):
    manifest = json.loads((build / "manifest.json").read_text())
    binary = (build / "sd-smoke.bin").read_bytes()
    if sha(binary) != APPROVED_SHA or manifest.get("binary_sha256") != APPROVED_SHA:
        raise ValueError("SD helper is not the independently reviewed executable")
    expected = {
        "load": "0x341E0000", "thumb_entry": "0x341E0001", "park": "0x341e05e4",
        "park_bytes": "fee7", "stack_top": "0x341B8000", "request": "0x341B4000",
        "status": "0x341B4100", "status_words": 78, "status_fields": FIELDS,
        "records": "0x341B4400", "record_count": 64, "record_words": 12,
        "sector_buffers": "0x341C0000", "sector_buffer_count": 6, "sector_bytes": 512,
        "command_whitelist": [0, 2, 3, 7, 8, 9, 13, 16, 17, 41, 55],
        "writes_card": False, "writes_nor": False, "executes_from_ram": True,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("SD helper layout/policy differs from reviewed host runner")
    if len(binary) != 3120 or binary[PARK-LOAD:PARK-LOAD+2] != bytes.fromhex("fee7"):
        raise ValueError("SD helper length or park instruction differs")
    return manifest, binary


def context_from_text(text):
    import re
    return {key: int(value, 16) for key, value in re.findall(
        r"^(PC|XPSR|CONTROL|PRIMASK|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)", text, re.M)}


def checked_terminal(raw, max_hz):
    if len(raw) != 312:
        raise ValueError("Incomplete SD result")
    status = dict(zip(FIELDS, struct.unpack("<78I", raw)))
    if (status["magic"] != 0x53445231 or status["schema"] != 1 or
            status["words"] != 78 or status["request_max_hz"] != max_hz):
        return None
    if status["result"] == 0x52554E4E or status["stage"] != 9:
        return None
    if not 0 <= status["result"] <= 23:
        raise ValueError("Unrecognized SD terminal result")
    return status


def execute(args, manifest, binary):
    # Raw sector bytes may contain user data; force all runtime evidence under
    # the repository's ignored tmp tree, never into public tracked evidence.
    output = args.out.resolve()
    output.relative_to((REPO / "tmp").resolve())
    bench = Bench(output)
    guard = REPO / "firmware/capture-timing/recovery_gpio/check_park.py"
    guard_args = [
        sys.executable, str(guard), "--build", str(args.recovery_build.resolve()),
        "--out", str(output / "early-park-guard"),
    ]
    (output / "request.json").write_text(json.dumps({
        "recovery_build": str(args.recovery_build.resolve()),
        "helper_build": str(args.build.resolve()), "helper_sha256": sha(binary),
        "max_hz": args.max_hz, "sector_lbas": [0, 1],
        "writes_sd": False, "writes_nor": False, "resets_or_power_changes": False,
    }, indent=2) + "\n")
    # This guard observes exact live prefix, selected recovery status, CPU
    # context, both caches disabled, and idle clocked XSPI. It leaves only an
    # exact branch-to-self park; disconnect may resume that safe instruction.
    process = subprocess.run(
        guard_args, capture_output=True, timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    (output / "early-park-guard.log").write_bytes(process.stdout + process.stderr)
    if process.returncode:
        raise RuntimeError("Fresh early-recovery guard failed; no SD helper RAM download performed")
    guard_result = json.loads((output / "early-park-guard/result.json").read_text())
    if guard_result.get("passed") is not True or guard_result.get("ccr", 0x30000) & 0x30000:
        raise ValueError("Fresh guard did not establish an uncached early park")
    print("Early recovery park verified; loading read-only SD RAM helper.", flush=True)

    bench.call("-halt", "-w", (args.build / "sd-smoke.bin").resolve(), hex(LOAD), "-v",
               success="Download verified successfully")
    if bench.upload(LOAD, len(binary), "helper-readback.bin") != binary:
        raise ValueError("Complete RAM helper readback differs; helper not executed")
    request = struct.pack("<4I", 0x53445244, args.max_hz, 0, 0)
    request_path, clear_path = output / "command.bin", output / "clear-status.bin"
    request_path.write_bytes(request)
    clear_path.write_bytes(bytes(312))
    bench.call("-halt", "-w", clear_path, hex(STATUS), "-v",
               "-w", request_path, hex(REQUEST), "-v",
               success="Download verified successfully")
    if bench.upload(STATUS, 312, "cleared-status-readback.bin") != bytes(312):
        raise ValueError("Result buffer was not cleared; refusing stale evidence")
    if bench.upload(REQUEST, 16, "request-readback.bin") != request:
        raise ValueError("SD request readback differs")
    bench.call("-halt", "-coreReg", f"PC={hex(ENTRY)}", "XPSR=0x01000000",
               "-run", success="Core run")
    deadline = time.monotonic() + 60
    status = None
    for i in range(30):
        raw = bench.upload(STATUS, 312, f"status-{i:02d}.bin")
        status = checked_terminal(raw, args.max_hz)
        if status is not None:
            (output / "status.bin").write_bytes(raw)
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("No fresh SD terminal record; target left untouched for diagnosis")
        time.sleep(0.1)
    if status is None:
        raise TimeoutError("No fresh SD terminal record; target left untouched for diagnosis")
    # Terminal RAM evidence permits a halt only now. Verify PC in that same
    # connection; a separate earlier halt cannot establish a lasting halt.
    context = context_from_text(bench.call("-halt", "-coreReg"))
    if (context.get("PC") != PARK or context.get("CONTROL") != 0 or
            context.get("PRIMASK") != 1 or context.get("FAULTMASK") != 0 or
            context.get("XPSR", 511) & 511 or
            not context.get("XPSR", 0) & 0x01000000):
        raise ValueError("SD terminal status exists but exact awake final park was not observed")
    if bench.upload(PARK, 2, "park-readback.bin") != bytes.fromhex("fee7"):
        raise ValueError("SD final park instruction differs")
    def word(address, name):
        return struct.unpack("<I", bench.upload(address, 4, name + ".bin"))[0]
    enabled = word(0x56028260, "final-ahb5enr")
    reset = word(0x56028220, "final-ahb5rstr")
    if enabled & 0x2020 != 0x2020 or reset & 0x2020:
        raise ValueError("XSPI clocks/reset no longer match safe idle-read precondition")
    xspi_sr = word(0x58025020, "final-xspi-sr")
    if xspi_sr & 0x7F20:
        raise ValueError("XSPI controller is not idle after read-only SD helper")
    if status["cleanup"] & 1 and enabled & (1 << 7):
        raise ValueError("SD helper claims cleanup but SDMMC2 bus clock remains enabled")
    bench.upload(RECORDS, 64*48, "records.bin")
    bench.upload(DATA, 6*512, "data.bin")
    inspector = subprocess.run([
        sys.executable, str(HERE / "inspect.py"), "--build", str(args.build.resolve()),
        "--status", str(output / "status.bin"), "--records", str(output / "records.bin"),
        "--data", str(output / "data.bin"),
    ], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)
    (output / "inspection.log").write_bytes(inspector.stdout + inspector.stderr)
    if inspector.returncode:
        raise RuntimeError("Host SD data inspection failed; inspect saved local evidence")
    report = json.loads(inspector.stdout)
    report["park_verification"] = {
        "context": context, "instruction": "fee7", "xspi_sr": xspi_sr,
        "ahb5enr": enabled, "ahb5rstr": reset,
        "persistent_halt_after_disconnect": "not guaranteed; resumes safe exact park",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = {
        "read_smoke_pass": report["read_smoke_pass"], "result": status["result"],
        "fail_stage": status["fail_stage"], "fail_command": status["fail_command"],
        "max_hz": args.max_hz, "reads_completed": status["read_count"],
        "cid": report["cid"], "capacity_decimal_gb": report["capacity_decimal_gb"],
        "report": str(output / "report.json"), "data_published": False,
    }
    print(json.dumps(summary, indent=2))
    if not report["read_smoke_pass"]:
        raise RuntimeError("SD smoke check failed; target remains in diagnostic park, no reset/retry performed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--recovery-build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-hz", type=int, choices=(100000, 12500000, 25000000),
                        default=100000)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    manifest, binary = checked_build(args.build)
    if not args.execute:
        print(json.dumps({
            "offline_only": True, "reviewed_helper_sha256": sha(binary),
            "entry": hex(ENTRY), "park": hex(PARK), "request_max_hz": args.max_hz,
            "next": "Only the current bench owner may add --execute after confirming ownership and rails.",
        }, indent=2))
        return
    execute(args, manifest, binary)


if __name__ == "__main__":
    main()
