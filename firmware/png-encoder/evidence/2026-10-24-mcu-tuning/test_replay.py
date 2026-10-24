"""Offline model and archived-identity regression checks; no hardware imports."""
import copy
from pathlib import Path
import tempfile
import unittest
import replay

def chunks(costs,sizes):
    total=cycles=0;out=[]
    for cost,size in zip(costs,sizes):
        total+=size;cycles+=cost
        out.append(dict(bytes=total,cpu_cycles=cycles))
    return out

class Models(unittest.TestCase):
    def test_one_buffer_unit(self):
        end,intervals=replay.pipeline(chunks([2],[3]),1,1)
        self.assertEqual(end,5);self.assertEqual(intervals[0]['producer_proxy_s'],2)
    def test_two_buffer_writer_bottleneck(self):
        # First producer ready at 1, writer owns buffers through 6/11/16.
        end,_=replay.pipeline(chunks([1,1,1],[5,5,5]),1,1)
        self.assertEqual(end,16)
    def test_two_buffer_producer_bottleneck(self):
        end,_=replay.pipeline(chunks([5,5,5],[1,1,1]),1,1)
        self.assertEqual(end,16)
    def test_variable_and_partial(self):
        end,intervals=replay.pipeline(chunks([2,1,4],[3,3,1]),1,1)
        self.assertEqual([i['bytes'] for i in intervals],[3,3,1])
        self.assertEqual(end,10)
    def test_percentile_interpolates(self):
        self.assertEqual(replay.pct([1,2,3],.95),2.9)
    def test_model_rejects_decreasing_counters(self):
        with self.assertRaises(ValueError):replay.pipeline(chunks([2,-1],[1,1]),1,1)
    def test_mve_normalization_scope(self):
        r={'reserved'+str(i):0 for i in range(53)}
        r.update(operation=2,reserved0=12,reserved1=0x4d564531,reserved2=0x343b0000,
                 reserved3=0x343a0000,reserved4=0xf00000)
        replay.normalization(r,dict(scalar_only=False,mve_conversion=True))
        with self.assertRaises(AssertionError):replay.normalization(r,dict(scalar_only=True))
        r['operation']=1
        with self.assertRaises(AssertionError):replay.normalization(r,dict(scalar_only=False,mve_conversion=True))
    def test_owned_permission_restored(self):
        r={'reserved'+str(i):0 for i in range(53)}
        r.update(operation=2,reserved0=12,reserved1=0x4d564531,reserved2=0x343b0000,
                 reserved3=0x343a0000,reserved4=0xf00020,reserved5=0x20,reserved6=1,reserved7=0x20)
        m=dict(scalar_only=False,mve_conversion=True,cpacr_policy='Explicit owned grant')
        replay.normalization(r,m)
        r['reserved7']=0
        with self.assertRaises(AssertionError):replay.normalization(r,m)
    def test_archive_replay(self):
        result=replay.replay()
        self.assertTrue(result['passed']);self.assertGreaterEqual(len(result['trials']),2)
    def test_missing_indexed_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'archive.json').write_text('{"files":[{"archived_path":"absent","bytes":0,"sha256":"x"}]}')
            with self.assertRaises(FileNotFoundError):replay.trial(p)

if __name__=='__main__':unittest.main()
