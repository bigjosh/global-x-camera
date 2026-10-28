"""Synthetic protocol/parser tests; no instrument or target access."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import decode


def channel(events=range(1, 11), errors=None):
    edges = []
    for n, event in enumerate(events):
        start = .1 + n * .01
        edges.extend((start, start + event * decode.STEP_S + (errors or {}).get(n, 0)))
    return dict(initial_state=0, begin_s=0., end_s=1., transitions=edges)


def binary(c, version=0):
    return (struct.pack("<8siiIddQ", b"<SALEAE>", version, 0, c["initial_state"],
                        c["begin_s"], c["end_s"], len(c["transitions"])) +
            b"".join(struct.pack("<d", x) for x in c["transitions"]))


class DecodeTests(unittest.TestCase):
    def test_complete_sequence_exact_intervals_but_not_standby_or_image_proof(self):
        reset = dict(initial_state=0, transitions=[.05], begin_s=0., end_s=1.)
        power = dict(initial_state=0, transitions=[.02], begin_s=0., end_s=1.)
        result = decode.decode(channel(), reset, power)
        self.assertTrue(result["decode_passed"])
        cycle = result["cycles"][0]
        self.assertEqual(cycle["event_ids"], list(range(1, 11)))
        self.assertTrue(cycle["marker_protocol_complete"])
        self.assertFalse(result["actual_standby_verified"])
        self.assertFalse(result["image_integrity_verified"])
        self.assertAlmostEqual(cycle["intervals"][0]["first_edge_delta_s"], .01)
        self.assertAlmostEqual(cycle["reset_release_to_receiver_entry_s"], .05)
        self.assertAlmostEqual(cycle["power_threshold_to_receiver_entry_s"], .08)

    def test_width_tolerance_accepts_quantization_but_rejects_unknowns(self):
        self.assertTrue(decode.decode(channel(errors={i: (-1)**i*140e-9 for i in range(10)}))["decode_passed"])
        bad = decode.decode(channel(errors={4: 160e-9}))
        self.assertFalse(bad["decode_passed"])
        self.assertEqual(bad["pulses"][4]["error"], "unknown_pulse_width")
        self.assertIsNone(bad["pulses"][4]["event_id"])
        self.assertIn(5, bad["cycles"][0]["missing_event_ids"])

    def test_short_glitch_and_out_of_range_retained_as_errors(self):
        for width in (20e-9, 5.6e-6):
            c = channel()
            c["transitions"][:0] = [.01, .01+width]
            result = decode.decode(c)
            self.assertFalse(result["decode_passed"])
            self.assertEqual(result["pulses"][0]["error"], "unknown_pulse_width")

    def test_missing_duplicate_out_of_order_do_not_qualify(self):
        for ids in ([1, 2, 4], [1, 2, 2, 3], [1, 3, 2], [2, 3]):
            with self.subTest(ids=ids):
                self.assertFalse(decode.decode(channel(ids))["decode_passed"])

    def test_partial_high_boundaries_are_not_event_pulses(self):
        c = channel([1])
        c["initial_state"] = 1
        c["transitions"] = [.0000005] + c["transitions"] + [.9]
        result = decode.decode(c)
        self.assertIsNone(result["pulses"][0]["event_id"])
        self.assertIsNone(result["pulses"][-1]["event_id"])
        self.assertFalse(result["decode_passed"])

    def test_two_cycles_have_separate_reference_edges(self):
        c = channel()
        c["transitions"] += [x+.5 for x in c["transitions"]]
        reset = dict(initial_state=0, transitions=[.05, .4, .55], begin_s=0., end_s=1.)
        result = decode.decode(c, reset)
        self.assertTrue(result["decode_passed"])
        self.assertEqual(len(result["cycles"]), 2)
        self.assertAlmostEqual(result["cycles"][1]["reset_release_to_receiver_entry_s"], .05)

    def test_initial_high_reference_does_not_invent_an_edge(self):
        high = dict(initial_state=1, transitions=[], begin_s=0., end_s=1.)
        result = decode.decode(channel(), high, high)
        self.assertIsNone(result["cycles"][0]["reset_release_to_receiver_entry_s"])
        self.assertIsNone(result["cycles"][0]["power_threshold_to_receiver_entry_s"])

    def test_explicit_storage_sequence_accepts_only_ordered_four_to_nine(self):
        good = channel(range(4, 10))
        self.assertTrue(decode.decode(good, sequence="storage")["decode_passed"])
        self.assertFalse(decode.decode(good)["decode_passed"])
        for ids in ([4, 5, 6, 8, 9], [4, 5, 5, 6, 7, 8, 9], range(1, 11)):
            self.assertFalse(decode.decode(channel(ids), sequence="storage")["decode_passed"])
        result = decode.decode(good, sequence="storage")
        self.assertNotIn("elapsed_from_receiver_entry_s", result["cycles"][0])
        self.assertFalse(result["actual_standby_verified"])

    def test_mismatched_capture_reference_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "digital_1.bin").write_bytes(binary(channel()))
            other = channel(); other["end_s"] = 1.001
            (root / "digital_4.bin").write_bytes(binary(other))
            with self.assertRaisesRegex(ValueError, "time bounds"):
                decode.summarize_folder(root)

    def test_binary_roundtrip_hash_and_strict_invalid_files(self):
        with tempfile.TemporaryDirectory() as name:
            p = Path(name) / "digital_1.bin"
            p.write_bytes(binary(channel()))
            result = decode.read_digital(p)
            self.assertEqual(result["transitions"], channel()["transitions"])
            self.assertEqual(len(result["sha256"]), 64)
            self.assertTrue(decode.summarize_folder(name)["decode_passed"])
            invalid = [binary(channel())[:-1], binary(channel(), version=1), b"bad"]
            for edges in ([.2, .1], [.1, .1], [float("nan")], [1.1]):
                c = channel(); c["transitions"] = edges; invalid.append(binary(c))
            for payload in invalid:
                p.write_bytes(payload)
                with self.assertRaises(ValueError):
                    decode.read_digital(p)


if __name__ == "__main__":
    unittest.main()
