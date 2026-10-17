"""Verify an exact early recovery park before low-SRAM NOR maintenance.

Reads RAM/registers and halts only after parked-status and live-code checks.
Never writes RAM, runs a helper, sends NOR commands, resets, or changes power.
The normal post-capture high-SRAM cache helper is not applicable here.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prepare_maintenance import registers
from bench import sha
from nor_bench import Bench

PREFIX_ADDRESS = 0x34180400
STATUS_ADDRESS = 0x341F7000
FIELDS = ('magic schema words state reason pin nominal_hz settle_cycles '
          'begin_cycle sample_cycle elapsed_cycles polls idr moder pupdr '
          'ahb4enr demcr dwt_ctrl control ipsr primask dbgcr ap_unlock reserved').split()
# An unknown/self-consistent build is insufficient authorization to halt.
APPROVED = {
    # v36: reviewed v34c recovery code, STREAMING enable and idle-gated shutdown.
    '976f5d4b0fe93243594e00d046e7ec9503f2b862973e64a226567558d71d1894':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '40743205503bdb465d0549b7764f1590c48b7aaac621bf096aa4b9618957c1bd'},
    '4ca979732ed3bb956522d53c25a16c30343bb1c600f16404cec4fa23ef52460f':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '7c99395b5a23e063e3c6e7b6ce06b9abf041f3736a004dcd4fc6bf275dcccc6b'},
    # v35 matched early control, five coarse lines; only exposure bytes differ.
    '078727c2406d1e3b5b0dd5a580cdab51c6979762644e6e208088c6963d9707c0':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '288e3d5b93d05d5e58a2d3f25e80c27e9badaacf08d5886769316a331b0b3bd7'},
    # v35 STREAMING, supported CCA coarse exposure 5 lines.
    'd35be46b35bebc67ac29dca60b0e39c54912c07eb646d1a3365a662ea228a535':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': 'b58dcb8d957ea26f6daa0467688b45aac74429b9a864ba0af866e3ce6b7cbc88'},
    # v35 STREAMING, supported CCA coarse exposure 21 lines.
    '4642c9a43fc156b3bb2f87e0275e1328f0dbae70c6d7328ded382e2554fb7e0f':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '578f86548711ee4725430ca4807d7bdfbb07a15cf520eba9d46d041c547fa4cb'},
    # v35 STREAMING, supported CCA coarse exposure 40 lines.
    '95e975d362cce315d240f3c76c93002abd8456d1209f8846ac45881fc52b7274':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '24079baafe08013bd6c4b5a8d092d2c3f4d61e9d5a5dfd4a9399ee3cd5632008'},
    # v35 matched early/STREAMING data-lane experiments. The first 0x830
    # prefix bytes, including the complete recovery branch, match v34c.
    '999494ada3b856acee37b24e09150e16c14717325d7840ca0b3f81b2e4b9f327':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': 'de30f24ffbc992a485f5e250c8fc25bc214d309082eb1a83b82e5c845daf6cdb'},
    '36c59eaff9d950b021eabed9ff132c114902830faa2dc7a21979715d246d633e':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '6a4e45dd95c1b226499fe980065736254d812dbdf62e6e87c9abeecca7188764'},
    '528bd09755a2de84d0eadf497015facebe21da680d502fdbf494bcf7ef4e106f':
        {'bytes': 4400, 'park': 0x3418078C,
         'sector': '570657ab294bac79e47c90113c45ef4b2e71f986ab3a1f1cd52fc9895b0fa009'},
    'b22939a1b6c2d30a18043c4c7cfc7f6ac63e53ea15acd9368bf2e1039bc73abe':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '14b6015e0c5705ce5bde655470977851e32cce01fa0164ccda163b892dca3222'},
}


def checked_build(build):
    manifest = json.loads((build/'manifest.json').read_text())
    code = (build/'stage1.bin').read_bytes()
    approved = APPROVED.get(sha(code))
    if not approved or len(code) != approved['bytes']:
        raise ValueError('Recovery prefix is not in the reviewed allowlist')
    if manifest.get('stage1_raw_sha256') != sha(code):
        raise ValueError('Prefix differs from manifest')
    if (manifest.get('program_sha256') != approved['sector'] or
            sha((build/'capture_sector_0.bin').read_bytes()) != approved['sector']):
        raise ValueError('Unreviewed recovery sector')
    spec = manifest.get('recovery_gpio', {})
    expected = dict(status_address=hex(STATUS_ADDRESS), status_words=len(FIELDS),
                    status_fields=FIELDS, park_address=hex(approved['park']),
                    park_bytes='fee7', settle_cycles=40000, max_polls=100000,
                    pin='PE1', active_low=True, internal_pull='up')
    if any(spec.get(k) != v for k, v in expected.items()):
        raise ValueError('Recovery layout differs from reviewed schema')
    offset = approved['park']-PREFIX_ADDRESS
    if code[offset:offset+2] != bytes.fromhex('fee7'):
        raise ValueError('Recovery park instruction differs')
    return code, approved


def validate_status(words):
    if len(words) != len(FIELDS):
        raise ValueError('Incomplete recovery status')
    s = dict(zip(FIELDS, words))
    expected = dict(magic=0x52475031, schema=1, words=24, state=3, reason=1,
                    pin=0x40001, nominal_hz=400000000, settle_cycles=40000,
                    control=0, ipsr=0, primask=1, dbgcr=0xB451B400, ap_unlock=0xB4)
    if any(s[k] != v for k, v in expected.items()):
        raise ValueError('Not a requested early recovery park')
    if (s['idr'] & 2 or s['moder'] & 12 or s['pupdr'] & 12 != 4 or
            s['elapsed_cycles'] < 40000 or not 0 <= s['polls'] < 100000 or
            (s['sample_cycle']-s['begin_cycle']) & 0xFFFFFFFF != s['elapsed_cycles'] or
            not s['ahb4enr'] & (1 << 4) or not s['demcr'] & (1 << 24) or
            not s['dwt_ctrl'] & 1 or s['dwt_ctrl'] & (1 << 25)):
        raise ValueError('Pin, settling, or timer evidence is inconsistent')
    return s


def validate_context(context, park, ccr, fpccr):
    if (context.get('PC') != park or context.get('CONTROL') != 0 or
            context.get('PRIMASK') != 1 or context.get('FAULTMASK') != 0 or
            context.get('XPSR', 511) & 511 or
            not context.get('XPSR', 0) & (1 << 24) or
            ccr & 0x30000 or fpccr & 1):
        raise ValueError('Not the reviewed awake, uncached, integer-only recovery context')


def validate_xspi_clock(enabled, reset):
    if enabled & 0x2020 != 0x2020 or reset & 0x2020:
        raise ValueError('Do not read unclocked or reset XSPI/XSPIM')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    code, approved = checked_build(a.build)
    b = Bench(a.out)
    status = validate_status(struct.unpack('<24I', b.upload(STATUS_ADDRESS, 96, 'recovery-status.bin')))
    if b.upload(PREFIX_ADDRESS, len(code), 'live-prefix.bin') != code:
        raise ValueError('Live prefix differs; no halt or maintenance authorized')
    context = registers(b.call('-halt', '-coreReg'))
    def word(address, name):
        return struct.unpack('<I', b.upload(address, 4, name+'.bin'))[0]
    ccr, fpccr = word(0xE000ED14, 'ccr'), word(0xE000EF34, 'fpccr')
    validate_context(context, approved['park'], ccr, fpccr)
    enabled, reset = word(0x56028260, 'ahb5enr'), word(0x56028220, 'ahb5rstr')
    validate_xspi_clock(enabled, reset)
    sr = word(0x58025020, 'xspi-sr')
    if sr & 0x7F20:  # FLEVEL[14:8] or BUSY[5]. No transaction is initiated.
        raise ValueError('XSPI controller is not idle with empty FIFO')
    # CLI disconnect can resume this exact branch-to-self park. Recheck its
    # stable record; no persistent halt or cache helper is assumed here.
    after = validate_status(struct.unpack('<24I', b.upload(STATUS_ADDRESS, 96, 'recovery-status-rechecked.bin')))
    if after != status:
        raise ValueError('Recovery status changed while validating park')
    result = dict(passed=True, status=status, context=context, ccr=ccr, fpccr=fpccr,
                  prefix_sha256=sha(code), xspi_sr=sr, halt_requested=True,
                  park_context_observed_in_halt_command=True,
                  persistent_halt_after_disconnect='not_guaranteed',
                  post_disconnect_execution='may resume the exact verified branch-to-self park',
                  ram_writes=False, nor_commands=False,
                  next_step='Reviewed low-SRAM nor_bench INFO, then separately guarded WRITE')
    (a.out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
