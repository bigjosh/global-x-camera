"""Extract a frozen build or exact bench records to a new directory, offline.

This is source/evidence extraction only, not a build or instrument runner.
"""
import argparse
import json
from pathlib import Path

import replay


def write_files(out, files):
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        dest = (out / name).resolve()
        dest.relative_to(out.resolve())
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--build')
    group.add_argument('--record')
    group.add_argument('--tools', action='store_true')
    group.add_argument('--session', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    index = json.loads((Path(__file__).parent / 'index.json').read_bytes())
    if args.build:
        files = {n: replay.read_object(r) for n, r in index['builds'][args.build]['files'].items()}
    elif args.record:
        files = replay.record_files(index['records'][args.record])
    elif args.session:
        files = {n: replay.decompress_record(r) for n, r in index['bench_session'].items()}
    else:
        files = {n: replay.read_object(r) for n, r in index['tools'].items()}
    write_files(args.out.resolve(), files)
    print(f'Extracted {len(files)} exact files to {args.out.resolve()}')


if __name__ == '__main__':
    main()
