"""Capture one explicitly requested JS110 off/on cycle through existing helpers.

Requires confirmed wiring, an already-running restore-mode JS110 session, and
Logic's API server. No debugger command or firmware programming is performed.
Use a fresh output directory. Raw traces remain there for offline inspection.
After the capture process exits, inspect saved traces even if the cycle command
or capture/export failed. cycle-outcome.json preserves all failures separately;
a successful inspection does not erase a command failure. An unfinished capture
is left running to its own bounded timeout and is not inspected while exporting.
An interrupted parent keeps waiting for the bounded cycle child to finish its
own power-restoration finally block. A child that exceeds the wait deadline is
reported as still running and is never killed; no competing mailbox request is
sent. Such a failed run requires subsequent physical rail verification.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def wait_for_cycle(process, timeout_s, on_interrupt):
    """Wait without killing a power-control child on interrupt or timeout.

    subprocess.run kills its child on KeyboardInterrupt, which can bypass the
    child's power-restoration finally block. Short waits keep interrupts
    observable while allowing this child to complete its bounded operation.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout_s)
        try:
            return process.wait(timeout=min(0.5, remaining))
        except KeyboardInterrupt as exc:
            on_interrupt(exc)
        except subprocess.TimeoutExpired:
            continue


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--response', type=Path, required=True)
    p.add_argument('--off-seconds', type=float, default=20)
    p.add_argument('--on-range', choices=['auto', '2A'], default='auto')
    p.add_argument('--ch5-signal', choices=['target-5v', 'main-vddio'], required=True)
    p.add_argument('--after-cycle-seconds', type=float, default=2,
                   help='Additional capture time after cycle_once completes, e.g. for GPIO telemetry.')
    args = p.parse_args(argv)
    if args.output.exists():
        p.error('Use a new output directory')
    if not 1 <= args.off_seconds <= 30:
        p.error('--off-seconds must be between 1 and 30')
    if not 0 <= args.after_cycle_seconds <= 30:
        p.error('--after-cycle-seconds must be between 0 and 30')
    here = Path(__file__).resolve().parent
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    # Keep the capture alive through the longest bounded child wait and the
    # requested trailing telemetry interval, even at the largest CLI values.
    capture_seconds = max(90, args.off_seconds + 62 + args.after_cycle_seconds)
    capture = subprocess.Popen([sys.executable, str(here/'capture_manual.py'),
        str(args.output), '--seconds', str(capture_seconds), '--ch5-signal', args.ch5_signal],
        creationflags=flags)
    errors = []
    causes = []
    outcome = {'cycle_returncode': None, 'cycle_status': 'not_started',
               'cycle_pid': None, 'capture_returncode': None,
               'inspection_returncode': None, 'inspection_status': 'not_started'}

    def record_error(stage, exc):
        errors.append({'stage': stage, 'type': type(exc).__name__, 'message': str(exc)})
        causes.append(exc)

    stage = 'capture_start'
    try:
        deadline = time.monotonic() + 20
        while not (args.output/'started').exists():
            if capture.poll() is not None:
                raise RuntimeError('Capture exited before ready')
            if time.monotonic() >= deadline:
                raise TimeoutError('Capture did not become ready')
            time.sleep(.1)
        if capture.poll() is not None:
            raise RuntimeError('Capture no longer running')
        stage = 'cycle'
        with (args.output/'cycle-log.jsonl').open('w', encoding='utf-8') as log:
            cycle = subprocess.Popen([sys.executable, str(here/'cycle_once.py'),
                '--control', str(args.control), '--response', str(args.response),
                '--off-seconds', str(args.off_seconds), '--on-range', args.on_range], stdout=log,
                stderr=subprocess.STDOUT, creationflags=flags)
            outcome['cycle_status'] = 'running'
            outcome['cycle_pid'] = cycle.pid
            # Five mailbox requests have eight-second response deadlines,
            # plus off dwell, two seconds after on, and ten seconds of margin.
            try:
                wait_for_cycle(cycle, args.off_seconds + 52,
                               lambda exc: record_error('cycle_interrupted', exc))
            finally:
                outcome['cycle_returncode'] = cycle.poll()
                outcome['cycle_status'] = ('finished' if cycle.returncode is not None
                                           else 'still_running_after_wait')
            if cycle.returncode:
                record_error('cycle', subprocess.CalledProcessError(cycle.returncode, cycle.args))
        time.sleep(args.after_cycle_seconds)
    except (Exception, KeyboardInterrupt) as exc:
        record_error(stage, exc)
    finally:
        try:
            if args.output.is_dir():
                (args.output/'stop').touch()
        except Exception as exc:
            record_error('capture_stop', exc)
        try:
            capture.wait(timeout=60)
        except (Exception, KeyboardInterrupt) as exc:
            record_error('capture_wait', exc)
        outcome['capture_returncode'] = capture.poll()
        if outcome['capture_returncode']:
            record_error('capture_export', RuntimeError(
                f"Capture/export failed: {outcome['capture_returncode']}"))
        if outcome['capture_returncode'] is None:
            outcome['inspection_status'] = 'skipped_capture_still_running'
        elif not args.output.is_dir():
            outcome['inspection_status'] = 'skipped_no_capture_directory'
            record_error('inspection', RuntimeError('No capture directory to inspect'))
        else:
            try:
                inspection = subprocess.run(
                    [sys.executable, str(here/'inspect_cycle.py'), str(args.output)],
                    check=False, creationflags=flags)
                outcome['inspection_returncode'] = inspection.returncode
                outcome['inspection_status'] = 'passed' if inspection.returncode == 0 else 'failed'
                if inspection.returncode:
                    record_error('inspection', subprocess.CalledProcessError(
                        inspection.returncode, inspection.args))
            except (Exception, KeyboardInterrupt) as exc:
                outcome['inspection_status'] = 'error'
                record_error('inspection', exc)
        outcome.update(passed=not errors and outcome['inspection_status'] == 'passed', errors=errors)
        if args.output.is_dir():
            try:
                (args.output/'cycle-outcome.json').write_text(
                    json.dumps(outcome, indent=2) + '\n', encoding='utf-8')
            except Exception as exc:
                record_error('outcome_save', exc)
    if errors:
        raise RuntimeError('; '.join(f"{error['stage']}: {error['message']}"
                                     for error in errors)) from causes[0]


if __name__ == '__main__':
    main()
