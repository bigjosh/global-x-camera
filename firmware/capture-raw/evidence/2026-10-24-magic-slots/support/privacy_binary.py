"""Pure, fail-closed classification of reviewed magic experiment binaries.

No filesystem, bench, runtime or instrument imports. This is an accidental
payload-retention guard, not a defense against deliberately encoded secrets in
otherwise valid diagnostics. The caller must classify the record as nonpixel
and separately authorize any legacy metadata/erased-sector exception.
"""
import hashlib
import math
import re
import struct
import zlib


def require(ok, message):
    if not ok:
        raise ValueError(message)


# Inventory: archive-selection.draft-v3.json, selected omit-class records.
# Size alone is insufficient for code: the separate CODE map pins every byte.
SIZES = {}
for size, names in {
    4: '''ahb4enr-after ahb4enr-before ahb4rstr-after ahb4rstr-before
        ahb5enr ahb5rstr before-context-ccr before-context-fpccr
        bridge-final-ccr bridge-final-fpccr ccr clock completed-ccr
        completed-fpccr failed-format-ccr failed-format-fpccr fpccr
        helper-complete-ccr helper-complete-fpccr initial-gpio pwr-cpucr
        rcc-en rcc-enable-before rcc-enable rcc-reset-before rcc-reset
        rcc-rst system-clock xspi-sr''',
    16: 'before-scr completed-scr scr request request-readback',
    32: 'before-erase completed-erase erase chunks magic-chunk magic-proof frame-guard',
    40: 'gpioc-before gpioc',
    44: 'before-stream',
    64: 'late-loader raw-request raw-request-readback',
    92: 'boot-proof-00 clear cleared',
    96: 'after-status before-status recovery-status-rechecked recovery-status',
    104: 'diagnostic status',
    128: '''after-vcp before-vcp before-sensor-status capture-profile initial-sd
        memory-proof sd-before sdmmc-no-fifo vcp-status-rechecked vcp-status''',
    200: 'before-card completed-card card',
    224: 'clear-status status-00 status-01 status-02',
    384: '''before-proof failed-proof final-proof original-proof-after
        original-proof-before-run original-proof-before original-proof-final
        proof-before-halt proof-before proof-final proof raw-clear raw-clear-readback''',
    416: 'producer',
    512: 'helper-proof-000 helper-proof',
    576: 'before-magic-slots completed-magic-slots',
    640: 'before-slots-mirror completed-slots-mirror',
}.items():
    for name in names.split():
        SIZES[name + '.bin'] = (size,)
SIZES['command.bin'] = (20, 32)
SIZES['fast.bin'] = (2176,)

CODE = {}
def code_names(names, hashes):
    for name in names.split():
        CODE[name + '.bin'] = hashes

code_names('before-code completed-code', {
    'e8f7ad28aa5a2c09d74bc484e5273a8d9c7d705c3c740b3cc00d2f68fd7d5464':26276,
    '2e9295dc14d8acec16a4d5546640e921a81223130b725fbbd30e529179519a91':27232})
code_names('executable-readback', {
    '7c5a6f61bd740875e362745c20f5f4d97710132575441c7bb327a0961ca00598':26280,
    'df1f8c932dda83411c83453991dd2ca5ea758fd154060a3cd92919ff1867cc8d':27080,
    '298aeb4ed4b5bbad9d057a0e18b3ac7396e160b6c56bd43288134a3139c08d14':27236})
code_names('code-0', {'08ec2660bb306afde8f6ca1b9d6ed38145b7dbb1dc00e6eac58929465ae49ef8':15272})
code_names('code-1', {'cc9f07f30ab55b4c1bda498d3c331aaa2b1a82b70e1071b8790ec21ddb581da0':10936})
code_names('original-code-before', {'8bf70853e4888f77252a847b543cb6bcfede82c27499ce02efbde22cdac7a2c0':27076})
code_names('bridge-readback', {'9d0a4553845dbf033264bde3629e2601aac561799cac9e34ed841f32485abdb6':1324})
code_names('helper-after helper-readback recover', {'646eb2d3a1fda15e5c2ab0a8224b47f0992e10c48b188fc0fa37eab45ee60277':1224})
code_names('before-prefix live-prefix', {
    '31b8a97eb8a68e574c1adab17e44b838044277bd95f81f5b22c30b9fdaaccd2e':5140,
    '44c3425ea8e22c06168d8a8d0b65ae7813a0cad147a6d06ad18278f71bd4b9c2':5140,
    'c6991a534d50569562c9d8426cb1d30c3bea20f208878bb81c56356747f41003':5140})
code_names('readback', {
    'f9c6a8935ed7d4aa90f71463f622bdf9261f5c30ba63a4de724cc7c198e45847':65536,
    '2ad7168302fe05b928b2b1aa62ef9732dfeab0d61e6092de2c086412d4485880':65536})
code_names('following-sector', {'01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f':4096})

TAGGED = {}
for tag, names in {
    b'RSW1': '''before-proof failed-proof final-proof original-proof-after
        original-proof-before-run original-proof-before original-proof-final
        proof-before-halt proof-before proof-final proof''',
    b'RGP1': 'after-status before-status recovery-status-rechecked recovery-status',
    b'VPC1': 'after-vcp before-vcp vcp-status-rechecked vcp-status',
    b'RBR1': 'boot-proof-00', b'RCP2':'capture-profile', b'SEN1':'before-sensor-status',
    b'NCP2':'diagnostic', b'SDR1':'helper-proof-000 helper-proof',
    b'R10M':'memory-proof', b'RLD1':'late-loader', b'PRD1':'producer',
    b'RMG1':'magic-proof', b'RSQ1':'raw-request raw-request-readback',
    b'NORD':'command',
}.items():
    for name in names.split():
        # Diagnostic magic values are numeric four-character constants stored
        # as little-endian uint32_t; on-media GXRS/GXRE are different literals.
        TAGGED[name + '.bin'] = (tag[::-1],)
TAGGED['request.bin'] = TAGGED['request-readback.bin'] = (b'1RBR', b'1QDS')
TAGGED['status.bin'] = (b'ENOD',)
for name in ('status-00.bin','status-01.bin','status-02.bin'):
    TAGGED[name] = (b'ENOD', b'NNUR')


def is_metadata_sector(raw):
    return (len(raw) == 512 and raw[:8] in (b'GXRWVOL1', b'GXRAWSL1') and
            int.from_bytes(raw[508:], 'little') == zlib.crc32(raw[:508]))


def is_erased_sector(raw):
    return len(raw) == 512 and raw in (bytes(512), bytes([255]) * 512)


def saleae(name, raw):
    if re.fullmatch(r'digital_[0-7]\.bin', name):
        require(len(raw) >= 44, 'Truncated Saleae digital header')
        magic, version, kind, initial, begin, end, count = struct.unpack_from('<8siiIddQ', raw)
        require(magic == b'<SALEAE>' and version == kind == 0 and initial in (0,1),
                'Unreviewed Saleae digital header')
        require(math.isfinite(begin) and math.isfinite(end) and begin <= end and
                count <= 2_000_000 and len(raw) == 44 + count * 8,
                'Saleae digital extent differs')
        previous = None
        for (value,) in struct.iter_unpack('<d', raw[44:]):
            require(math.isfinite(value) and begin <= value <= end and
                    (previous is None or previous < value), 'Invalid digital transition')
            previous = value
        return 'saleae-digital'
    if name == 'analog_4.bin':
        require(len(raw) >= 48, 'Truncated Saleae analog header')
        magic, version, kind, begin, rate, downsample, count = struct.unpack_from('<8siidQQQ', raw)
        require(magic == b'<SALEAE>' and version == 0 and kind == 1 and
                math.isfinite(begin) and 0 < rate <= 125_000_000 and
                0 < downsample <= rate and count <= 4_000_000 and len(raw) == 48 + 4 * count,
                'Saleae analog header/extent differs')
        require(all(math.isfinite(value) for (value,) in struct.iter_unpack('<f',raw[48:])),
                'Nonfinite analog sample')
        return 'saleae-power-analog'
    return None


def validate_nonpixel_binary(path, raw):
    """Raise for unknown names, wrong sizes or unreviewed byte-bearing content.

    Pixel-sector exceptions are intentionally not inferred here. The caller can
    admit an explicitly listed metadata/erased probe only after the corresponding
    pure is_metadata_sector/is_erased_sector check, with archive provenance.
    """
    name = str(path).replace('\\','/').rsplit('/',1)[-1]
    require(type(raw) is bytes and name.endswith('.bin'), 'Expected binary bytes and .bin name')
    if name in ('slot.bin','frame.bin','payload-padded.bin','snapshots.bin','sectors.bin') or re.fullmatch(r'frame-[0-9a-f]+\.bin',name):
        raise ValueError('Pixel-bearing filename requires explicit separate admission: ' + name)
    kind = saleae(name, raw)
    if kind:
        return dict(kind=kind, bytes=len(raw))
    if name in CODE:
        require(CODE[name].get(hashlib.sha256(raw).hexdigest()) == len(raw),
                'Unreviewed firmware/readback bytes: ' + name)
        return dict(kind='exact-code', bytes=len(raw))
    if name in ('header.bin','volume.bin'):
        require(is_metadata_sector(raw), 'Legacy metadata CRC/magic differs')
        return dict(kind='legacy-metadata', bytes=len(raw))
    if name in ('leading-magic.bin','trailing-magic.bin'):
        require(raw == (b'GXRS' if name.startswith('leading') else b'GXRE'), 'Slot marker differs')
    elif name == 'frame-padding.bin':
        require(len(raw) in (152,160) and not any(raw), 'Nonzero/invalid frame padding')
    else:
        require(name in SIZES and len(raw) in SIZES[name], 'Unknown binary name or extent: ' + name)
        if name in TAGGED:
            require(raw[:4] in TAGGED[name], 'Diagnostic record tag differs: ' + name)
        if name in ('clear-status.bin','clear.bin','cleared.bin','raw-clear.bin','raw-clear-readback.bin'):
            require(not any(raw), 'Clear buffer contains data')
        if name == 'frame-guard.bin':
            require(raw == struct.pack('<8I', *(0xA15A1000+i for i in range(8))), 'Frame guard differs')
        if name.endswith('magic-slots.bin'):
            require(is_erased_sector(raw[64:]), 'Magic slots scan buffer contains unclassified data')
        if name.endswith('slots-mirror.bin'):
            require(is_erased_sector(raw[128:]) or is_metadata_sector(raw[128:]),
                    'Legacy slots I/O buffer contains unclassified data')
    return dict(kind='bounded-diagnostic', bytes=len(raw))
