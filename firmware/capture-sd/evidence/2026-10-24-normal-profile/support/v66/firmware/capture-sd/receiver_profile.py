"""Deterministic receiver profile transform for the pinned v45b source."""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PROOF_REGIONS = {
    "TRACE": (0x343F0000, 64 * 4),
    "EVENTS": (0x343F0100, 200 * 4 * 4),
    "ERROR_HISTORY": (0x343F1000, 16 * 12 * 4),
    "STAGE1_STATUS_RESERVED": (0x343F3000, 64 * 4),
    "SENSOR": (0x343F4000, 32 * 4),
    "MEMORY_COPY": (0x343F5000, 32 * 4),
    "RAW10": (0x343F6000, 10 * 4),
    "PE1_RECOVERY_COPY": (0x343F7000, 24 * 4),
    "VCP_RECOVERY_COPY": (0x343F7080, 32 * 4),
    "FAST": (0x343F8000, (32 + 32 * 16) * 4),
    "SHUTDOWN": (0x343F8900, 16 * 4),
    "FORCE": (0x343F8940, 32 * 4),
    "LED": (0x343F89C0, 32 * 4),
    "RCP2": (0x343F8A80, 32 * 4),
    "LATE_LOADER": (0x343F9B00, 16 * 4),
    "COMPLETION": (0x343F9C00, 64 * 4),
    "PERIPHERALS": (0x343F9D00, 64 * 4),
    "SAVE_LOADER": (0x343F9E00, 16 * 4),
    "SAVE_REQUEST": (0x343F9F00, 16 * 4),
    "SAVE_REPORT": (0x343FA000, 128 * 4),
    "CARD_RESERVED": (0x343FA200, 128 * 4),
    "FS_RESERVED": (0x343FA400, 128 * 4),
}


def literal(text, name):
    match = re.search(r"^#define\s+" + re.escape(name) + r"\s+.*?\b(0x[0-9A-Fa-f]+|[0-9]+)U?\b", text, re.M)
    if not match:
        raise ValueError("Missing literal definition: " + name)
    return int(match[1], 0)


def check_regions(status_led_header=None, capture_header=None, overrides=None):
    """Check all simultaneously live high-SRAM proof/reserved regions.

    LED and RCP2 addresses/sizes come from their actual copied headers, so a
    future header edit cannot silently disagree with the static inventory.
    """
    status_led_header = status_led_header or HERE.parent / "capture-timing/status_leds/status_leds.h"
    capture_header = capture_header or HERE / "capture_profile.h"
    led = Path(status_led_header).read_text(encoding="utf-8")
    profile = Path(capture_header).read_text(encoding="utf-8")
    inventory = dict(PROOF_REGIONS)
    inventory["LED"] = literal(led, "STATUS_LED_PROOF"), literal(led, "STATUS_LED_PROOF_WORDS") * 4
    inventory["RCP2"] = literal(profile, "CAPTURE_PROFILE_ADDRESS"), literal(profile, "CAPTURE_PROFILE_WORDS") * 4
    if overrides:
        inventory.update(overrides)
    regions = sorted((start, start + size, name) for name, (start, size) in inventory.items())
    assert all(0x343F0000 <= start < end <= 0x34400000 for start, end, _ in regions)
    for previous, following in zip(regions, regions[1:]):
        assert previous[1] <= following[0], (previous, following)
    return {name: dict(start=hex(start), end_exclusive=hex(start + size))
            for name, (start, size) in inventory.items()}


LIFETIME_ALIASES = [
    dict(region="0x34000000..0x342e9f20", ownership="captured frame plus 32-byte canary",
         aliases="completed low-SRAM prefix, recovery proofs and NOR/readback helpers; never concurrent"),
    dict(region="0x34320000..0x343a0000", ownership="SAVE code and bounded BSS",
         aliases="PNG workspace and READ buffer are an operation-exclusive union"),
    dict(region="0x343a0000..0x343b0000", ownership="runtime stack and canary", aliases="none"),
    dict(region="0x343c0000..0x343c2000", ownership="late completion code",
         aliases="148-byte maintenance helper at 0x343c0000 and 64-byte status at 0x343c0400; LPL/LPM guards prohibit concurrent maintenance"),
]

EARLY_REGIONS = {
    "PREFIX_RESERVED": (0x34180400, 0x1C00),
    # Conservative reservation from the linker end to stage1.S's initial MSP;
    # this is a lifetime bound, not a measured maximum stack usage.
    "PREFIX_STACK_RESERVED": (0x34182000, 0x6000),
    "NOR_OR_READBACK_REQUEST": (0x341B4000, 64),
    "NOR_OR_READBACK_PROOF_RESERVED": (0x341B4100, 224),
    "NOR_DIAGNOSTIC": (0x341B4300, 104),
    "HELPER_STACK": (0x341B6000, 0x2000),
    "NOR_INPUT": (0x341C0000, 0x10000),
    "NOR_OUTPUT": (0x341D0000, 0x10000),
    "HELPER_CODE_RESERVED": (0x341E0000, 0x10000),
    "MEMORY_BOOT": (0x341F5000, 128),
    "PE1_RECOVERY": (0x341F7000, 96),
    "VCP_RECOVERY": (0x341F7080, 128),
}


def check_early_regions():
    """Separate lifetime: these bytes become frame storage after handoff."""
    rows = sorted((start, start + size, name) for name, (start, size) in EARLY_REGIONS.items())
    for previous, following in zip(rows, rows[1:]):
        assert previous[1] <= following[0], (previous, following)
    return {name: dict(start=hex(start), end_exclusive=hex(start + size))
            for name, (start, size) in EARLY_REGIONS.items()}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Expected exactly one receiver anchor: " + old[:80])
    return text.replace(old, new)


def profile_metadata(profile, status_led_header=None, capture_header=None):
    if profile not in ("normal", "diagnostic"):
        raise ValueError("Unknown diagnostics profile")
    regions = check_regions(status_led_header, capture_header)
    return dict(schema=2, address=regions["RCP2"]["start"], bytes=128,
                magic="0x52435032", diagnostics_profile=profile,
                profile_value=int(profile == "diagnostic"),
                required_performed_flags="0x7f" if profile == "diagnostic" else "0x1f",
                skipped_trace_words=[] if profile == "diagnostic" else [8, 9, 10, 11],
                fine_timing_clock="DWT CYCCNT at nominal 400 MHz; unsigned 32-bit deltas",
                essential_sensor_reads=["0x0300 line length", "0x030a RAW bits", "0x030f data type"],
                full_frame_scan=profile == "diagnostic",
                routine_register_snapshots=True,
                optional_sensor_register_reads=profile == "diagnostic",
                disjoint_proof_regions=regions, lifetime_aliases=LIFETIME_ALIASES,
                early_helper_regions=check_early_regions())


def transform(text):
    if '#include "capture_profile.h"' in text:
        raise ValueError("Receiver profile transform is already applied")
    text = once(text, '#include "status_leds.h"',
                '#include "status_leds.h"\n#include "capture_profile.h"\n'
                '#define CPROF ((volatile uint32_t *)CAPTURE_PROFILE_ADDRESS)')
    # Cheap CSI snapshots, cumulative raw history, ForceRx guards and error
    # records remain byte-for-byte source-identical in both profiles.
    # Do not extend the cold-start critical path: initialize after frame IRQ.
    begin = text.index('  event(31); fast_snapshot(431);')
    end = text.index('  event(40);\n  status_led_complete_sleep();', begin)
    old = text[begin:end]
    expected = ['raw10[1]!=BYTES', 'line_length!=1236U', 'raw_bits!=10U',
                'HAL_DCMIPP_CSI_PIPE_Stop', 'fast_shutdown_data_off();',
                'VD6G_Stop(&sensor)', 'hash=(hash^v)*16777619U', 'FAST[1]=40;']
    if not all(token in old for token in expected):
        raise ValueError("Frozen receiver completion structure changed")
    return text[:begin] + POST_FRAME + text[end:]


POST_FRAME = r'''  event(31); fast_snapshot(431);
  uint32_t profile_started=DWT->CYCCNT;
  for(unsigned i=0;i<CAPTURE_PROFILE_WORDS;++i) CPROF[i]=0U;
  CPROF[CP_MAGIC]=CAPTURE_PROFILE_MAGIC;
  CPROF[CP_SCHEMA]=CAPTURE_PROFILE_SCHEMA; CPROF[CP_WORDS]=CAPTURE_PROFILE_WORDS;
  CPROF[CP_PROFILE]=CAPTURE_DIAGNOSTICS; CPROF[CP_STATE]=1U;
  CPROF[CP_POST_FRAME_BEGIN]=profile_started;
  CPROF[CP_FRAME]=(uint32_t)g_frame; CPROF[CP_BYTES]=BYTES;
  CPROF[CP_WIDTH]=WIDTH; CPROF[CP_HEIGHT]=HEIGHT;
  TRACE[44]=CSI->SR0; TRACE[45]=CSI->SR1;
  volatile uint32_t *raw10=(volatile uint32_t *)0x343F6000U;
  raw10[0]=0x52313046U; raw10[1]=DCMIPP->P0DCCNTR;
  raw10[2]=DCMIPP->P0PPCR; raw10[3]=DCMIPP->P0DCLMTR;
  raw10[4]=CSI->VC0CFGR1; raw10[5]=DCMIPP->P0FSCR;
  raw10[6]=DCMIPP->CMSR2; raw10[7]=0;
  volatile uint32_t *guard=(volatile uint32_t *)(0x34000000U+BYTES);
  for(unsigned i=0;i<8;++i) if(guard[i]!=(0xA15A1000U+i)) raw10[7]|=1U<<i;
  CPROF[CP_DMA_BYTES]=raw10[1]; CPROF[CP_CANARY_MASK]=raw10[7]^255U;
  if(raw10[1]!=BYTES || raw10[7]) fail(0x81,-1);
  CPROF[CP_FLAGS]=CP_F_GEOMETRY|CP_F_CANARY;

  uint16_t line_length=0;
  check(0x54,rd16(&sensor,0x0300,&line_length)); TRACE[47]=line_length;
  early_sensor[11]=line_length;
  if(line_length!=1236U) fail(0x7D,-1);
  uint8_t raw_bits=0,raw_dt=0;
  check(0x82,rd8(&sensor,0x030A,&raw_bits));
  check(0x83,rd8(&sensor,0x030F,&raw_dt));
  raw10[8]=raw_bits; raw10[9]=raw_dt;
  CPROF[CP_BITS]=raw_bits; CPROF[CP_DATA_TYPE]=raw_dt;
  if(raw_bits!=10U || raw_dt!=0x2BU) fail(0x84,-1);
  CPROF[CP_FLAGS]|=CP_F_RAW10;
  CPROF[CP_ESSENTIAL_DONE]=DWT->CYCCNT;
#if CAPTURE_DIAGNOSTICS
  CPROF[CP_DIAGNOSTIC_READS_BEGIN]=DWT->CYCCNT;
  uint16_t coarse=0,sensor_rom=0;
  check(0x53,rd16(&sensor,0x0064,&coarse)); TRACE[46]=coarse;
  check(0x7E,rd16(&sensor,0x0014,&sensor_rom)); early_sensor[10]=sensor_rom;
  uint8_t sensor_orientation=0;
  check(0x7F,rd8(&sensor,0x001A,&sensor_orientation)); early_sensor[17]=sensor_orientation;
  uint32_t clock_value;
  for(unsigned i=0;i<4;++i) { check(0x60+i,rd32(&sensor,0x0034+i*4,&clock_value)); TRACE[52+i]=clock_value; }
  check(0x64,rd32(&sensor,0x0044,&clock_value)); TRACE[56]=clock_value;
  uint8_t clock_byte;
  check(0x65,rd8(&sensor,0x0048,&clock_byte)); TRACE[57]=clock_byte;
  check(0x66,rd16(&sensor,0x0458,&coarse)); TRACE[58]=coarse;
  CPROF[CP_DIAGNOSTIC_READS_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_REGISTER_DUMPS;
#endif

  /* Preserve idle-checked data disable before sensor STOP. */
  fast_snapshot(435); CPROF[CP_PIPE_STOP_BEGIN]=DWT->CYCCNT;
  check(32, HAL_DCMIPP_CSI_PIPE_Stop(&hcam,DCMIPP_PIPE0,DCMIPP_VIRTUAL_CHANNEL0));
  CPROF[CP_PIPE_STOP_DONE]=DWT->CYCCNT; fast_snapshot(439);
#if FAST_SHUTDOWN_DATA_OFF
  fast_shutdown_data_off();
#else
#error "Profile proof requires the qualified idle-checked data disable"
#endif
  CPROF[CP_DATA_OFF_DONE]=DWT->CYCCNT;
  check(33, VD6G_Stop(&sensor));
  CPROF[CP_SENSOR_STOP_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
  fast_snapshot(436); __DSB();
#if CAPTURE_DIAGNOSTICS
  CPROF[CP_SCAN_BEGIN]=DWT->CYCCNT;
  uint32_t min=255,max=0,sum=0,hash=2166136261U;
  for (unsigned i=0;i<BYTES;++i) { uint32_t v=g_frame[i]; if(v<min)min=v; if(v>max)max=v; sum+=v; hash=(hash^v)*16777619U; }
  TRACE[8]=min; TRACE[9]=max; TRACE[10]=sum; TRACE[11]=hash;
  CPROF[CP_FNV]=hash; CPROF[CP_SCAN_DONE]=DWT->CYCCNT;
  CPROF[CP_FLAGS]|=CP_F_FULL_SCAN;
#else
  TRACE[8]=0U; TRACE[9]=0U; TRACE[10]=0U; TRACE[11]=0U;
#endif
  TRACE[5]=frames; TRACE[6]=vsyncs; TRACE[7]=errors;
  TRACE[12]=(uint32_t)g_frame; TRACE[13]=BYTES; TRACE[14]=WIDTH; TRACE[15]=HEIGHT;
  TRACE[4] |= hcam.ErrorCode;
  CPROF[CP_ERRORS]=TRACE[4]|errors;
  if(frames!=1U || CPROF[CP_ERRORS]) fail(0x85,-1);
  CPROF[CP_FLAGS]|=CP_F_ERRORS;
  fast_snapshot(440); if(FAST[3]) fail(0xA2,-1); FAST[1]=40;
  CPROF[CP_HANDOFF_READY]=DWT->CYCCNT;
  __DMB(); CPROF[CP_STATE]=2U; __DMB();
'''
