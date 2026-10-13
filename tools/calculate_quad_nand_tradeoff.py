"""Reproduce quad-versus-parallel NAND screening models, not measured camera limits."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_BYTES = 644 * 604 * 10 // 8
PARTS = {
    "alliance_x8": dict(part="AS9F14G08SA-45BIN", page=2048, spare=128,
                        cycle_ns=45, program_typ_us=300, program_max_us=700,
                        program_typ_ma=None, program_max_ma=20, host_ecc=True,
                        read_typ_us=None, read_max_us=30),
    "winbond_quad": dict(part="W25N04KWZEIR", page=2048, spare=128,
                         clocks_mhz=[50, 100], program_typ_us=250, program_max_us=700,
                         program_typ_ma=25, program_max_ma=35, host_ecc=False,
                         read_typ_us=45, read_max_us=65),
    "micron_quad": dict(part="MT29F4G01ABBFDWB-IT:F", page=4096, spare=256,
                        clocks_mhz=[50, 83], program_typ_us=240, program_max_us=600,
                        program_typ_ma=20, program_max_ma=25, host_ecc=False,
                        read_typ_us=90, read_max_us=170),
    "macronix_quad_randomizer_off": dict(part="MX35UF4G24AD-Z4I8", page=4096, spare=256,
                        clocks_mhz=[50, 100], program_typ_us=320, program_max_us=700,
                        program_typ_ma=23, program_max_ma=30, host_ecc=True),
    "macronix_quad_randomizer_on": dict(part="MX35UF4G24AD-Z4I8", page=4096, spare=256,
                        clocks_mhz=[50, 100], program_typ_us=360, program_max_us=740,
                        program_typ_ma=23, program_max_ma=30, host_ecc=True),
}


def calculate(p, clock_mhz, include_spare):
    pages = math.ceil(IMAGE_BYTES / p["page"])
    byte_count = pages * (p["page"] + (p["spare"] if include_spare else 0))
    if clock_mhz is None:
        transfer_ms = byte_count * p["cycle_ns"] / 1e6
        command_ms = 0  # Same baseline as earlier parallel comparison.
    else:
        transfer_ms = byte_count * 8 / (4 * clock_mhz * 1000)
        command_ms = pages * 64 / (clock_mhz * 1000)  # WREN8 + LOAD24 + EXEC32.
    busy_typ_ms = pages * p["program_typ_us"] / 1000
    busy_max_ms = pages * p["program_max_us"] / 1000
    return dict(
        clock_mhz=clock_mhz, pages=pages, transferred_bytes=byte_count,
        transfer_ms=transfer_ms, serial_command_ms=command_ms,
        program_busy_typ_ms=busy_typ_ms, program_busy_max_ms=busy_max_ms,
        write_typ_program_ms=transfer_ms + command_ms + busy_typ_ms,
        write_max_program_ms=transfer_ms + command_ms + busy_max_ms,
        program_typ_energy_mj=(None if p["program_typ_ma"] is None else
                               1.8 * p["program_typ_ma"] * busy_typ_ms / 1000),
        program_max_current_typ_time_mj=1.8*p["program_max_ma"]*busy_typ_ms/1000,
        program_max_current_max_time_mj=1.8*p["program_max_ma"]*busy_max_ms/1000,
    )


results = {mode: {name: [calculate(p, clock, include_spare)
                        for clock in p.get("clocks_mhz", [None])]
                  for name, p in PARTS.items()}
           for mode, include_spare in (("data_only", False), ("full_spare_allowance", True))}
baseline = results["full_spare_allowance"]["alliance_x8"][0]["write_typ_program_ms"]
for rows in results["full_spare_allowance"].values():
    for row in rows:
        delta = baseline - row["write_typ_program_ms"]
        row["time_saved_vs_alliance_ms"] = delta
        row["other_board_energy_saved_at_200mw_mj"] = 0.2 * delta

capacities = []
for gibits in [1, 2, 4]:
    capacity = gibits * 2**30 // 8
    capacities.append(dict(gibit=gibits, capacity_mib=capacity // 2**20,
        tightly_packed_2k_page_images=capacity // (math.ceil(IMAGE_BYTES/2048)*2048),
        images_512kib_allocation=capacity // (512*1024),
        images_512kib_allocation_after_20pct_reserve=math.floor(0.8*capacity/(512*1024))))

verification = []
for name, write_clock, read_clock in (("alliance_x8", None, None),
                                    ("winbond_quad", 100, 100),
                                    ("micron_quad", 50, 30)):
    p = PARTS[name]
    write = calculate(p, write_clock, True)
    load_ms = (write["transferred_bytes"]*p["cycle_ns"]/1e6 if read_clock is None else
               write["transferred_bytes"]*8/(4*read_clock*1000))
    read_typ = (None if p["read_typ_us"] is None else
                load_ms + write["pages"]*p["read_typ_us"]/1000)
    read_max = load_ms + write["pages"]*p["read_max_us"]/1000
    verification.append(dict(part=p["part"], read_clock_mhz=read_clock,
        read_transfer_ms=load_ms, read_typ_array_ms=read_typ, read_max_array_ms=read_max,
        write_typ_plus_read_typ_array_ms=(None if read_typ is None else
                                         write["write_typ_program_ms"]+read_typ),
        write_typ_plus_read_max_array_ms=write["write_typ_program_ms"]+read_max))

report = dict(date="2026-09-08", image_bytes=IMAGE_BYTES, parts=PARTS,
              results=results, capacity=capacities, verification=verification, assumptions=[
    "Packed RAW10, full 644x604 image; 16-bit containers have different capacity and timing.",
    "Pre-erased storage, sequential ordinary page programs; no cache/two-plane overlap.",
    "Full-spare mode is a conservative byte-count allowance, not permission to write internal-ECC bytes.",
    "Write only legal user OOB; data-only mode gives the alternate bus-time calculation.",
    "Serial model includes 64 command clocks per page; parallel command overhead omitted as in prior baseline.",
    "Excludes DMA/CS gaps/status polling, host ECC, metadata commit, verification, retries, erase, boot, shutdown.",
    "Maximum-program model is not a whole-operation bound; bus/host overhead is not bounded.",
    "Program energy is NAND internal-busy only at nominal 1.8V, not total storage/camera/battery energy.",
    "Alliance normal-program typical current unspecified; its max-current/typical-time product is not typical.",
    "Common 200mW other-board load is illustrative; real MCU sleep and rail gating alter savings.",
    "Micron 83MHz is a quad LOAD screening case; quad READ has a separate lower limit in Rev F.",
    "Verification rows use fixed bus rates with typical/max array latency, omitting read commands/CRC/host ECC.",
    "Capacity reserve is a planning allowance, not a manufacturer or final firmware guarantee.",
])
target = ROOT / "docs/power/quad-nand-calculations.json"
target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"output": str(target), "capacity": capacities,
                  "verification": verification}, indent=2))
