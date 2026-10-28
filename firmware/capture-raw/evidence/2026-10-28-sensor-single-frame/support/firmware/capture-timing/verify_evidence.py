"""Verify archived evidence bytes against each immutable archive index."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent / 'evidence'
    count = size = 0
    indexes = sorted(root.glob('*/archive-index.json'))
    for index in indexes:
        for entry in json.loads(index.read_text())['files']:
            path = (index.parent / entry['archive']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError(f'Archive path escapes evidence root: {path}')
            data = path.read_bytes()
            if (len(data) != entry['bytes']
                    or hashlib.sha256(data).hexdigest() != entry['sha256']):
                raise ValueError(f'Archive bytes changed: {path}')
            count += 1
            size += len(data)
    print(json.dumps(dict(indexes=len(indexes), files=count, bytes=size, passed=True)))


if __name__ == '__main__':
    main()
