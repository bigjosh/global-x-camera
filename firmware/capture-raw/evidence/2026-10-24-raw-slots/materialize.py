"""Extract exact archived files into a new directory. No hardware or build calls."""
import argparse
import json
from pathlib import Path
import replay


def write_files(out, files):
    out = out.resolve()
    for name in files:
        replay.checked_name(name)
        (out / name).resolve().relative_to(out)
    out.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--record')
    group.add_argument('--build')
    group.add_argument('--tools', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    index = json.loads((Path(__file__).parent/'index.json').read_bytes())
    if args.tools:
        files = {name: replay.read_object(item) for name, item in index['tools'].items()}
    else:
        record = index['records'][args.record] if args.record else index['builds'][args.build]
        files = replay.file_bytes(record)
    write_files(args.out, files)
    print(f'Extracted {len(files)} exact files to {args.out.resolve()}')


if __name__ == '__main__':
    main()
