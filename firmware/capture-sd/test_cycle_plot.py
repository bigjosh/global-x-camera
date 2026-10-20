"""Offline compact evidence tests using actual recorder/analyzer output."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

import cycle_energy
import cycle_plot
from test_cycle_energy import CRITERIA, record


class CompactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.raw=self.root/"raw"
        record(self.raw,decimation=2)
        evidence=self.root/"proof.json"
        evidence.write_text('{"test_only":true}')
        window=dict(name="synthetic cycle",start_sample_id=0,end_sample_id=6400,
                    terminal_state_qualified=True,terminal_evidence=str(evidence))
        self.analysis=cycle_energy.analyze(self.raw,dict(criteria=CRITERIA,cycles=[window]))
        self.path=self.root/"analysis.json"
        self.path.write_text(json.dumps(self.analysis))

    def tearDown(self):
        self.temp.cleanup()

    def test_compact_integrals_retain_spike_all_samples_and_native_decimation(self):
        compact=cycle_plot.export(self.raw,self.path,bin_s=.037,idle_tail_s=.7)
        rows=compact["rows"]
        self.assertEqual(sum(r[2] for r in rows),
                         (compact["view_end_sample_id"]-compact["view_start_sample_id"])//2)
        self.assertEqual(max(r[5] for r in rows),1.0)
        self.assertEqual(max(r[11] for r in rows),5.0)
        self.assertAlmostEqual(compact["exact_segment_integrals_j"]["onset_to_plateau_energy_j"],
                               .904,places=6)
        for name,value in compact["exact_segment_integrals_j"].items():
            self.assertAlmostEqual(value,self.analysis["cycles"][0][name],places=12)
        self.assertIn("not within-bin sample order"," ".join(compact["limits"]))
        self.assertFalse(compact["uses_host_utc_alignment"])

    def test_changed_analysis_boundary_integral_or_manifest_hash_rejected(self):
        for kind in ("integral","manifest","geometry"):
            with self.subTest(kind=kind):
                data=json.loads(json.dumps(self.analysis))
                if kind=="integral":
                    data["cycles"][0]["onset_to_plateau_energy_j"]+=.1
                elif kind=="manifest":
                    data["manifest_sha256"]="0"*64
                else:
                    data["sample_rate_hz"]=1000
                self.path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    cycle_plot.export(self.raw,self.path)

    def test_unqualified_plateau_flags_survive_compact_export(self):
        old=self.analysis['cycles'][0]
        window=dict(name='unverified current signature',**old['window'],
                    terminal_state_qualified=False,terminal_evidence=old['terminal_evidence'])
        analysis=cycle_energy.analyze(self.raw,dict(criteria=CRITERIA,cycles=[window]),
                                      allow_unqualified_plateau=True)
        self.path.write_text(json.dumps(analysis))
        compact=cycle_plot.export(self.raw,self.path)
        metadata=compact['cycle_analysis']
        self.assertFalse(metadata['terminal_state_qualified'])
        # This is also the metadata consumed by plot's ambiguity annotation.
        self.assertFalse(metadata['completion_boundary_qualified'])
        self.assertFalse(metadata['onset_to_plateau_energy_is_complete_cycle'])
        self.assertIn('not firmware completion, SBF or file verification',
                      metadata['terminal_state_qualification'])
        self.assertAlmostEqual(compact['exact_segment_integrals_j']['onset_to_plateau_energy_j'],
                               old['onset_to_plateau_energy_j'],places=12)

    def test_signed_power_is_preserved_and_partial_bin_boundaries_fail(self):
        class Fake:
            rate=1000
            decimation=2
            def get(self,name,start,end):
                return np.array([1,-2,3,-4,5],dtype="<f4")
        rows=cycle_plot.bins(Fake(),10,20,6,(14,))
        self.assertEqual([r[:3] for r in rows],[[10,14,2],[14,16,1],[16,20,2]])
        self.assertAlmostEqual(cycle_plot.integrated(rows,10,20,1000,2),.006)
        with self.assertRaisesRegex(ValueError,"boundaries"):
            cycle_plot.integrated(rows,12,20,1000,2)
        with self.assertRaisesRegex(ValueError,"misaligned"):
            cycle_plot.bins(Fake(),10,20,6,(13,))

    def test_nonfinite_cannot_be_hidden_by_binning_and_output_never_overwrites(self):
        class Fake:
            decimation=1
            def get(self,*args):
                return np.array([0,np.nan,1],dtype="<f4")
        with self.assertRaisesRegex(ValueError,"Nonfinite"):
            cycle_plot.bins(Fake(),0,3,3)
        compact=cycle_plot.export(self.raw,self.path)
        path=self.root/"compact.json.gz"
        cycle_plot.write_compact(path,compact)
        self.assertEqual(cycle_plot.read_compact(path),compact)
        with self.assertRaises(FileExistsError):
            cycle_plot.write_compact(path,compact)


if __name__=="__main__":
    unittest.main()
