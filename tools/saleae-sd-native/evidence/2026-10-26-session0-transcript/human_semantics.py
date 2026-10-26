"""Human descriptions for the native-SD decoder's all-events CSV.

Offline helper; no device access. Values are decoded from recorded events, not
filled from firmware expectations. SD v2 primary references are documented in
SOURCES below. Reserved/unknown values remain explicit.
"""
from __future__ import annotations

import re

SOURCES = {
    "commands": "SD Physical Layer Simplified v2.00, sections 4.7 and 4.8; printed pp46-57",
    "responses": "SD Physical Layer Simplified v2.00, section 4.9; printed pp58-60",
    "card_status": "SD Physical Layer Simplified v2.00, Table 4-35; printed pp62-63",
    "registers": "SD Physical Layer Simplified v2.00, chapter 5, CID/CSD/SCR",
}

STATE = {0: "IDLE", 1: "READY", 2: "IDENTIFICATION", 3: "STANDBY",
         4: "TRANSFER", 5: "SENDING DATA", 6: "RECEIVING DATA",
         7: "PROGRAMMING", 8: "DISCONNECT"}
STATUS = {
    31: "argument out of range", 30: "address misalignment", 29: "invalid block length",
    28: "invalid erase sequence", 27: "invalid erase parameter", 26: "write-protection violation",
    25: "card locked", 24: "lock/unlock failed", 23: "command CRC failed",
    22: "illegal command", 21: "uncorrectable internal ECC", 20: "internal controller error",
    19: "general card error", 16: "CSD overwrite violation", 15: "write-protected erase skipped",
    14: "internal ECC disabled", 13: "erase sequence reset", 3: "authentication sequence error",
}


def parse_fields(text: str | dict) -> dict[str, str]:
    if isinstance(text, dict):
        return text
    # CRC-lane text contains semicolons. Preserve field boundaries only at keys.
    pairs = re.findall(r"(?:^|; )([^;=]+)=((?:(?!; [^;=]+=).)*)", text)
    return dict(pairs)


def integer(value: str | int, default: int = 0) -> int:
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return default


def register_bits(value: int, hi: int, lo: int) -> int:
    return (value >> lo) & ((1 << (hi - lo + 1)) - 1)


def voltage_window(value: int) -> str:
    ranges = [(i, 2.7 + (i - 15) / 10) for i in range(15, 24) if value & (1 << i)]
    if not ranges:
        return f"voltage-window mask 0x{value & 0xFFFFFF:06X}"
    # Typical cards advertise a contiguous window; list non-contiguous windows.
    groups = []
    lo = hi = ranges[0][1]
    prev = ranges[0][0]
    for bit, v in ranges[1:]:
        if bit != prev + 1:
            groups.append(f"{lo:.1f}-{hi + .1:.1f} V")
            lo = v
        hi, prev = v, bit
    groups.append(f"{lo:.1f}-{hi + .1:.1f} V")
    return ", ".join(groups)


def status_text(value: int, r6: bool = False) -> str:
    state = (value >> 9) & 15
    ready = "READY_FOR_DATA=1 (card buffer ready)" if value & 0x100 else "READY_FOR_DATA=0 (card buffer not ready)"
    parts = [f"state when command arrived: {STATE.get(state, 'reserved ' + str(state))}", ready]
    if value & 0x20:
        parts.append("APP_CMD set")
    if r6:
        flags = [label for bit, label in [(15, "command CRC failed"), (14, "illegal command"),
                                          (13, "general card error")] if value & (1 << bit)]
        if value & 8:
            flags.append("authentication sequence error")
    else:
        flags = [label for bit, label in STATUS.items() if value & (1 << bit)]
    parts.append("flags: " + ", ".join(flags) if flags else "no reported error/status exception")
    return "; ".join(parts)


def cid_description(hex120: str) -> str:
    b = bytes.fromhex(hex120)
    if len(b) != 15:
        return "CID payload has unexpected length"
    ascii_field = lambda x: x.decode("ascii", errors="replace")
    date = int.from_bytes(b[13:15], "big") & 0xFFF
    return (f"card identity: manufacturer ID 0x{b[0]:02X}; OEM/application ID {ascii_field(b[1:3])!r}; "
            f"product {ascii_field(b[3:8])!r}; revision {b[8] >> 4}.{b[8] & 15}; "
            f"serial 0x{int.from_bytes(b[9:13], 'big'):08X}; manufacture {2000 + (date >> 4):04d}-{date & 15:02d}")


def csd_description(hex120: str) -> str:
    value = int(hex120, 16) << 8  # fields contain bits127:8, CRC/end excluded
    g = lambda hi, lo: register_bits(value, hi, lo)
    version = g(127, 126)
    speed = g(103, 96)
    units = [100_000, 1_000_000, 10_000_000, 100_000_000]
    tenths = [0, 10, 12, 13, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80]
    hz = units[speed & 7] * tenths[(speed >> 3) & 15] // 10 if (speed & 7) < 4 and not (speed & 128) else 0
    parts = [f"CSD structure {version} ({'SDHC/SDXC' if version == 1 else 'SDSC' if version == 0 else 'unparsed'})"]
    if version == 1:
        sectors = (g(69, 48) + 1) * 1024
        parts.append(f"capacity {sectors:,} sectors x 512 B = {sectors * 512:,} B")
    elif version == 0:
        capacity = (g(73, 62) + 1) * (1 << (g(49, 47) + 2)) * (1 << g(83, 80))
        parts.append(f"capacity {capacity:,} B")
    parts += [f"default maximum transfer rate {hz / 1e6:g} MHz" if hz else f"unrecognized TRAN_SPEED 0x{speed:02X}",
              f"read block length {1 << g(83, 80)} B", f"write block length {1 << g(25, 22)} B",
              f"permanent write-protect {g(13, 13)}; temporary write-protect {g(12, 12)}"]
    return "; ".join(parts)


def scr_description(preview: str) -> str:
    b = bytes.fromhex(preview)
    if len(b) != 8:
        return "SCR payload has unexpected length"
    value = int.from_bytes(b, "big")
    width = (value >> 48) & 15
    widths = [str(n) + "-bit" for mask, n in [(1, 1), (4, 4)] if width & mask]
    return (f"SCR: structure {(value >> 60) & 15}; SD_SPEC {(value >> 56) & 15}; "
            f"supports {' and '.join(widths) or 'unrecognized bus widths'}; "
            f"DATA_STAT_AFTER_ERASE={'0xFF' if (value >> 55) & 1 else '0x00'}")


class Explainer:
    def __init__(self):
        self.block_addressed: bool | None = None
        self.last_data_command: tuple[int, bool] | None = None

    def command(self, c: int, arg: int, app: bool) -> str:
        if app:
            if c == 41:
                return (f"request card power-up/operating conditions; host supports high-capacity cards: {'yes' if arg & 0x40000000 else 'no'}; "
                        f"host voltage window {voltage_window(arg)}; 1.8 V switch requested: {'yes' if arg & 0x1000000 else 'no'}")
            if c == 6:
                return f"set native SD data width to { {0: '1 bit', 2: '4 bits'}.get(arg & 3, 'reserved encoding')}"
            if c == 23:
                return f"pre-erase hint for {(arg & 0x7FFFFF):,} blocks before next multiblock write; does not set its transfer length"
            if c == 51:
                self.last_data_command = (c, app)
                return "read 8-byte SD Configuration Register (SCR) on data lines"
            if c == 13:
                self.last_data_command = (c, app)
                return "read 64-byte SD Status register on data lines"
            if c == 22:
                return "request number of successfully written blocks (4-byte data reply)"
            return f"application command {c}; argument 0x{arg:08X}"
        if c == 0:
            self.block_addressed = None
            return "reset card to IDLE/native initialization; no response is expected"
        if c == 8:
            return f"check interface compatibility: supplied voltage code {(arg >> 8) & 15} (1 = 2.7-3.6 V); echo test pattern 0x{arg & 255:02X}"
        if c == 55:
            return f"prefix next accepted command as an application command; addressed RCA 0x{arg >> 16:04X}"
        if c == 2:
            return "ask card for its CID identity register"
        if c == 3:
            return "ask card to publish a Relative Card Address (RCA); host does not assign the RCA in this command"
        if c in (7, 9, 10, 13):
            actions = {7: "select card" if arg >> 16 else "deselect all cards", 9: "read CSD capabilities/capacity register",
                       10: "read CID identity register", 13: "query card status and readiness"}
            return f"{actions[c]}; RCA 0x{arg >> 16:04X}"
        if c == 16:
            return f"set data block length to {arg:,} bytes"
        if c in (17, 18, 24, 25):
            self.last_data_command = (c, app)
            mode = {17: "read one block", 18: "start multiblock read", 24: "write one block", 25: "start multiblock write"}[c]
            address = f"LBA {arg:,} (byte offset {arg * 512:,})" if self.block_addressed else f"byte address {arg:,}" if self.block_addressed is False else f"address 0x{arg:08X} (addressing mode not yet established)"
            return f"{mode} at {address}" + ("; continues until stop/count completion" if c in (18, 25) else "")
        if c == 12:
            return "stop current multiblock transfer; check R1b and DAT0 busy release before considering card ready"
        if c == 23:
            return f"set explicit multiblock transfer count to {arg:,} blocks (CMD23, not the ACMD23 pre-erase hint)"
        if c == 6:
            self.last_data_command = (c, app)
            groups = ", ".join(f"group {i + 1}={'unchanged' if ((arg >> (i * 4)) & 15) == 15 else str((arg >> (i * 4)) & 15)}" for i in range(6))
            return f"{'switch' if arg & 0x80000000 else 'check'} function selection; {groups}; return 64-byte switch-status block"
        if c in (32, 33):
            return f"set erase range {'start' if c == 32 else 'end'} address to {arg:,} (inclusive)"
        if c == 38:
            return "erase the previously selected address range; R1b/DAT0 busy applies"
        return f"command {c}; argument 0x{arg:08X}; semantics not implemented"

    def response(self, fields: dict) -> str:
        typ = fields.get("response_type", "unknown")
        value = integer(fields.get("value", "0"))
        cmd = integer(fields.get("command", "-1"), -1)
        if typ in ("R1", "R1b"):
            return status_text(value) + ("; optional DAT0 busy phase is tracked separately" if typ == "R1b" else "")
        if typ == "R3":
            complete = bool(value & 0x80000000)
            if complete:
                self.block_addressed = bool(value & 0x40000000)
            return (f"power-up {'complete' if complete else 'still in progress'}; voltage window {voltage_window(value)}; "
                    f"CCS={(value >> 30) & 1}" + (f" ({'512-byte block addressing' if self.block_addressed else 'byte addressing'})" if complete else " (not valid until power-up completes)") + "; R3 has no CRC7")
        if typ == "R6":
            return f"assigned RCA 0x{value >> 16:04X}; " + status_text(value & 0xFFFF, r6=True)
        if typ == "R7":
            return f"accepted voltage code {(value >> 8) & 15} (1 = 2.7-3.6 V); echoed check pattern 0x{value & 255:02X}"
        if typ == "R2":
            payload = fields.get("CID_CSD_120_bits", "")
            return csd_description(payload) if cmd == 9 else cid_description(payload) if cmd in (2, 10) else "unassociated CID/CSD register"
        return "unassociated or unsupported response; do not infer card state"

    def event(self, row: dict) -> str:
        f = parse_fields(row.get("fields", ""))
        typ = row.get("type", "")
        description = row.get("description", row.get("text", ""))
        invalid = str(row.get("error", "false")).lower() == "true"
        if typ in ("command", "response") and (f.get("crc") == "BAD" or f.get("end_bit") == "BAD" or "FRAMING BAD" in description):
            return "INVALID decoded token; retain raw fields but do not interpret as an accepted card transaction"
        if typ == "command":
            return self.command(integer(f.get("command", "-1"), -1), integer(f.get("argument", "0")), f.get("application") == "yes")
        if typ == "response":
            return self.response(f)
        if typ == "data_block":
            if self.last_data_command == (51, True):
                return scr_description(f.get("preview", "")) + "; " + f.get("CRC16 received/calculated", "")
            return (f"{f.get('bytes', '?')}-byte packet on {f.get('width', '?')} data lanes" +
                    (f"; {f['address']}" if "address" in f else "") +
                    f"; {'CRC/framing failure' if invalid else 'all active-lane CRC16s and end bits pass'}; first bytes {f.get('preview', '')}")
        if typ == "write_status":
            status = integer(f.get("status", "-1"), -1)
            return {2: "card accepted this data packet's CRC (010); programming can still be busy", 5: "card rejected this packet: CRC error (101)"}.get(status, f"reserved/unrecognized native write-status token {status:03b}")
        if typ == "busy":
            return "DAT0 held low: card busy; raw rising edge ends this interval" + ("; capture truncation: duration is a lower bound" if f.get("complete") == "no" else "")
        if typ == "bus_width":
            return f"accepted ACMD6 switches subsequent data packets to {f.get('width', '?')}-bit mode"
        return description or typ
