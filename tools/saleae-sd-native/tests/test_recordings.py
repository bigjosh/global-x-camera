"""Regression-test the passive C++ decoder using two recorded SD bus clips.

Only Python's standard library and the built sd_native_replay executable are
required. No instrument API, private full capture, or target access is used.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[3]
REPLAY = REPO / "tmp/sd-native-build/Release/sd_native_replay.exe"


class RecordedCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        if not REPLAY.is_file():
            raise FileNotFoundError(f"Build sd_native_replay first, or pass --replay: {REPLAY}")
        cls.temporary = tempfile.TemporaryDirectory(prefix="sd-native-recordings-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.events = {}
        cls.payloads = {}
        for name in cls.manifest["fixtures"]:
            payload = gzip.decompress((FIXTURES / f"{name}.csv.gz").read_bytes())
            cls.payloads[name] = payload
            csv_path = Path(cls.temporary.name) / f"{name}.csv"
            csv_path.write_bytes(payload)
            process = subprocess.run(
                [str(REPLAY.resolve()), "--width", "4", "--rate", "250000000", str(csv_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=True,
            )
            if process.stderr.strip():
                raise AssertionError(f"Unexpected replay stderr for {name}: {process.stderr}")
            cls.events[name] = [json.loads(line) for line in process.stdout.splitlines() if line]

    def of_type(self, name, kind):
        return [event for event in self.events[name] if event["type"] == kind]

    def test_fixture_hashes_counts_and_sample_boundaries(self):
        for name, record in self.manifest["fixtures"].items():
            with self.subTest(fixture=name):
                compressed = (FIXTURES / record["path"]).read_bytes()
                raw = self.payloads[name]
                self.assertEqual(len(compressed), record["gzip_bytes"])
                self.assertEqual(hashlib.sha256(compressed).hexdigest(), record["gzip_sha256"])
                self.assertEqual(len(raw), record["uncompressed_bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record["uncompressed_sha256"])
                reader = csv.reader(io.StringIO(raw.decode("ascii")))
                self.assertEqual(next(reader), self.manifest["columns"])
                rows = [list(map(int, row)) for row in reader]
                self.assertEqual(len(rows), record["event_rows"])
                self.assertEqual(rows[0][0], record["first_sample"])
                self.assertEqual(rows[-1][0], record["last_sample"])
                self.assertTrue(all(a[0] < b[0] for a, b in zip(rows, rows[1:])))
                for column, signal in enumerate(self.manifest["columns"][1:], start=1):
                    transitions = sum(a[column] != b[column] for a, b in zip(rows, rows[1:]))
                    self.assertEqual(transitions, record["transitions"][signal])

    def test_recorded_command_and_response_crcs(self):
        for name in self.manifest["fixtures"]:
            with self.subTest(fixture=name):
                commands = self.of_type(name, "command")
                responses = self.of_type(name, "response")
                expected = self.manifest["expected"][name]["host_commands"]
                self.assertEqual([int(e["fields"]["command"]) for e in commands], expected)
                self.assertEqual([int(e["fields"]["command"]) for e in responses], expected)
                for event in commands + responses:
                    self.assertFalse(event["error"], event)
                    self.assertEqual(event["fields"]["crc"], "OK")
                    self.assertEqual(event["fields"]["crc_received"], event["fields"]["crc_calculated"])
                    self.assertEqual(event["fields"]["end_bit"], "1")

    def test_cmd25_and_application_preerase_hint(self):
        commands = self.of_type("first-write", "command")
        hint = next(e for e in commands if e["fields"]["command"] == "23")
        write = next(e for e in commands if e["fields"]["command"] == "25")
        expected = self.manifest["expected"]["first-write"]
        self.assertEqual(hint["fields"]["application"], "yes")
        self.assertEqual(int(hint["fields"]["argument"], 16), expected["acmd23_blocks"])
        self.assertEqual(write["fields"]["application"], "no")
        self.assertEqual(int(write["fields"]["argument"], 16), expected["cmd25_lba"])
        transfer, = self.of_type("first-write", "transfer")
        self.assertEqual(int(transfer["fields"]["preerase_hint"]), expected["acmd23_blocks"])
        self.assertEqual(transfer["fields"]["explicit_CMD23_count"], "0")

    def test_first_block_payload_preview_and_all_lane_crcs(self):
        expected = self.manifest["expected"]["first-write"]
        blocks = self.of_type("first-write", "data_block")
        self.assertEqual(len(blocks), expected["complete_data_blocks"])
        block = blocks[0]
        self.assertFalse(block["error"])
        fields = block["fields"]
        self.assertEqual(fields["bytes"], "512")
        self.assertEqual(fields["width"], "4")
        self.assertEqual(fields["payload_clocks"], "1024")
        self.assertEqual(fields["packet_clocks"], "1042")
        self.assertEqual(fields["end_bits"], "OK")
        self.assertEqual(fields["mode"], "command-associated")
        self.assertEqual(fields["preview"].replace(" ", "").lower(), expected["first_payload_prefix_hex"])
        crc_text = "; ".join(
            f"D{lane}:OK 0x{crc:04X}/0x{crc:04X}"
            for lane, crc in enumerate(expected["data_crc_received"])
        )
        self.assertEqual(fields["CRC16 received/calculated"], crc_text)
        statuses = self.of_type("first-write", "write_status")
        self.assertEqual(len(statuses), expected["accepted_tokens"])
        self.assertFalse(statuses[0]["error"])
        self.assertEqual(statuses[0]["fields"]["status"], "2")
        self.assertEqual(statuses[0]["fields"]["token_end"], "1")

    def test_exact_raw_dat0_busy_intervals(self):
        for name in self.manifest["fixtures"]:
            with self.subTest(fixture=name):
                expected = self.manifest["expected"][name]
                busy, = self.of_type(name, "busy")
                self.assertFalse(busy["error"])
                self.assertEqual(busy["start"], expected["busy_edge_start_sample"])
                self.assertEqual(busy["end"], expected["busy_edge_end_sample"])
                self.assertEqual(int(busy["fields"]["sample_duration"]), expected["busy_edge_duration_samples"])
                self.assertAlmostEqual(busy["duration_us"], expected["busy_edge_duration_us"], places=9)
                self.assertEqual(busy["fields"]["boundary"], "raw DAT0 transitions")
                self.assertEqual(busy["fields"]["complete"], "yes")

    def test_final_r1b_busy_overlaps_response_and_programming_status(self):
        responses = self.of_type("final-stop", "response")
        busy, = self.of_type("final-stop", "busy")
        expected = self.manifest["expected"]["final-stop"]
        self.assertEqual(responses[0]["fields"]["response_type"], "R1b")
        self.assertEqual(responses[0]["start"], expected["cmd12_response_start_sample"])
        self.assertLess(busy["start"], responses[0]["start"])
        self.assertGreater(busy["end"], responses[1]["end"])
        self.assertLess(busy["end"], responses[2]["start"])
        self.assertIn("CMD12", busy["text"])
        self.assertEqual([int(e["fields"]["value"], 16) for e in responses], expected["r1_status_words"])
        self.assertEqual(
            [e["fields"]["card_state"] for e in responses],
            ["receive-data", "programming", "transfer"],
        )
        self.assertEqual([e["fields"]["ready_for_data"] for e in responses], ["no", "no", "yes"])
        self.assertFalse(any(e["error"] for e in self.events["final-stop"]))

    def test_truncated_cmd25_is_not_reported_complete(self):
        transfer, = self.of_type("first-write", "transfer")
        self.assertTrue(transfer["error"])
        self.assertEqual(transfer["fields"]["completion"], "capture/transaction incomplete")
        self.assertEqual(transfer["fields"]["blocks"], "1")
        self.assertEqual(transfer["fields"]["bad_data_blocks"], "0")
        self.assertEqual(transfer["fields"]["rejected_or_missing_status"], "0")
        self.assertEqual(int(transfer["fields"]["DAT0_busy_samples"]), 61026)
        self.assertEqual([e for e in self.events["first-write"] if e["error"]], [transfer])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=REPLAY)
    options, remaining = parser.parse_known_args()
    REPLAY = options.replay
    unittest.main(argv=[__file__, *remaining])
