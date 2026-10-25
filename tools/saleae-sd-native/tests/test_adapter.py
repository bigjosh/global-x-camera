"""Run the actual Logic adapter against recorded transitions with SDK mocks."""
import argparse
import gzip
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--adapter", type=Path, required=True)
args = parser.parse_args()
fixtures = Path(__file__).parent / "fixtures"
with tempfile.TemporaryDirectory(prefix="native-sd-adapter-") as temporary:
    paths = []
    for name in ("first-write", "final-stop"):
        path = Path(temporary) / (name + ".csv")
        path.write_bytes(gzip.decompress((fixtures / (name + ".csv.gz")).read_bytes()))
        paths.append(str(path))
    subprocess.run([str(args.adapter.resolve()), *paths], check=True, timeout=30)
