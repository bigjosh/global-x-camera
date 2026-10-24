"""Native execution of the exact sink: boundaries, FNV, accounting and limits."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
CLOCK=C.CFUNCTYPE(C.c_uint64,C.c_void_p)
class Chunk(C.Structure):
    _fields_=[('bytes',C.c_uint32),('fnv',C.c_uint32),('elapsed',C.c_uint64),
              ('sink',C.c_uint64),('cpu',C.c_uint64)]
class Sink(C.Structure):
    _fields_=[('now',CLOCK),('user',C.c_void_p),('chunks',C.POINTER(Chunk)),
              ('begin',C.c_uint64),('deadline',C.c_uint64),('sink_cycles',C.c_uint64),
              ('bytes',C.c_uint32),('fnv',C.c_uint32),('calls',C.c_uint32),
              ('chunk_count',C.c_uint32),('error',C.c_uint32)]
def fnv(data):
    value=2166136261
    for byte in data:value=((value^byte)*16777619)&0xffffffff
    return value

class SinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='png-sink-')
        path=Path(cls.folder.name)/'sink.dll'
        cc=shutil.which('clang') or shutil.which('gcc')
        subprocess.run([cc,'-shared','-O2','-std=c11','-Wall','-Wextra','-Werror',
                        str(HERE/'bench_sink.c'),'-o',str(path)],check=True,capture_output=True)
        cls.lib=C.CDLL(str(path))
        cls.lib.pb_sink_init.argtypes=[C.POINTER(Sink),CLOCK,C.c_void_p,C.POINTER(Chunk),C.c_uint64,C.c_uint64]
        cls.lib.pb_sink_write.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]
        cls.lib.pb_sink_finish.argtypes=[C.POINTER(Sink),C.c_uint64]
    @classmethod
    def tearDownClass(cls):
        if hasattr(C,'windll'): C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle))
        cls.folder.cleanup()
    def setUp(self):
        self.tick=100; self.chunks=(Chunk*100)(); self.sink=Sink()
        @CLOCK
        def clock(user):
            self.tick+=10
            return self.tick
        self.clock=clock
        self.lib.pb_sink_init(C.byref(self.sink),clock,None,self.chunks,100,4000000000)
    def put(self,raw):
        data=C.create_string_buffer(raw)
        return self.lib.pb_sink_write(C.byref(self.sink),data,len(raw))
    def test_stream_boundaries_digest_and_disjoint_intervals(self):
        raw=bytes(range(256))*400+bytes(range(17))
        for start in range(0,len(raw),16381):self.assertEqual(self.put(raw[start:start+16381]),1)
        self.assertEqual(self.lib.pb_sink_finish(C.byref(self.sink),self.tick+100),1)
        self.assertEqual(self.sink.fnv,fnv(raw)); self.assertEqual(self.sink.bytes,len(raw))
        self.assertEqual(self.sink.chunk_count,4)
        prior=0
        for chunk in self.chunks[:4]:
            self.assertGreater(chunk.bytes,prior); prior=chunk.bytes
            self.assertEqual(chunk.fnv,fnv(raw[:chunk.bytes]))
            self.assertEqual(chunk.elapsed,chunk.sink+chunk.cpu)
    def test_exact_boundary_no_duplicate_empty_tail(self):
        self.assertEqual(self.put(b'X'*32768),1)
        self.assertEqual(self.lib.pb_sink_finish(C.byref(self.sink),self.tick+100),1)
        self.assertEqual(self.sink.chunk_count,1)
    def test_output_limit_refuses_before_read(self):
        self.sink.bytes=3200000
        self.assertEqual(self.lib.pb_sink_write(C.byref(self.sink),None,1),0)
        self.assertEqual(self.sink.error,9)
    def test_deadline_refuses_callback(self):
        self.sink.deadline=5
        self.assertEqual(self.put(b'abc'),0); self.assertEqual(self.sink.error,10)
        self.assertEqual(self.sink.bytes,0)
    def test_chunk_bound_refuses(self):
        self.sink.chunk_count=100
        self.assertEqual(self.put(b'a'*32768),0); self.assertEqual(self.sink.error,12)
    def test_regressing_clock_refuses(self):
        self.tick=0
        self.assertEqual(self.put(b'a'),0); self.assertEqual(self.sink.error,10)

if __name__=='__main__':unittest.main()
