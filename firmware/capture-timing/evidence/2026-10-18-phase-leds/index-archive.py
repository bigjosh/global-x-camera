"""Index this offline archive plus exact deduplicated dependencies."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    paths = {p.relative_to(HERE).as_posix() for p in HERE.rglob('*')
             if p.is_file() and p.name != 'archive-index.json' and '__pycache__' not in p.parts
             and not any(part.startswith('restore-check') for part in p.parts)}
    for row in json.loads((HERE/'source-provenance.json').read_text()):
        paths.add(row['archive'])
    for row in json.loads((HERE/'license-index.json').read_text())['files']:
        paths.add(row['archive'])
    files = []
    for name in sorted(paths):
        path = (HERE/name).resolve()
        if not path.is_relative_to(HERE.parent.resolve()):
            raise ValueError('Index path escapes evidence tree')
        data = path.read_bytes()
        files.append(dict(archive=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    result = dict(schema=1, scope='Exact offline v44 phase LEDs and shallow sleep; hardware qualification pending', files=files)
    (HERE/'archive-index.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(files=len(files), indexed_bytes=sum(f['bytes'] for f in files))))


if __name__ == '__main__':
    main()
