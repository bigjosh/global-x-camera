"""Offline negative-evidence and interval-scope checks, with no bench imports."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import compare_runs as compare
import energy


def stamp(seconds):
    return dict(utc=datetime.fromtimestamp(1700000000+seconds, timezone.utc).isoformat(),
                monotonic_ns=int((100+seconds)*1e9))


def result(fnv, nonce=1, mode=1):
    return dict(report=dict(magic=0x53564431, schema=1, words=128, state=2,
        operation=1, result=0, terminal=0x444F4E45, media_idle=1, card_error=0,
        fs_result=0, png_result=0, width=1120, height=1364,
        frame_bytes=compare.FRAME_BYTES, rows=1364, nonce=nonce, mode=mode,
        cpu_hz=400000000, sd_hz=25000000, fnv_before=fnv, fnv_after=fnv,
        png_bytes=700000, name=f"IMG{nonce:05d}.PNG",
        total=400000000, encode=300000000, callback=100000000,
        finish=1000000, init=1000000, mount=1000000, validate=1000000),
        card=dict(media_idle=1, error=0, initialized=0, controller_owned=0,
                  write_cycles=100000000),
        filesystem=dict(fat_result=0, completed=1, bytes_written=700000,
                        final_name=f"IMG{nonce:05d}.PNG"),
        request=dict(operation=1, mode=mode, nonce=nonce, sd_clock_hz=25000000),
        module_sha256="a"*64,
        final_context=dict(ccr=513, fpccr=0, registers=dict(CONTROL=0, FAULTMASK=0)),
        host_timing=dict(run_before=stamp(.4), run_after=stamp(.6), polls=[
            dict(before=stamp(.7), after=stamp(.8), state=1, terminal=0, nonce=nonce),
            dict(before=stamp(2.5), after=stamp(2.7), state=2,
                 terminal=0x444F4E45, nonce=nonce)]))


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = bytes(compare.FRAME_BYTES)
        cls.fnv = compare.fnv1a(cls.frame)

    def test_host_window_keeps_target_duration_separate(self):
        evidence = result(self.fnv)
        window, seconds = compare.host_window(evidence, .05)
        self.assertEqual(window["start_utc"], stamp(.4)["utc"])
        self.assertEqual(window["end_utc"], stamp(2.7)["utc"])
        self.assertAlmostEqual(seconds, 2.3)
        self.assertNotIn("target_duration_s", window)
        self.assertEqual(evidence["report"]["total"]/400000000, 1)

    def test_first_terminal_must_be_fresh_success_and_monotonic(self):
        for mutate in (
            lambda e: e["host_timing"]["polls"][-1].update(nonce=99),
            lambda e: e["host_timing"]["polls"][-1].update(state=3),
            lambda e: e["host_timing"]["polls"][-1].update(before=stamp(.5)),
            lambda e: e["host_timing"]["polls"][-1]["after"].update(utc=stamp(9)["utc"]),
            lambda e: e["report"].update(total=4*400000000),
        ):
            bad = result(self.fnv)
            mutate(bad)
            with self.assertRaises(energy.EvidenceError):
                compare.host_window(bad, .05)

    def test_reject_stale_or_corrupt_frame_nonidle_and_cache_dirty(self):
        for mutate in (
            lambda e: e["report"].update(fnv_after=0),
            lambda e: e["report"].update(nonce=99),
            lambda e: e["card"].update(media_idle=0),
            lambda e: e["filesystem"].update(completed=0),
            lambda e: e["final_context"].update(ccr=0x10000),
            lambda e: e["report"].update(callback=400000000),
            lambda e: e["report"].update(cache_enabled=1, final_ccr=513,
                                         postclean_validated=0, postclean_fnv=self.fnv),
        ):
            bad = result(self.fnv)
            mutate(bad)
            with self.assertRaises(energy.EvidenceError):
                compare.validate_save(bad, self.fnv)

    def test_manifest_extension_distinguishes_legacy_zero_words_from_v6(self):
        legacy = result(self.fnv)
        legacy["report"].update(cache_enabled=0, initial_mpu_ctrl=0, final_ccr=0,
                                postclean_validated=0, postclean_fnv=0, complete=0)
        _, policy = compare.validate_save(legacy, self.fnv)
        self.assertEqual(policy, {})
        new = deepcopy(legacy)
        new.update(cache_report_extension=1, data_cache_enabled=True)
        new["report"].update(cache_enabled=1, initial_mpu_ctrl=4, final_ccr=513,
                             postclean_validated=1, postclean_fnv=self.fnv, complete=410000000)
        self.assertEqual(compare.validate_save(new, self.fnv)[1]["cache_enabled"], 1)
        for key, value in (("final_ccr", 0x10000), ("postclean_validated", 0),
                           ("postclean_fnv", 0), ("initial_mpu_ctrl", 5),
                           ("cache_enabled", 0)):
            bad = deepcopy(new)
            bad["report"][key] = value
            with self.subTest(field=key), self.assertRaises(energy.EvidenceError):
                compare.validate_save(bad, self.fnv)

    def make_input(self, folder):
        (folder/"frame.bin").write_bytes(self.frame)
        return dict(schema=1, frame_file="frame.bin", measurement_setup="fixed setup", runs=[])

    def test_separate_module_and_cache_groups_and_reject_duplicate_observation(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            spec = self.make_input(folder)
            for i, mode in enumerate((0, 1, 2, 1), 1):
                evidence = result(self.fnv, i, mode)
                if i == 4:
                    evidence["module_sha256"] = "b"*64
                    evidence.update(cache_report_extension=1, data_cache_enabled=True)
                    evidence["report"].update(cache_enabled=1, initial_mpu_ctrl=0,
                        final_ccr=513, postclean_validated=1, postclean_fnv=self.fnv,
                        complete=410000000)
                path = folder/f"{i}.json"
                path.write_text(json.dumps(evidence))
                spec["runs"].append(dict(result=path.name))
            report = compare.compare(spec, folder)
            self.assertEqual(len(report["groups"]), 2)
            self.assertEqual(report["groups"][0]["observed_order"],
                             ["stored", "fast-none", "fast-sub"])
            self.assertEqual(report["runs"][-1]["complete_s"], 1.025)
            (folder/"copy.json").write_bytes((folder/"1.json").read_bytes())
            spec["runs"].append(dict(result="copy.json"))
            with self.assertRaises(energy.EvidenceError):
                compare.compare(spec, folder)

    def test_power_integration_uses_host_bracket_not_firmware_duration(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            spec = self.make_input(folder)
            (folder/"result.json").write_text(json.dumps(result(self.fnv)))
            power = dict(event="stream_chunk", signal="power", units="W",
                sample_id=0, sample_id_end_exclusive=100, sample_rate_hz=10,
                decimate_factor=1, count=100, finite_count=100, nonfinite_count=0,
                min=3, max=3, sum=300, mean=3, duration_s=10, gap_native_samples=None,
                sample_utc=stamp(0)["utc"], time_map={})
            records = [dict(event="stream_start", schema=2), power,
                       dict(event="stream_stop", complete=True, error=None, dropped_chunks=0)]
            (folder/"power.jsonl").write_text("\n".join(json.dumps(x) for x in records))
            spec["runs"] = [dict(result="result.json", stream_log="power.jsonl",
                                boundary_uncertainty_s=.05)]
            report = compare.compare(spec, folder)
            measured = report["runs"][0]["host_bracket_energy"]
            self.assertAlmostEqual(measured["uniform_partial_chunk_estimate_j"], 6.9, places=5)
            self.assertAlmostEqual(measured["energy_bounds_j"][0], 6.6, places=5)
            self.assertAlmostEqual(measured["energy_bounds_j"][1], 7.2, places=5)
            self.assertFalse(measured["physical_alignment_verified"])
            (folder/"power.jsonl").write_text("\n".join(json.dumps(x) for x in records[:-1]))
            with self.assertRaises(energy.EvidenceError):
                compare.compare(spec, folder)
            spec["allow_live_stream_snapshot"] = True
            live = compare.compare(spec, folder)["runs"][0]["host_bracket_energy"]
            self.assertFalse(live["recording_finalized"])
            self.assertIn("final logger", live["live_snapshot_limitation"])
            spec["runs"][0].pop("boundary_uncertainty_s")
            with self.assertRaises(energy.EvidenceError):
                compare.compare(spec, folder)


if __name__ == "__main__":
    unittest.main()
