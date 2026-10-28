"""Offline fixtures only: no instruments, subprocesses, or real bench files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "experiments/collect_matrix_evidence.py"
SPEC = importlib.util.spec_from_file_location("collector", SCRIPT)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.capture = self.repo / "tmp/bringup/opt-matrix-test-01"
        self.trial = self.repo / "tmp/bringup/nor-program-test-01"
        self.capture.mkdir(parents=True)
        self.trial.mkdir(parents=True)
        self.review = {"passed": True}
        self.write_json(self.capture / "independent-review.json", self.review)
        self.write_json(self.capture / "cycle-outcome.json", {
            "passed": True, "cycle_returncode": 0, "capture_returncode": 0,
            "inspection_returncode": 0})
        for name in ("capture-config.json", "digital.csv", "cycle-log.jsonl",
                     "analog.csv", "boot.sal"):
            (self.capture / name).write_bytes(b"raw\r\nbytes\n")
        (self.capture / "unrelated-secret.bin").write_bytes(b"not selected")
        data = b"\xff" * 65536
        image = self.repo / "tmp/bringup/image.bin"
        image.write_bytes(data)
        (self.trial / "readback.bin").write_bytes(data)
        (self.trial / "status.bin").write_bytes(b"status bytes")
        self.request = {"sequence": 12, "desired_sha256": sha(data),
                        "current_sha256": sha(data),
                        "desired_source": str(image), "current_source": str(image)}
        self.write_json(self.trial / "request.json", self.request)
        self.write_json(self.trial / "status.json", {
            "sequence": 12, "command": 3, "result": 0,
            "magic": 0x444F4E45, "flags": 7})
        self.write_json(self.trial / "verified.json", {
            "byte_for_byte_match": True, "bytes": len(data), "sha256": sha(data)})
        self.analysis = self.repo / "tmp/bringup/analysis.json"
        self.write_json(self.analysis, {"passed": True, "runs": [{
            "label": "test", "folder": str(self.capture), "passed": True,
            "independent_review_sha256": sha((self.capture / "independent-review.json").read_bytes())}]})
        self.manifest = self.repo / "manifest.json"
        self.write_json(self.manifest, {
            "schema_version": 1, "source_root": "tmp/bringup",
            "captures": [self.capture.name], "program_trials": [self.trial.name],
            "analysis": str(self.analysis)})
        self.output = self.repo / "evidence/complete"

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_preserves_compact_bytes_excludes_raw_and_unrelated_files(self):
        result = collector.collect(self.repo, self.manifest, self.output)
        self.assertFalse(result["hardware_access"])
        copied = self.output / "captures" / self.capture.name / "digital.csv"
        source = self.capture / "digital.csv"
        self.assertEqual(source.read_bytes(), copied.read_bytes())
        self.assertEqual(source.stat().st_mtime_ns, copied.stat().st_mtime_ns)
        self.assertEqual(collector.attributes(source), collector.attributes(copied))
        self.assertEqual((self.output / ".gitattributes").read_bytes(), b"* -text -whitespace\n")
        names = {path.name for path in self.output.rglob("*") if path.is_file()}
        self.assertTrue({"analog.csv", "boot.sal", "image.bin", "readback.bin", "unrelated-secret.bin"}.isdisjoint(names))
        provenance = json.loads((self.output / "provenance.json").read_text())
        self.assertTrue(provenance["complete"])
        self.assertEqual(len(provenance["local_only_artifacts"]), 4)
        self.assertTrue(all(item["sha256"] for item in provenance["local_only_artifacts"]))
        with self.assertRaises(FileExistsError):
            collector.collect(self.repo, self.manifest, self.output)

    def test_rejects_failed_capture_before_publishing(self):
        self.write_json(self.capture / "cycle-outcome.json", {"passed": False})
        with self.assertRaisesRegex(ValueError, "Capture has not passed"):
            collector.collect(self.repo, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_stale_analysis_hash(self):
        self.write_json(self.capture / "independent-review.json", {"passed": True, "changed": True})
        with self.assertRaisesRegex(ValueError, "review hash is stale"):
            collector.collect(self.repo, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_readback_content_mismatch(self):
        (self.trial / "readback.bin").write_bytes(b"\x00" * 65536)
        with self.assertRaisesRegex(ValueError, "readback hash mismatch"):
            collector.collect(self.repo, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_unselected_runs_and_path_escape(self):
        self.write_json(self.analysis, {"passed": True, "runs": [{
            "folder": str(self.capture), "label": "test", "passed": True},
            {"folder": str(self.repo / "tmp/bringup/unselected"), "label": "other", "passed": True}]})
        with self.assertRaisesRegex(ValueError, "exactly the selected captures"):
            collector.collect(self.repo, self.manifest, self.output)
        with self.assertRaises(ValueError):
            collector.resolve_in_repo(self.repo, "../outside")


if __name__ == "__main__":
    unittest.main()
