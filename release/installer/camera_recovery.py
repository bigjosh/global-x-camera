"""Portable entry and exact verification of this camera's early UART park.

Importing this module does not enumerate devices or access hardware. Recovery
requires the existing reviewed FLASH guard; it cannot repair a missing guard or
corrupt boot header. The caller must establish stable power and completed
storage work before requesting a reset. No automatic retries are performed.

BREAK driving NRST is observed behavior of this prototype's ST-LINK firmware,
not a general UART feature. The byte train and a successful serial write alone
are not proof of entry: always call verify_park before loading a RAM helper.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import threading
import time


VID, PID = 0x0483, 0x3754
PREFIX_ADDRESS = 0x34180400
STATUS_ADDRESS = 0x341F7000
VCP_ADDRESS = 0x341F7080
PARK_ADDRESS = 0x3418078C
FIELDS = (
    'magic schema words state reason pin nominal_hz settle_cycles '
    'begin_cycle sample_cycle elapsed_cycles polls idr moder pupdr '
    'ahb4enr demcr dwt_ctrl control ipsr primask dbgcr ap_unlock reserved'
).split()
VCP_FIELDS = (
    'magic schema words pin nominal_hz window_cycles baud min_low max_low '
    'min_high max_high required first_cycle last_cycle edges good_pulses '
    'bad_pulses max_train last_low last_high request request_cycle initial_level '
    'final_level source_bits polls reserved26 reserved27 reserved28 reserved29 '
    'reserved30 reserved31'
).split()

# Independently reviewed input tuples. A self-consistent profiles.json alone
# must never authorize a halt or flash operation. Adding an image needs review.
APPROVED = {
    'b1b032c7ae48e68a8942922b9a6a2d8e57983030a331b1d5b590c01ee3571c52': {
        'prefix_bytes': 7164,
        'sector0_sha256': '1a9278ab1733134a86e382af61b3a78627fe40d82e9e137dd33f2bfcf8de1197',
        'sector1_sha256': 'ed6d416974bf0801f1b1daa6e29520db06fa3294bb33060a9dfbc48b761fbc38',
    },
    'b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242': {
        'prefix_bytes': 7160,
        'sector0_sha256': '6ddf4499865264aec845150597aa6b8d44cb89e7d5e621dd324a0e1a9170b499',
        'sector1_sha256': '206da4c0a8bdcda6205d7ccdb3d9ac02548e9db6852b1fa47afa6327b76473d8',
    },
}


def discover_serial_ports(ports=None):
    """List only this ST-LINK V3EC's VID/PID; no serial port is opened."""
    if ports is None:
        from serial.tools import list_ports
        ports = list_ports.comports()
    return [p for p in ports if p.vid == VID and p.pid == PID]


def select_serial_port(serial_number, explicit_port=None, ports=None):
    """Bind the UART to the full serial of the selected ST-LINK debugger.

    Prefer macOS callout devices when a driver exposes both cu/tty aliases.
    An explicit port does not waive USB identity or ambiguity checks.
    """
    if not isinstance(serial_number, str) or not serial_number:
        raise ValueError('A full ST-LINK serial number is required')
    candidates = [p for p in discover_serial_ports(ports)
                  if p.serial_number == serial_number]
    if explicit_port is not None:
        candidates = [p for p in candidates if p.device == str(explicit_port)]
    else:
        # Discard only an actual tty alias of a matching cu device, not an
        # unrelated second serial interface belonging to the same debugger.
        devices = {p.device for p in candidates}
        candidates = [p for p in candidates
                      if not (p.device.startswith('/dev/tty.') and
                              '/dev/cu.' + p.device[len('/dev/tty.'):] in devices)]
    if len(candidates) != 1:
        raise RuntimeError('Expected one matching ST-LINK UART; found '
                           f'{len(candidates)}. Select its exact port/serial.')
    return candidates[0].device


def _serial(port):
    import serial
    uart = serial.Serial()
    uart.port = str(port)
    uart.baudrate = 1_000_000
    uart.bytesize = serial.EIGHTBITS
    uart.parity = serial.PARITY_NONE
    uart.stopbits = serial.STOPBITS_ONE
    uart.timeout = 0.5
    uart.write_timeout = 2
    uart.rts = False
    uart.dtr = False
    uart.xonxoff = uart.rtscts = uart.dsrdtr = False
    return uart


def _close_serial(uart, log, worker=None):
    """Release reset and close even after a partial send or host exception."""
    failures = []
    if uart.is_open:
        # Do not send a CDC BREAK control request for the power-on-only path.
        # pyserial tracks its requested BREAK state; if asserting it failed
        # partway, that state is still True and cleanup attempts release.
        actions = []
        if uart.break_condition:
            actions.append(lambda: setattr(uart, 'break_condition', False))
        actions.append(uart.cancel_write)
        for action in actions:
            try:
                action()
            except Exception as exc:
                failures.append(repr(exc))
        if worker is not None:
            worker.join(3)
            if worker.is_alive():
                failures.append('UART sender did not stop after cancellation')
        for action in (uart.reset_output_buffer, uart.close):
            try:
                action()
            except Exception as exc:
                failures.append(repr(exc))
    log('uart_closed', cleanup_errors=failures)
    if failures:
        raise RuntimeError('UART cleanup failed; reset/port state needs checking: '
                           + '; '.join(failures))


class RecoveryStream:
    """Keep C0 data queued while the operator powers the target on.

    Opening this context sends no BREAK or reset. check() surfaces sender
    failures/deadline expiry while the caller polls exact recovery evidence.
    Exit this context before starting any flash operation. It owns only the
    selected serial port, not target power or the debugger transport.
    """
    def __init__(self, port, log, max_duration=120):
        if not math.isfinite(max_duration) or max_duration <= 0:
            raise ValueError('Recovery stream duration must be positive and finite')
        self.port, self.log, self.max_duration = port, log, max_duration
        self.uart = None
        self.worker = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error = None
        self._expired = False
        self._closed = False
        self.bytes_written = 0

    def __enter__(self):
        if self.uart is not None:
            raise RuntimeError('A recovery stream cannot be opened twice')
        self.uart = _serial(self.port)
        try:
            self.uart.open()
            self.deadline = time.monotonic() + self.max_duration
            self.log('uart_power_on_stream_started', port=str(self.port),
                     baud=1_000_000, pattern='c0', reset_sent=False,
                     max_duration=self.max_duration)
            self.worker = threading.Thread(target=self._send,
                                           name='camera-power-on-uart', daemon=True)
            self.worker.start()
            if not self._ready.wait(3):
                raise TimeoutError('Initial UART recovery train was not queued within 3 seconds')
            self.check()
            self.log('uart_power_on_stream_armed', bytes_written=self.bytes_written,
                     reset_sent=False)
            return self
        except BaseException:
            self._stop.set()
            try:
                _close_serial(self.uart, self.log, self.worker)
            finally:
                self._closed = True
            raise

    def _send(self):
        try:
            while not self._stop.is_set():
                if time.monotonic() >= self.deadline:
                    self._expired = True
                    return
                count = self.uart.write(b'\xc0' * 32768)
                self.bytes_written += count or 0
                if self._stop.is_set():
                    return  # cancel_write can intentionally return a short send
                if count != 32768:
                    raise RuntimeError(f'Partial UART write: {count} of 32768 bytes')
                # A successful OS/USB queue write is stronger than thread
                # startup, but is still not proof of the physical waveform.
                self._ready.set()
        except Exception as exc:
            if not self._stop.is_set():
                self._error = exc
        finally:
            # Wake __enter__ immediately on error/expiry as well as success;
            # its check() distinguishes those outcomes before claiming armed.
            self._ready.set()

    def check(self):
        if self.uart is None or self.worker is None or self._closed:
            raise RuntimeError('Recovery stream is not open')
        if self._error is not None:
            raise RuntimeError('UART recovery stream failed') from self._error
        if self._expired or time.monotonic() >= self.deadline:
            raise TimeoutError('Recovery power-on window expired; no reset was sent')
        if not self.worker.is_alive() and not self._stop.is_set():
            raise RuntimeError('UART recovery stream stopped unexpectedly')

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        try:
            _close_serial(self.uart, self.log, self.worker)
        finally:
            self._closed = True
        self.log('uart_power_on_stream_stopped', bytes_written=self.bytes_written,
                 reset_sent=False)
        return False


def request_recovery(port, log, wait_for_power=0):
    """Send one measured C0/BREAK request; verification is a separate step.

    Uses a queued 32768-byte train so UART data spans the BREAK-controlled
    reset release. No reset, helper reload or write retry follows failure.
    """
    if not math.isfinite(wait_for_power) or wait_for_power < 0:
        raise ValueError('Power-on wait must be nonnegative and finite')
    if wait_for_power:
        with RecoveryStream(port, log, max_duration=wait_for_power + 1) as stream:
            deadline = time.monotonic() + wait_for_power
            while time.monotonic() < deadline:
                stream.check()
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            stream.check()
            log('uart_power_on_wait_complete', bytes_written=stream.bytes_written,
                seconds=wait_for_power, reset_sent=False)
        return
    uart = _serial(port)
    result = {}
    worker = None

    def send():
        try:
            result['written'] = uart.write(b'\xc0' * 32768)
        except Exception as exc:
            result['error'] = repr(exc)

    try:
        uart.open()
        log('uart_opened', port=str(port), baud=1_000_000, pattern='c0')
        time.sleep(0.3)
        worker = threading.Thread(target=send, name='camera-recovery-uart', daemon=True)
        worker.start()
        time.sleep(0.023)
        if 'error' in result or ('written' in result and result['written'] != 32768):
            raise RuntimeError(f'UART stimulus failed before reset: {result}')
        uart.break_condition = True
        log('break_on')
        time.sleep(0.1)
        uart.break_condition = False
        log('break_off')
        worker.join(3)
        if worker.is_alive() or result.get('written') != 32768 or 'error' in result:
            raise RuntimeError(f'Incomplete UART recovery stimulus: {result}')
        time.sleep(0.75)
        log('uart_stimulus_complete', **result)
    finally:
        _close_serial(uart, log, worker)


def normal_reset(port, log):
    """Release a powered normal reset, without sending recovery bytes.

    Caller must first prove all NOR/SD work complete. This does not switch power
    and can start a photo capture when target USB VBUS is absent.
    """
    uart = _serial(port)
    try:
        uart.open()
        uart.reset_output_buffer()
        log('uart_opened_no_recovery_train', port=str(port))
        uart.break_condition = True
        log('break_on')
        time.sleep(0.1)
        uart.break_condition = False
        log('break_off_normal_reset_release')
    finally:
        _close_serial(uart, log)


def load_profiles(profiles_dir):
    """Validate offline metadata and exact prefix bytes before any transport."""
    root = Path(profiles_dir).resolve()
    document = json.loads((root / 'profiles.json').read_text(encoding='utf-8'))
    if document.get('schema') != 1 or not isinstance(document.get('profiles'), list):
        raise ValueError('Unsupported recovery profiles schema')
    profiles = document['profiles']
    if not profiles:
        raise ValueError('No reviewed recovery profiles supplied')
    seen_ids, seen_hashes = set(), set()
    result = []
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError('Malformed recovery profile')
        identity = profile.get('id')
        digest = profile.get('prefix_sha256')
        approved = APPROVED.get(digest)
        if (not isinstance(identity, str) or not identity or identity in seen_ids or
                digest in seen_hashes or approved is None or
                any(profile.get(k) != v for k, v in approved.items())):
            raise ValueError('Recovery profile is not an exact reviewed image')
        filename = profile.get('prefix_file')
        if not isinstance(filename, str) or Path(filename).is_absolute():
            raise ValueError('Recovery prefix path must be relative to profiles')
        path = (root / filename).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError('Recovery prefix escapes the profiles directory') from exc
        code = path.read_bytes()
        if (len(code) != approved['prefix_bytes'] or
                hashlib.sha256(code).hexdigest() != digest or
                code[PARK_ADDRESS-PREFIX_ADDRESS:PARK_ADDRESS-PREFIX_ADDRESS+2] != b'\xfe\xe7'):
            raise ValueError('Recovery prefix bytes differ from the reviewed image')
        seen_ids.add(identity)
        seen_hashes.add(digest)
        result.append((dict(profile), code))
    return result


def validate_status(words):
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
    if (s['reserved'] not in (1, 2, 3) or
            bool(s['reserved'] & 1) != (not bool(s['idr'] & 2)) or
            s['moder'] & 0x3000 or s['pupdr'] & 0x3000 != 0x1000):
        raise ValueError('PE1/PE6 source or GPIO configuration is inconsistent')
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
            s['max_train'] > s['good_pulses'] or s['edges'] > s['polls']):
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


def validate_context(context, ccr, fpccr):
    if (context.get('PC') != PARK_ADDRESS or context.get('CONTROL') != 0 or
            context.get('PRIMASK') != 1 or context.get('FAULTMASK') != 0 or
            context.get('XPSR', 511) & 511 or
            not context.get('XPSR', 0) & (1 << 24) or
            ccr & 0x30000 or fpccr & 1):
        raise ValueError('Not the reviewed awake, uncached, integer-only recovery context')


def verify_park(transport, profiles_dir):
    """Identify an exact reviewed prefix and prove its early maintenance state.

    No RAM writes, reset, power changes, standard external loader or NOR
    commands occur here. The halt is issued only after prefix/status checks.
    Return identifies the prefix; caller must separately read and compare both
    complete NOR sectors before programming. RAM prefix proof is not that proof.
    """
    profiles = load_profiles(profiles_dir)

    def words(address, count, label):
        data = transport.upload(address, count * 4, label)
        if len(data) != count * 4:
            raise ValueError(f'Incomplete {label}')
        return struct.unpack('<' + 'I' * count, data)

    status = validate_status(words(STATUS_ADDRESS, 24, 'recovery-status'))
    vcp = validate_vcp_status(words(VCP_ADDRESS, 32, 'vcp-status'), status)
    # This installer enters through UART, so require that source even if a
    # separately asserted PE1 pin could also select the same reviewed park.
    if not vcp['request']:
        raise ValueError('No observed UART recovery request; no halt authorized')
    maximum = max(len(code) for _, code in profiles)
    live = transport.upload(PREFIX_ADDRESS, maximum, 'live-prefix')
    if len(live) != maximum:
        raise ValueError('Incomplete live prefix')
    matches = [(p, code) for p, code in profiles if live[:len(code)] == code]
    if len(matches) != 1:
        raise ValueError('Live prefix is not one reviewed image; no halt authorized')
    profile, _ = matches[0]
    text = transport.call('-halt', '-coreReg')
    context = {key: int(value, 16) for key, value in re.findall(
        r'^\s*(PC|XPSR|CONTROL|PRIMASK|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)',
        text, re.M)}
    ccr = words(0xE000ED14, 1, 'ccr')[0]
    fpccr = words(0xE000EF34, 1, 'fpccr')[0]
    validate_context(context, ccr, fpccr)
    enabled = words(0x56028260, 1, 'ahb5enr')[0]
    reset = words(0x56028220, 1, 'ahb5rstr')[0]
    if enabled & 0x2020 != 0x2020 or reset & 0x2020:
        raise ValueError('Do not read unclocked or reset XSPI/XSPIM')
    sr = words(0x58025020, 1, 'xspi-sr')[0]
    if sr & 0x7F20:
        raise ValueError('XSPI controller is not idle with empty FIFO')
    after = validate_status(words(STATUS_ADDRESS, 24, 'recovery-status-rechecked'))
    if after != status:
        raise ValueError('Recovery status changed while validating park')
    vcp_after = validate_vcp_status(words(VCP_ADDRESS, 32, 'vcp-status-rechecked'), after)
    if vcp_after != vcp:
        raise ValueError('VCP proof changed while validating park')
    transport.log('recovery_verified', profile=profile['id'],
                  prefix_sha256=profile['prefix_sha256'], status=status,
                  vcp_status=vcp, context=context, ccr=ccr, fpccr=fpccr,
                  xspi_sr=sr, persistent_halt_after_disconnect=False)
    return profile
