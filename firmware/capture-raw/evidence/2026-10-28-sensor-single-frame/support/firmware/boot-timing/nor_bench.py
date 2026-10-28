"""Run one reviewed RAM NOR operation through HOTPLUG AP1, without reset.

Requires exclusive bench ownership and either fresh code RAM after a cold boot
or the identical helper already executed there. Never replaces executed code
with a different binary under an active I-cache. No power control is performed.
Failed operations leave the target alone for diagnosis; no automatic retry of
an erase/program, debugger reset, or power cycle is attempted.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import zlib

CLI = Path('C:/Users/joshd/AppData/Local/stm32cube/bundles/programmer/2.23.0/bin/STM32_Programmer_CLI.exe')
SERIAL = '002100203335511035383531'
FIELDS = '''magic result sequence command stage address transfer_count polls last_sr
nor_status nor_security jedec_id changed_mask erased_mask completed_mask pages_programmed
current_crc input_crc final_crc expected_current_crc expected_input_crc flags failure_stage
failure_address failure_opcode last_opcode control ipsr cpu_ccr old_msp old_msplim ahb5enr
ahb5rstr mux_cr original_cr original_dcr1 original_dcr2 original_sr original_ccr original_tcr
original_ir original_dlr original_ar cfgr1 cfgr2 pll1cfgr1 pll1cfgr2 pll1cfgr3 dwt_initial
dwt_final dwt_advance cleanup_result first_mismatch wren_count transaction_count max_wip_cycles'''.split()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Bench:
    def __init__(self, output):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.calls = 0

    def call(self, *args, timeout=20, success=None):
        self.calls += 1
        argv = [str(CLI), '-c', 'port=SWD', 'mode=HOTPLUG', 'ap=1', 'sn='+SERIAL,
                *map(str, args)]
        began = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            process = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            # subprocess.run has reaped only its own CLI. It does not stop the
            # RAM helper; preserve that distinction and never reset the target.
            (self.output/f'cli-{self.calls:02d}-timeout.log').write_bytes(exc.stdout or b'')
            raise RuntimeError('CLI timed out; target state unknown. No reset or power change performed.') from exc
        (self.output/f'cli-{self.calls:02d}.log').write_bytes(process.stdout)
        with (self.output/'calls.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'utc': began, 'argv': argv, 'returncode': process.returncode})+'\n')
        text = process.stdout.decode('utf-8', errors='replace')
        if process.returncode or 'Error:' in text or (success and success not in text):
            raise RuntimeError(f'CLI call {self.calls} failed; inspect its saved log. No automatic reset/retry.')
        return text

    def upload(self, address, length, name):
        path = self.output/name
        if path.exists():
            raise FileExistsError(path)
        self.call('-u', hex(address), str(length), path)
        data = path.read_bytes()
        if len(data) != length:
            raise RuntimeError(f'Incomplete RAM upload: {path}')
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['info', 'write'])
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--current', type=Path)
    parser.add_argument('--desired', type=Path)
    args = parser.parse_args()
    if not 0 < args.sequence < 2**32:
        parser.error('Sequence must fit a nonzero 32-bit word')
    if args.operation == 'write' and not (args.current and args.desired):
        parser.error('WRITE requires exact current and desired 65536-byte files')
    manifest = json.loads((args.build/'manifest.json').read_text(encoding='utf-8-sig'))
    binary = args.build/'programmer.bin'
    if sha(binary.read_bytes()) != manifest['binary_sha256']:
        raise ValueError('Helper differs from reviewed build manifest')
    if (manifest['load'] != '0x341E0000' or manifest['thumb_entry'] != '0x341E0001'
            or manifest['command_address'] != '0x341B4000'
            or manifest['status'] != '0x341B4100'
            or manifest['status_fields_in_word_order'] != FIELDS):
        raise ValueError('Helper layout differs from this reviewed host runner')
    current = args.current.read_bytes() if args.current else b''
    desired = args.desired.read_bytes() if args.desired else b''
    if args.operation == 'write' and (len(current) != 65536 or len(desired) != 65536):
        raise ValueError('Both flash buffers must be exactly 65536 bytes')
    bench = Bench(args.out)
    command = [0x4E4F5244, args.sequence, 2 if args.operation == 'info' else 3,
               0 if args.operation == 'info' else 65536, 0,
               0 if args.operation == 'info' else 0x57524954,
               zlib.crc32(current), zlib.crc32(desired)]
    cmd = bench.output/'command.bin'
    cmd.write_bytes(struct.pack('<8I', *command))
    clear = bench.output/'clear-status.bin'
    clear.write_bytes(bytes(len(FIELDS)*4))
    (bench.output/'request.json').write_text(json.dumps({
        'operation': args.operation, 'sequence': args.sequence, 'command': command,
        'helper_sha256': sha(binary.read_bytes()),
        'current_sha256': sha(current), 'desired_sha256': sha(desired),
        'current_source': str(args.current), 'desired_source': str(args.desired),
    }, indent=2)+'\n', encoding='utf-8')
    bench.call('-halt', '-w', binary.resolve(), '0x341E0000', '-v',
               success='Download verified successfully')
    if args.operation == 'write':
        bench.call('-halt', '-w', args.desired.resolve(), '0x341C0000', '-v',
                   success='Download verified successfully')
    bench.call('-halt', '-w', clear, '0x341B4100', '-v',
               '-w', cmd, '0x341B4000', '-v',
               '-coreReg', 'PC=0x341E0001', 'XPSR=0x01000000', '-run', success='Core run')
    # Observe completion without halting an in-progress NOR write. Each CLI is
    # bounded; elapsed host timeout means diagnostic stop, not hardware reset.
    deadline = time.monotonic()+90
    for poll in range(40):
        data = bench.upload(0x341B4100, len(FIELDS)*4, f'status-{poll:02d}.bin')
        status = dict(zip(FIELDS, struct.unpack('<'+'I'*len(FIELDS), data)))
        if (status['sequence'] == args.sequence and status['command'] == command[2]
                and status['expected_current_crc'] == command[6]
                and status['expected_input_crc'] == command[7]
                and status['magic'] == 0x444F4E45):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('No fresh DONE record; target left running for diagnosis')
        time.sleep(.2)
    else:
        raise TimeoutError('No fresh DONE record; target left running for diagnosis')
    (bench.output/'status.json').write_text(json.dumps(status, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(status, indent=2), flush=True)
    # A DONE record alone may still flag flash/controller state uncertainty.
    if status['result'] or status['flags'] & 16 or status['flags'] & 7 != 7:
        raise RuntimeError('RAM helper refused/failed operation; target left as-is for diagnosis')
    bench.call('-halt')
    if args.operation == 'write':
        readback = bench.upload(0x341D0000, 65536, 'readback.bin')
        if readback != desired:
            raise RuntimeError('Full 64KiB host comparison failed')
        (bench.output/'verified.json').write_text(json.dumps({
            'byte_for_byte_match': True, 'bytes': len(readback), 'sha256': sha(readback),
            'changed_mask': status['changed_mask'], 'erased_mask': status['erased_mask'],
            'completed_mask': status['completed_mask'], 'pages_programmed': status['pages_programmed'],
        }, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
