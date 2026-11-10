"""Offline by default; root-owned, bounded read-only PHY diagnosis with --execute.

This reuses the unchanged reviewed SRAM bridge and corrected MDIO v2 binary.
The bridge enables expanded SRAM before any high-SRAM access. The PHY helper
temporarily owns only PF4/PG11 and restores them and added GPIO clocks. No PHY
write frame, camera/SD/NOR command, reset, target power change or sleep occurs.
The bridge leaves expanded SRAM enabled; this is not an undisturbed power sample.
Final execution remains at the MDIO branch-to-self, with its own stack.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MDIO_DIR = ROOT / "tmp/bringup/nucleo-isolated-20261028/mdio/v2"
spec = importlib.util.spec_from_file_location("current_campaign_mdio_v2", MDIO_DIR / "run.py")
mdio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdio)
bridge = mdio.isolated.raw.bridge
RECOVERY = ROOT / "tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged"
BRIDGE = ROOT / "tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1"
PREFIX = "6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874"


def checked():
    identity = bridge.checked_recovery(RECOVERY)
    if identity["prefix_sha256"] != PREFIX:
        raise ValueError("Requires exact installed October28 single-frame recovery")
    bm, bc = bridge.checked_bridge(BRIDGE)
    dm, dc = mdio.checked_probe()
    # Firmware, proof and stack are disjoint; all high regions are touched only
    # after bridge completion, live memory gates and exact terminal context.
    if not (dm["load"] == 0x343C4000 and dm["load"] + len(dc) < 0x343C6000
            and dm["proof"] == 0x343C6000 and dm["proof"] + 2048 <= 0x343C6800
            and bm["park"] == 0x341E0016):
        raise ValueError("Unexpected layout")
    plan = dict(
        recovery=identity, bridge=bm, diagnostic=dm,
        diagnostic_source_directory=str(MDIO_DIR),
        host_sha256=mdio.sha(Path(__file__).read_bytes()),
        phy_register_coverage="IDs reg2/reg3 at all32 addresses; BMCR reg0 twice at each matching LAN8742",
        omitted_registers=[1, 17, 18, 31],
        no_phy_write_frames=True, no_camera_sd_nor_commands=True,
        no_reset_or_power_switch=True,
        changes="Temporary RAM code/stack, expanded SRAM clocks/init, and restored PF4/PG11 GPIO ownership",
        final_park=hex(dm["park"]), final_stack="0x343AF000..0x343B0000",
        final_limit="No return to old caller stack or automatic reset/recovery; root performs separate fresh recovery",
    )
    return plan, bc, dc


def save(out, name, value):
    (out / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare(output):
    """Root-only: current exact early park -> unchanged SRAM bridge -> helper load."""
    plan, boot_code, code = checked()
    out = Path(output).resolve()
    if HERE not in out.parents:
        raise ValueError("Output must be a fresh campaign child directory")
    out.mkdir(parents=True, exist_ok=False)
    save(out, "plan.json", plan)
    b = bridge.bootstrap(SimpleNamespace(recovery_build=RECOVERY, bridge=BRIDGE), out, boot_code)
    prior = json.loads((b.output / "verified.json").read_text())
    if prior["bridge_sha256"] != bridge.BOOT_SHA or prior["recovery_identity"]["prefix_sha256"] != PREFIX:
        raise ValueError("Bridge provenance differs")
    # Crucially, no high address is touched before these RCC checks.
    memenr, = struct.unpack("<I", b.upload(0x5602824C, 4, "mdio-memenr.bin"))
    memrstr, = struct.unpack("<I", b.upload(0x5602820C, 4, "mdio-memrstr.bin"))
    if memenr & 0x18F != 0x18F or memrstr & 0x18F:
        raise ValueError("Expanded AXISRAM gated/reset; no high-SRAM access attempted")
    live = bridge.checked_boot(b.upload(bridge.BOOT_PROOF, 92, "mdio-bridge-proof.bin"), prior["proof"]["nonce"])
    if live != prior["proof"] or b.upload(bridge.LOAD, len(boot_code), "mdio-bridge-code.bin") != boot_code:
        raise ValueError("Bridge code/proof changed")
    context = bridge.sd.context_proof(b, {bridge.BOOT_PARK}, "mdio-bridge-context")
    cfgr = struct.unpack("<II", b.upload(0x56028020, 8, "mdio-cfgr.bin"))
    pll = struct.unpack("<III", b.upload(0x56028080, 12, "mdio-pll1.bin"))
    ic1, = struct.unpack("<I", b.upload(0x560280C4, 4, "mdio-ic1.bin"))
    faults = struct.unpack("<II", b.upload(0xE000ED28, 8, "mdio-faults-before.bin"))
    if cfgr != (0x33330000, 0x100000) or pll != (0x404B00, 0, 0x49000005) or ic1 != 0x20000 or any(faults):
        raise ValueError("Clock/context/fault state differs from MDIO v2 precondition")
    apb5, = struct.unpack("<I", b.upload(0x5602827C, 4, "mdio-apb5enr.bin"))
    ahb5, = struct.unpack("<I", b.upload(0x56028260, 4, "mdio-ahb5enr.bin"))
    if apb5 & 0x44 or ahb5 & 0x80:
        raise ValueError("Unexpected active camera/SD peripheral clock; no helper load")
    m = plan["diagnostic"]
    b.call("-halt", "-w", MDIO_DIR / "mdio_diag.bin", hex(m["load"]), "-v",
           success="Download verified successfully")
    if b.upload(m["load"], len(code), "mdio-helper-readback.bin") != code:
        raise ValueError("MDIO helper RAM readback differs; not launched")
    save(out, "prepared.json", dict(plan=plan, bridge_terminal=live, context=context,
         memenr=memenr, memrstr=memrstr, cfgr=list(cfgr), pll=list(pll), ic1=ic1,
         faults=list(faults), apb5enr=apb5, ahb5enr=ahb5,
         helper_sha256=mdio.sha(code), launched=False))
    return b, m


def execute(output):
    out = Path(output).resolve()
    if HERE not in out.parents or out.exists():
        raise ValueError("Execution output must be a new campaign child directory")
    state = dict(passed=False, stage="prepare", reset_or_power_changed=False,
                 phy_writes=False, sd_commands=False, nor_commands=False)
    try:
        b, m = prepare(out)
        state["stage"] = "launch-read-only-mdio"
        save(out, "result.json", state)
        mdio.launch(b, m)
        state["stage"] = "bounded-completion-wait"
        save(out, "result.json", state)
        time.sleep(0.6)
        # Keep incomplete evidence; no automatic halt/retry/reset on a missing terminal.
        before = mdio.decode(b.upload(m["proof"], 2048, "mdio-terminal-before-observe.bin"))
        state["initial_observation"] = before
        if before["magic"] != 0x3144494D or before["version"] != 2 or before["state"] not in (4, 15):
            raise ValueError("No MDIO terminal proof; no automatic retry/recovery")
        result = mdio.observe(b, m)
        state["diagnostic"] = result
        if not result["completed_and_restored"]:
            raise ValueError("MDIO diagnosis did not complete with exact GPIO/clock restoration")
        state.update(passed=True, stage="complete", final_pc=hex(result["pc"]),
                     no_automatic_return_or_recovery=True)
    except Exception as error:
        state["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if out.exists():
            save(out, "result.json", state)
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.execute:
        if args.out is None:
            p.error("--execute requires --out")
        print(json.dumps(execute(args.out), indent=2))
    else:
        plan, _, _ = checked()
        print(json.dumps(dict(offline_checked=True, plan=plan), indent=2))


if __name__ == "__main__":
    main()
