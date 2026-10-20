"""Read PWR Standby history only from a freshly verified early recovery park.

Requires exclusive bench ownership and an already selected recovery park. Never
resets, changes target power, runs RAM code, writes CPUCR, or clears reset/Standby
flags. If necessary, the sole register write enables the PWR bus clock through
RCC's write-one-set alias. The clock is left enabled and that change is recorded.

SBF=1 reports Standby since the last POR/CSSF clear, not its date or duration.
SBF=0 is inconclusive: it does not prove that the attempted Standby never happened.
Keep the pre-entry flag-clear proof and reset/power trace for trial attribution.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
RECOVERY = ROOT / "firmware/capture-timing/recovery_gpio"
sys.path.insert(0, str(RECOVERY))
import check_park

Bench = check_park.Bench
RCC_AHB4RSTR = 0x5602821C
RCC_AHB4ENR = 0x5602825C
RCC_AHB4ENSR = 0x56028A5C
PWR_CPUCR = 0x56024830
PWR_BIT = 1 << 18
SBF = 1 << 9
STOPF = 1 << 8
CCR = 0xE000ED14
FPCCR = 0xE000EF34


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def validate_park_result(result, code, approved):
    """Saved evidence is provenance; it never replaces the fresh live check."""
    if (result.get("passed") is not True
            or result.get("prefix_sha256") != sha(code)
            or result.get("park_context_observed_in_halt_command") is not True
            or result.get("ram_writes") is not False
            or result.get("nor_commands") is not False):
        raise ValueError("Missing or mismatched successful recovery-park evidence")
    status = check_park.validate_status(
        [result["status"][key] for key in check_park.FIELDS],
        vcp=approved.get("vcp", False))
    if approved.get("vcp", False):
        check_park.validate_vcp_status(
            [result["vcp_status"][key] for key in check_park.VCP_FIELDS], status)
    check_park.validate_context(result["context"], approved["park"],
                                result["ccr"], result["fpccr"])
    if result["xspi_sr"] & 0x7F20:
        raise ValueError("Saved recovery evidence has a non-idle XSPI controller")
    return result


def fresh_park_check(build, output):
    """Run the existing allowlisted guard sequentially, without any retry."""
    argv = [sys.executable, str(RECOVERY / "check_park.py"),
            "--build", str(build), "--out", str(output / "park-check")]
    (output / "park-check-request.json").write_text(
        json.dumps(dict(utc=utc(), argv=argv), indent=2) + "\n", encoding="utf-8")
    try:
        process = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        (output / "park-check.log").write_bytes(error.stdout or b"")
        raise RuntimeError("Fresh park check timed out; no reset or retry attempted") from error
    (output / "park-check.log").write_bytes(process.stdout)
    if process.returncode:
        raise RuntimeError("Fresh park check failed; no PWR register access authorized")
    path = output / "park-check/result.json"
    return json.loads(path.read_text(encoding="utf-8-sig")), sha(path.read_bytes())


def read_word(bench, address, name):
    return struct.unpack("<I", bench.upload(address, 4, name + ".bin"))[0]


def live_guard(bench, code, approved, fresh, name, include_code=False):
    status = check_park.validate_status(
        struct.unpack("<24I", bench.upload(check_park.STATUS_ADDRESS, 96,
                                          name + "-status.bin")),
        vcp=approved.get("vcp", False))
    if status != fresh["status"]:
        raise ValueError("Recovery record changed after the fresh park check")
    vcp = None
    if approved.get("vcp", False):
        vcp = check_park.validate_vcp_status(
            struct.unpack("<32I", bench.upload(check_park.VCP_ADDRESS, 128,
                                              name + "-vcp.bin")), status)
        if vcp != fresh["vcp_status"]:
            raise ValueError("VCP record changed after the fresh park check")
    if include_code and bench.upload(check_park.PREFIX_ADDRESS, len(code),
                                     name + "-prefix.bin") != code:
        raise ValueError("Live prefix differs; PWR register access refused")
    return dict(status=status, vcp_status=vcp)


def read_flag(bench, code, approved, fresh, result):
    """The only possible write is RCC_AHB4ENSR.PWRENS; never PWR_CPUCR."""
    result["stage"] = "recheck-live-park"
    result["guard_before"] = live_guard(
        bench, code, approved, fresh, "before", include_code=True)
    # A prior CLI disconnect may resume execution. Halt-dependent context is
    # sampled in one connection, only after matching exact live park code.
    context = check_park.registers(bench.call("-halt", "-coreReg"))
    ccr = read_word(bench, CCR, "ccr")
    fpccr = read_word(bench, FPCCR, "fpccr")
    check_park.validate_context(context, approved["park"], ccr, fpccr)
    result["context_rechecked"] = dict(context=context, ccr=ccr, fpccr=fpccr)
    result["stage"] = "rcc-preflight"
    reset = read_word(bench, RCC_AHB4RSTR, "ahb4rstr-before")
    enabled = read_word(bench, RCC_AHB4ENR, "ahb4enr-before")
    result["rcc_before"] = dict(ahb4rstr=reset, ahb4enr=enabled)
    if reset & PWR_BIT:
        raise ValueError("PWR is held in reset; no PWR read or reset release attempted")
    if not enabled & PWR_BIT:
        result["stage"] = "enable-pwr-bus-clock"
        # Record intent first: a failed CLI response cannot establish whether
        # the write reached the target. Do not retry or restore a guessed state.
        result["clock_enable_write_attempted"] = True
        bench.call("-w32", hex(RCC_AHB4ENSR), hex(PWR_BIT))
    result["stage"] = "rcc-readback"
    enabled_after = read_word(bench, RCC_AHB4ENR, "ahb4enr-after")
    reset_after = read_word(bench, RCC_AHB4RSTR, "ahb4rstr-after")
    result["rcc_after"] = dict(ahb4rstr=reset_after, ahb4enr=enabled_after)
    if not enabled_after & PWR_BIT or reset_after & PWR_BIT:
        raise ValueError("PWR clock/reset readback failed; CPUCR was not accessed")
    result["stage"] = "read-cpucr"
    cpucr = read_word(bench, PWR_CPUCR, "pwr-cpucr")
    result.update(cpucr=cpucr, sbf=bool(cpucr & SBF), stopf=bool(cpucr & STOPF),
                  pdds=bool(cpucr & 1), observation_utc=utc())
    result["interpretation"] = (
        "SBF is set: hardware reports Standby since the last POR or CSSF clear. "
        "Attribution to this trial requires its pre-entry flag-clear proof and "
        "reset/power history." if cpucr & SBF else
        "SBF is clear: inconclusive. This does not prove that Standby was never "
        "entered; a POR or flag-clear operation may have removed the evidence.")
    result["stage"] = "final-live-park-check"
    result["guard_after"] = live_guard(bench, code, approved, fresh, "after")
    result.update(passed=True, stage="complete", trial_entry_proven=False,
                  clock_left_enabled=True,
                  persistent_halt_after_disconnect="not_guaranteed",
                  post_disconnect_execution="may resume the verified branch-to-self park")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True,
                        help="Exact allowlisted staged recovery build")
    parser.add_argument("--park-result", type=Path, required=True,
                        help="Prior successful check_park result; checked again live")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    build, prior_path, output = (p.resolve() for p in
                                 (args.build, args.park_result, args.out))
    # All local failures precede any debugger client creation.
    code, approved = check_park.checked_build(build)
    prior_bytes = prior_path.read_bytes()
    prior = validate_park_result(
        json.loads(prior_bytes.decode("utf-8-sig")), code, approved)
    output.mkdir(parents=True, exist_ok=False)
    (output / "prior-park-result.json").write_bytes(prior_bytes)
    result = dict(
        passed=False, stage="fresh-park-check", began_utc=utc(),
        build=str(build), prefix_sha256=sha(code),
        prior_park_result_path=str(prior_path), prior_park_result_sha256=sha(prior_bytes),
        guard_script_sha256=sha((RECOVERY / "check_park.py").read_bytes()),
        reader_script_sha256=sha(Path(__file__).read_bytes()),
        clock_enable_write_attempted=False, cpucr_written=False,
        reset_or_power_changed=False, ram_writes=False, nor_commands=False,
        register_addresses={name: hex(address) for name, address in
                            (("rcc_ahb4rstr", RCC_AHB4RSTR),
                             ("rcc_ahb4enr", RCC_AHB4ENR),
                             ("rcc_ahb4ensr", RCC_AHB4ENSR),
                             ("pwr_cpucr", PWR_CPUCR))})
    try:
        fresh, fresh_sha = fresh_park_check(build, output)
        validate_park_result(fresh, code, approved)
        result.update(fresh_park_result_sha256=fresh_sha, fresh_park_result=fresh)
        # The caller's selected park must remain the same throughout this
        # operation. Requiring this also catches an intervening reset.
        if (fresh["status"] != prior["status"]
                or fresh.get("vcp_status") != prior.get("vcp_status")):
            raise ValueError("Fresh recovery evidence differs from the supplied park")
        read_flag(Bench(output / "registers"), code, approved, fresh, result)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["ended_utc"] = utc()
        (output / "result.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
