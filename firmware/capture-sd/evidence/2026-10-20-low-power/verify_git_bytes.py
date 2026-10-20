"""Verify Git clean-filter or staged-blob identity without modifying the index."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from verify import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path(__file__).parent)
    parser.add_argument("--staged", action="store_true",
                        help="Require each archive file in stage 0 with exact bytes")
    args = parser.parse_args()
    archive = args.archive.resolve()
    verify(archive)
    def git(*argv, data=None):
        return subprocess.check_output(["git", "-C", str(archive), *argv], input=data)
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    algorithm = git("rev-parse", "--show-object-format").decode().strip()
    plan = json.loads((archive/"archive-plan.json").read_text())
    names = [e["archived_path"] for e in plan["source_index"]] + ["archive-plan.json"]
    staged = {}
    if args.staged:
        raw = git("ls-files", "--stage", "-z", "--", ".")
        for item in raw.split(b"\0"):
            if item:
                info, path = item.split(b"\t", 1)
                mode, oid, stage = info.decode().split()
                if stage != "0":
                    raise ValueError("Unmerged archive index entry")
                staged[path.decode()] = oid
    for name in names:
        path = archive/name
        raw = path.read_bytes()
        expected = hashlib.new(algorithm, b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        relative = path.relative_to(root).as_posix()
        actual = subprocess.check_output(
            ["git", "-C", str(root), "hash-object", "--path", relative, "--stdin"],
            input=raw).decode().strip()
        if actual != expected:
            raise ValueError("Git clean filter changes archived bytes: " + name)
        if args.staged and staged.get(name) != expected:
            raise ValueError("Staged archive blob differs or is missing: " + name)
    print(json.dumps(dict(files=len(names), exact_clean_filter_bytes=True,
                          exact_staged_blob_bytes=args.staged,
                          index_modified=False), indent=2))


if __name__ == "__main__":
    main()
