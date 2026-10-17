"""Request one off/on cycle from an already-running js110_session.py.

Start the logic capture first. This uses host delays only for dwell times;
physical timing must come from the recorded rail waveforms.
"""
import argparse
import json
import os
from pathlib import Path
import time
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--response', type=Path, required=True)
    p.add_argument('--off-seconds', type=float, default=15)
    args = p.parse_args()
    if not 1 <= args.off_seconds <= 30:
        p.error('--off-seconds must be between 1 and 30')

    def request(state):
        ident = str(uuid.uuid4())
        tmp = args.control.with_suffix('.request.tmp')
        tmp.write_text(json.dumps({'id': ident, 'state': state}), encoding='utf-8')
        os.replace(tmp, args.control)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                result = json.loads(args.response.read_text(encoding='utf-8-sig'))
                if result.get('id') == ident:
                    print(json.dumps(result), flush=True)
                    if not result.get('ok'):
                        raise RuntimeError('Joulescope command failed')
                    return
            except (FileNotFoundError, PermissionError, json.JSONDecodeError):
                pass
            time.sleep(0.05)
        raise TimeoutError('No matching response from persistent JS110 session')

    try:
        request('off')
        time.sleep(args.off_seconds)
        request('query')
    finally:
        request('auto')
    time.sleep(2)
    request('query')


if __name__ == '__main__':
    main()
