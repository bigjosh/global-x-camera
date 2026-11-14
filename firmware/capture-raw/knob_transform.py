"""Opt-in controls receiver transform and two exact sensor-prefix relocations.

Capture builds keep their original prefix; only the combined USB/selector
packager may apply these relocations after binding the CRC-checked helper.
"""
import hashlib
import struct
import zlib

BASE = 0x34180400
CALL = 0x34181332
MANUAL_LITERAL = 0x341816A4
HELPER = 0x34200100
RECORD = 0x343F9400
MANUAL = RECORD + 64
OLD_CALL = bytes.fromhex('fff7d1f9')
OLD_MANUAL = 0x3418179C


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Controls transform anchor changed: ' + old[:90])
    return text.replace(old, new, 1)


def branch_link(address, target):
    displacement = target - address - 4
    if displacement & 1 or not -(1 << 24) <= displacement < (1 << 24):
        raise ValueError('Controls helper outside Thumb BL range')
    offset = displacement & 0x1FFFFFF
    s, i1, i2 = (offset >> 24) & 1, (offset >> 23) & 1, (offset >> 22) & 1
    return struct.pack('<HH', 0xF000 | (s << 10) | ((offset >> 12) & 0x3FF),
                       0xD000 | ((1 ^ i1 ^ s) << 13) | ((1 ^ i2 ^ s) << 11) | ((offset >> 1) & 0x7FF))


def patch_prefix(original):
    if len(original) != 6720:
        raise ValueError('Controls require the exact pre-selector prefix extent')
    call, manual = CALL - BASE, MANUAL_LITERAL - BASE
    if original[call:call+4] != OLD_CALL or struct.unpack_from('<I', original, manual)[0] != OLD_MANUAL:
        raise ValueError('Controls sensor call/manual-table anchor differs')
    result = bytearray(original)
    result[call:call+4] = branch_link(CALL, HELPER)
    struct.pack_into('<I', result, manual, MANUAL)
    return bytes(result), audit_prefix(original, result)


def audit_prefix(original, changed):
    if len(original) != len(changed) or len(original) != 6720:
        raise ValueError('Controls prefix dimensions changed')
    normalized = bytearray(changed)
    call, manual = CALL - BASE, MANUAL_LITERAL - BASE
    if (original[call:call+4] != OLD_CALL or
            struct.unpack_from('<I', original, manual)[0] != OLD_MANUAL or
            changed[call:call+4] != branch_link(CALL, HELPER) or
            struct.unpack_from('<I', changed, manual)[0] != MANUAL):
        raise ValueError('Controls prefix patch differs')
    normalized[call:call+4] = OLD_CALL
    struct.pack_into('<I', normalized, manual, OLD_MANUAL)
    if normalized != original:
        raise ValueError('Controls changed bytes outside the two sensor relocations')
    return dict(schema=1, call_address=CALL, helper_address=HELPER | 1,
                call_before=OLD_CALL.hex(), call_after=changed[call:call+4].hex(),
                manual_literal_address=MANUAL_LITERAL, manual_before=OLD_MANUAL,
                manual_after=MANUAL, record_address=RECORD,
                original_sha256=hashlib.sha256(original).hexdigest(),
                patched_sha256=hashlib.sha256(changed).hexdigest(),
                all_other_bytes_preserved=True, combined_selector_required=True)


def capture(text):
    text = once(text, '#include "runtime.h"', '#include "runtime.h"\n#include "capture_controls.h"')
    text = once(text, '#include "sensor_autostop.inc"',
                '#include "sensor_autostop.inc"\n#include "knob_capture.inc"')
    text = once(text, '  if(line_length!=1236U) MAGIC_FAIL(0x7D,-1);',
                '  if(!knob_record_valid() || line_length!=CAPTURE_CONTROLS->line_length) MAGIC_FAIL(0x7D,-1);')
    begin = text.index('  if(exposure_coarse!=RAW_EXPOSURE_COARSE) MAGIC_FAIL(0x90,-1);')
    end = text.index('\n#endif', begin) + len('\n#endif')
    text = text[:begin] + '  MAGIC_CHECK(0x9A,knob_verify_applied(line_length,exposure_coarse));' + text[end:]
    return text


def magic_runtime(text):
    text = once(text, 'MAGIC_LATE static int magic_publish(',
                'extern int raw_controls_metadata_freeze(void *destination);\n\nMAGIC_LATE static int magic_publish(')
    text = once(text, '        *available=(MAGIC_SLOTS_IMAGE_OFFSET+raw_capture_available())&~511U;',
                '        *available=(MAGIC_SLOTS_IMAGE_OFFSET+raw_capture_available())&~511U;\n'
                '        if(*available && raw_controls_metadata_freeze((void *)(RAW_SLOT_BUFFER_ADDRESS+4U))) return 3;')
    text = once(text, '    *available=MAGIC_SLOTS_PADDED_BYTES;',
                '    if(raw_controls_metadata_freeze((void *)(RAW_SLOT_BUFFER_ADDRESS+4U))) return 3;\n'
                '    *available=MAGIC_SLOTS_PADDED_BYTES;')
    return text


def contract(header_sha256):
    return dict(schema=1, record_address=RECORD, record_bytes=128, record_magic='CKN1',
                header_sha256=header_sha256, helper_address=HELPER | 1,
                requires_combined_selector=True, exposure_us=[1000, 500000],
                asa=[100, 200, 400, 800], analog_gain=[1, 2, 4, 8], digital_gain=1,
                line_lengths=[1280], maximum_frame_lines=65535,
                metadata_offset=4, metadata_bytes=128, metadata_reservation=152,
                metadata_policy='Snapshot configured/applied state before first nonzero publication; never rewrite',
                post_frame_validation='Latched line/coarse/frame/margin and applied analog/digital gain',
                first_sector_timeout_ms=3000, final_capture_timeout_ms=3000,
                autostop_timeout_ms=1000, autostop_timeout_origin='after FRAME')


def decode_record(raw):
    """Decode only the known half-second CKN1 record, not arbitrary slot data."""
    if len(raw) not in (128, 152) or (len(raw) == 152 and any(raw[128:])):
        raise ValueError('Controls metadata size/reserved tail differs')
    record = raw[:128]
    words = struct.unpack('<32I', record)
    if words[0:3] != (0x314E4B43, 1, 128) or zlib.crc32(record[:124]) != words[31]:
        raise ValueError('Controls metadata identity/CRC differs')
    state, error, flags = words[3:6]
    expected_flags = 23 | (8 if state == 4 else 0)
    if state not in (3, 4) or error or flags != expected_flags or any(words[29:31]):
        raise ValueError('Controls metadata state/flags/reserved fields differ')
    requested, line, frame = words[13:16]
    manual = record[64:76]
    coarse = int.from_bytes(manual[2:4], 'little')
    asa, vt, applied_coarse, applied_gain, applied_digital, margin = words[19:25]
    expected_coarse = (requested*160800000 + 1280000000-1)//1280000000
    gain = {100: 0, 200: 16, 400: 24, 800: 28}.get(asa)
    if (not 1000 <= requested <= 500000 or line != 1280 or vt != 160800000 or
            coarse != expected_coarse or coarse < 21 or
            frame != max(4336, coarse+2000) or frame > 65535 or margin > 1993 or
            coarse > frame-margin-7 or manual[0] != 2 or manual[1] != gain or
            manual[4:] != bytes((0, 1))*4):
        raise ValueError('Controls metadata timing/gain bounds differ')
    if state == 4 and (applied_coarse, applied_gain, applied_digital) != (coarse, gain, 256):
        raise ValueError('Controls applied readback differs from configured values')
    return dict(schema=1, state=state, validation='applied' if state == 4 else 'configured',
                exposure_raw=words[9], asa_raw=words[10],
                exposure_fraction_q16=words[11], asa_fraction_q16=words[12],
                requested_us=requested, nominal_exposure_us=(coarse*line*1000000+vt//2)//vt,
                line_length=line, coarse_lines=coarse, frame_length=frame, margin=margin,
                asa=asa, asa_provisional=True, analog_gain=32//(32-gain),
                analog_code=gain, digital_gain=1, applied_coarse=applied_coarse,
                applied_gain=applied_gain, applied_digital=applied_digital,
                crc32=words[31])
