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
VCP_ADDRESS = 0x341F7080
VCP_FIELDS = (
    'magic schema words pin nominal_hz window_cycles baud min_low max_low '
    'min_high max_high required first_cycle last_cycle edges good_pulses '
    'bad_pulses max_train last_low last_high request request_cycle initial_level '
    'final_level source_bits polls reserved26 reserved27 reserved28 reserved29 '
    'reserved30 reserved31').split()
# An unknown/self-consistent build is insufficient authorization to halt.
APPROVED = {
    # v66c normal Standby accepts the current SAVE profile at the late loader.
    # The exact early recovery bytes/literals remain unchanged.
    '247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'},
    # v64 normal awake; relocated RCP2 is clear of the complete LED proof.
    '58dbd958018a2e55de8bb49807a90a3875c643f605a68e053b77979f86332107':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '6823ef327e6625d26877aa5d3a9b09353b52556434f41fc8d736e64bad508cc7'},
    # v65 normal Standby; same exact early guard/literals as v64/v59.
    '6f07ee096565b43a8d5c1f09a0dc28e300599667bda4b025868cb278288baefb':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '409628f664b41b39b8a6397d9098a7bd3420d23c9d8441538e11e59ae9ee593c'},
    # v62b normal awake retains original CSI error-history snapshots.
    # Reviewed early guard/literals; approval is not hardware qualification.
    'e03eee01bfde90acfc1bb9466c12f2568ebf3d5890695f0ed4bdbfa5776a03f4':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'ae732240a491e4cba5e5ce408e43f56ee1ed99c33fe8008b2848c0ff6c98118d'},
    # v62 normal-profile awake qualification; all early guard bytes/literals
    # match the qualified guard. Exact approval is not hardware qualification.
    'e754f7cf914fd64cb8a34486ef5e466ece5e00108ad3fed7325aefa3075ea746':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'ec2c2ae7855a85aadf658078f8a44c12735ce82a1820883b1ef27a6b59363163'},
    # v60c awake / v61b Standby PD12 timing overlays, independently reviewed.
    # Exact early guard/literals are unchanged; hardware timing is unqualified.
    'e14913fa5c47f9d03e6680ca3ab8499afee0bf73f6654ef7d892c7303fa0ba42':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e'},
    '73ec49d0f6b011ca615813886709d429e9dd8e5604af04b5d03447ef5ca7b51e':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f'},
    # v57/v58/v59 qualify nCS after GPIO takeover; all earlier guards retained.
    '67278231209a8eec1201d1b596cc862a41a288c237a3c2214ec3834c56995d23':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '44ea4f525d965e5b01a5178e4bb12e332f88184be2896e8c412e6ae13fc6caeb'},
    '34e5ef66662471b1d98f453d3ec33b9e9f60511970dc263e6db875924785d940':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '758d5bd20b48282983f434a647aedf46d2561f4732d0ce8fb01dc4dfd883b4e3'},
    '9a6c498a94c9415ec3dc39933bae2e958ceb0a43b53a1b2c8b931ef26475d071':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63'},
    # v55d Stop and v56d Standby; same reviewed early guard and v8b writer.
    '35f0540ac1254ef7afeadb2afe53df305588ad954249bf3b5e51f4e31cd3e9f4':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '26c8bbaffe917f2b222dc65ce0e9ccc21310ccc6175ca217b90c3e772e7138c7'},
    'e9e16460d775e697aa8acf7ea13680b5fd00ba91707008aff2fdfc1ea483da41':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'adfb2e736f58fb2ebb838db5aadab2f63c9a25522dafdcd1ce64f89e6d3cec1f'},
    # v54d late-loaded peripheral-off trial, unchanged v8b save module.
    '3476b99d2ad9c32fdbe40f9f7c2bceb1c8075fa44b86ddeb75fc7a5751833c2a':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'bfdf657721b96fecfaabd037b28dcecd57350e9be2f46934b2c0dd666945d82c'},
    # v51b terminal peripheral-off trial; same early guard/literals as v50.
    # Receiver length and storage-module offset were independently checked.
    '3d39b1d481469d2013c8d25e796c96ef67e6439ac5455ce90c61c86137ae95e5':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': 'fd729d9609c74c22c0fbedc63b49d388e2f75b47c47ba4650e687a5188a295f5'},
    # v50 capture/PNG/SD awake integration; reviewed exact v8b storage module.
    # Early guard and all referenced literals match the v45b/v46 baseline.
    '8a65df7b36a0c9a0c80e25c4a1000d4bae914ce9d3a46e5ff83e5454cdf109f7':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '9ffc2c1cbaacf9f60258343ac6a061b35fb62f8b62b42c1a5b50ccc5f432f5cd'},
    # v46 offline-reviewed awake completion: two receiver bytes differ from v45b;
    # the entire early recovery branch is byte-identical. Not hardware-qualified.
    'da664e5425574d6130e995513a70169b7a3dd7397ed8c86a8acf5ce651ab8ea7':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '3f64bb86b73c44ba403a2a150f058eb0daf661c4b1ac41e6ca4634073bdd7cae'},
    # v45b additive PE6 pulse detector; independently reviewed offline.
    # Exact binary approval is not hardware qualification.
    'a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a':
        {'bytes': 5140, 'park': 0x3418078C, 'vcp': True,
         'sector': '2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2'},
    # v44 phase LEDs: reviewed masked GPIO setup before the unchanged guard.
    # Exact binary approval enables validation; it is not hardware qualification.
    '875d665e050aa2c20e59843c382130d2029035a478230a39f15892ce543c90c6':
        {'bytes': 4652, 'park': 0x3418078C,
         'sector': 'a325b36ed6d3f893ebe0d1153f476fd06fc51c648a1fe55aac15d353c959b4d8'},
    # v43 lane1/PEN+200us timing discriminator, reviewed complete guard.
    '7e4d6d6249c501d963c5f9f421a3f50e1573410c869bb27d726b96a6f1acde31':
        {'bytes': 4436, 'park': 0x3418078C,
         'sector': '8793d0718f1a0d83833a61e6c32dfc4ae60114c8040da67b1f0dfbee21fdd9ac'},
    # v41 default exposure, byte-identical lane1 receiver and recovery guard.
    '0886559c3e4b5ddd358eb25a4f0c4ad4b40f588839c089a0fe1320675e28abce':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': 'c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f'},
    # v42 bothForce/STOP0 discriminator, same recovery guard and error policy.
    '8d21e1c02f56d3255f6d7bf6adeede84682cc04ebbb9dea391185fd1efc182bd':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '26fc78fec73bdf3831cfdc55c2369b03f7a87ad746bc08c6a60593becc74179c'},
    # v41 lane1-only ForceRx; complete0x658 guard and park unchanged.
    '5079100595a19d8fc4a5b949cc231a9bafdab48029e361ac7b47acdf80b323f2':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '15eb8aceed6834090e5223c7e70dd3b4bb8a2e9278655eda1917f63db6a7bc0f'},
    # v39 ForceRx retained through100us observed Stop, same complete guard.
    'a9a8e95e1415caf85138e893fb1e821ed0297777b669e9c95cf61382224c165b':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': 'acf73e0184d2336e3ed7dfb066337a64970a0686921c7d053687afe73ca47328'},
    # v39 matched EARLY/STOP control, with reviewed0x658 recovery invariant.
    '97ee75d0fd62ed4ae776fc74cd91b43990d6d2cd28620a90b5bfba23fda4ca03':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '843e910792e7c0d2c93f16700abdcaeeda8e245402bd913d3b3effa9d923a737'},
    # v38b: same ACK receiver, default exposure; exact recovery guard unchanged.
    '24616bf20b08df1032bc976a200ba3f98076f0eead70e8c18c1d04642502483c':
        {'bytes': 4436, 'park': 0x3418078C,
         'sector': '439dcafc0fc615a4c0589ef06aa4295c73a879e8e3277bf1a849d12054c0ea81'},
    # v38a: ACK gate; complete recovery code/literals through0x658 unchanged.
    '1654c04b078259f6e429df5355b0e67efaf105d2a377d8ac76c3f418e1b83694':
        {'bytes': 4436, 'park': 0x3418078C,
         'sector': '72e869b41373774dd7ace8cfbb3e190f230eefc346e3c3332143cbfa658e2260'},
    # v37: v36 minimum exposure, only continuous STOP dwell changed.
    '073090134af441dcd2f3f3e6dcc0d417d67cb5ea8d55c7df56b5dacc4299b543':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': 'd11513f667e23603688d82925eb4f312cb5435c79c730fd17c1bc54810f7c206'},
    '6f9fe85fabf23cecabbb36fdfb8d5f6e3a0fda5f6e9173438984168e8e316801':
        {'bytes': 4432, 'park': 0x3418078C,
         'sector': '0e0ded7ec903034aa5d8200f6f838a9026d2e8f1fdc32fac94ab11be4e727266'},
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
    if approved.get('vcp'):
        vcp = manifest.get('recovery_vcp', {})
        expected_vcp = dict(
            schema=1, pin='PE6', internal_pull='up',
            status_address=hex(VCP_ADDRESS), status_words=32, status_fields=VCP_FIELDS,
            published_status_address='0x343f7080', baud=1000000,
            min_low_cycles=2400, max_low_cycles=5200,
            min_high_cycles=100, max_high_cycles=1600, required_pulses=3,
            window_cycles=40000, nominal_clock_hz=400000000)
        if any(vcp.get(k) != v for k, v in expected_vcp.items()):
            raise ValueError('VCP layout differs from reviewed schema')
    offset = approved['park']-PREFIX_ADDRESS
    if code[offset:offset+2] != bytes.fromhex('fee7'):
        raise ValueError('Recovery park instruction differs')
    return code, approved


def validate_status(words, vcp=False):
    if len(words) != len(FIELDS):
        raise ValueError('Incomplete recovery status')
    s = dict(zip(FIELDS, words))
    expected = dict(magic=0x52475031, schema=1, words=24, state=3, reason=1,
                    pin=0x40001, nominal_hz=400000000, settle_cycles=40000,
                    control=0, ipsr=0, primask=1, dbgcr=0xB451B400, ap_unlock=0xB4)
    if any(s[k] != v for k, v in expected.items()):
        raise ValueError('Not a requested early recovery park')
    if (s['moder'] & 12 or s['pupdr'] & 12 != 4 or
            s['elapsed_cycles'] < 40000 or not 0 <= s['polls'] < 100000 or
            (s['sample_cycle']-s['begin_cycle']) & 0xFFFFFFFF != s['elapsed_cycles'] or
            not s['ahb4enr'] & (1 << 4) or not s['demcr'] & (1 << 24) or
            not s['dwt_ctrl'] & 1 or s['dwt_ctrl'] & (1 << 25)):
        raise ValueError('Pin, settling, or timer evidence is inconsistent')
    if vcp:
        if (s['reserved'] not in (1, 2, 3) or
                bool(s['reserved'] & 1) != (not bool(s['idr'] & 2)) or
                s['moder'] & 0x3000 or s['pupdr'] & 0x3000 != 0x1000):
            raise ValueError('PE1/PE6 source or GPIO configuration is inconsistent')
    elif s['idr'] & 2:
        raise ValueError('PE1 did not request recovery')
    return s


def validate_vcp_status(words, guard):
    if len(words) != len(VCP_FIELDS):
        raise ValueError('Incomplete VCP proof')
    s = dict(zip(VCP_FIELDS, words))
    expected = dict(magic=0x56504331, schema=1, words=32, pin=0x40006,
                    nominal_hz=400000000, window_cycles=40000, baud=1000000,
                    min_low=2400, max_low=5200, min_high=100, max_high=1600,
                    required=3, last_cycle=guard['sample_cycle'],
                    source_bits=guard['reserved'], polls=guard['polls'],
                    final_level=int(bool(guard['idr'] & 64)))
    if (any(s[k] != v for k, v in expected.items()) or
            any(s[f'reserved{i}'] for i in range(26, 32)) or
            s['initial_level'] not in (0, 1) or
            s['request'] != int(bool(guard['reserved'] & 2)) or
            s['good_pulses'] + s['bad_pulses'] > s['edges'] // 2 or
            s['max_train'] > s['good_pulses'] or
            s['edges'] > s['polls']):
        raise ValueError('VCP proof disagrees with the requested park')
    first = (s['first_cycle'] - guard['begin_cycle']) & 0xFFFFFFFF
    if first > guard['elapsed_cycles']:
        raise ValueError('VCP observation starts outside the guard interval')
    if s['request']:
        request = (s['request_cycle'] - guard['begin_cycle']) & 0xFFFFFFFF
        if (s['max_train'] < 3 or s['good_pulses'] < 3 or s['edges'] < 6 or
                not first < request < 40000 or request - first < 7400):
            raise ValueError('No qualified pulse train within the startup deadline')
    elif s['request_cycle'] or s['max_train'] >= 3:
        raise ValueError('VCP request flag disagrees with pulse evidence')
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
    is_vcp = approved.get('vcp', False)
    status = validate_status(struct.unpack('<24I', b.upload(
        STATUS_ADDRESS, 96, 'recovery-status.bin')), vcp=is_vcp)
    vcp_status = validate_vcp_status(struct.unpack('<32I', b.upload(
        VCP_ADDRESS, 128, 'vcp-status.bin')), status) if is_vcp else None
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
    after = validate_status(struct.unpack('<24I', b.upload(
        STATUS_ADDRESS, 96, 'recovery-status-rechecked.bin')), vcp=is_vcp)
    if after != status:
        raise ValueError('Recovery status changed while validating park')
    if is_vcp:
        vcp_after = validate_vcp_status(struct.unpack('<32I', b.upload(
            VCP_ADDRESS, 128, 'vcp-status-rechecked.bin')), after)
        if vcp_after != vcp_status:
            raise ValueError('VCP proof changed while validating park')
    result = dict(passed=True, status=status, context=context, ccr=ccr, fpccr=fpccr,
                  prefix_sha256=sha(code), xspi_sr=sr, halt_requested=True,
                  park_context_observed_in_halt_command=True,
                  persistent_halt_after_disconnect='not_guaranteed',
                  post_disconnect_execution='may resume the exact verified branch-to-self park',
                  ram_writes=False, nor_commands=False,
                  next_step='Reviewed low-SRAM nor_bench INFO, then separately guarded WRITE',
                  vcp_status=vcp_status)
    (a.out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
