"""Exercise the explicit local literal-only path, including raw fallback.

Input/output bytes remain in host memory. No board or storage access.
"""
import ctypes as C
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
import zlib
from test_png16 import HERE, close_library

HARNESS=r'''
#include <stddef.h>
#include <string.h>
#include "miniz_config.h"
#include "vendor/miniz/miniz.h"
typedef struct { unsigned char *out; size_t used,capacity; } output;
static mz_bool sink(const void *p,int n,void *user) {
    output *o=user;
    if (n<0 || (size_t)n>o->capacity-o->used) return MZ_FALSE;
    memcpy(o->out+o->used,p,(size_t)n);o->used+=(size_t)n;return MZ_TRUE;
}
int flags_status(int flags,int callback) {
    tdefl_compressor d;
    return tdefl_init(&d,callback ? sink : NULL,NULL,flags);
}
int stream(const unsigned char *input,size_t bytes,size_t piece,
           unsigned char *out,size_t capacity,size_t *used,int intermediate_flush) {
    tdefl_compressor d; output o={out,0,capacity};
    int rc=tdefl_init(&d,sink,&o,TDEFL_FAST_HUFFMAN_ONLY|TDEFL_WRITE_ZLIB_HEADER);
    if (rc) return rc;
    while(bytes) {
        size_t n=bytes<piece ? bytes:piece;
        rc=tdefl_compress_buffer(&d,input,n,intermediate_flush ? TDEFL_FULL_FLUSH:TDEFL_NO_FLUSH);
        if(rc) { *used=o.used;return rc; }
        input+=n;bytes-=n;
    }
    rc=tdefl_compress_buffer(&d,NULL,0,TDEFL_FINISH);
    *used=o.used;return rc;
}
'''


class HuffmanPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='png16-huffman-path-')
        folder=Path(cls.temp.name);source=folder/'harness.c';source.write_text(HARNESS)
        library=folder/'huffman.dll'
        compiler=shutil.which('clang') or shutil.which('gcc')
        subprocess.run([compiler,'-shared','-O2','-std=c11','-Wall','-Wextra','-Werror',
            '-I',str(HERE),str(source),str(HERE/'png16_miniz.c'),'-o',str(library)],
            check=True,capture_output=True)
        cls.lib=C.CDLL(str(library))
        cls.lib.flags_status.argtypes=[C.c_int,C.c_int]
        cls.lib.stream.argtypes=[C.c_void_p,C.c_size_t,C.c_size_t,C.c_void_p,
            C.c_size_t,C.POINTER(C.c_size_t),C.c_int]

    @classmethod
    def tearDownClass(cls):
        close_library(cls.lib);del cls.lib;cls.temp.cleanup()

    def test_explicit_flag_rejects_unreviewed_strategies_and_output_api(self):
        fast=0x100000
        for checksum in (0,0x1000,0x2000,0x3000):
            self.assertEqual(self.lib.flags_status(fast|checksum,1),0)
            self.assertEqual(self.lib.flags_status(fast|checksum,0),-2)
        for other in (1,2,0xFFF,0x4000,0x8000,0x10000,0x20000,0x40000,0x80000,0x200000):
            self.assertEqual(self.lib.flags_status(fast|0x1000|other,1),-2)
        # The existing reviewed fast path and upstream Huffman-only flags still initialize.
        for old in (0x5001,0x45001,0x1000):
            self.assertEqual(self.lib.flags_status(old,1),0)

    def test_streaming_raw_fallback_dictionary_wrap_and_full_flush(self):
        rng=random.Random(0x483D)
        random_bytes=rng.randbytes(100003)
        for raw in (b'',b'\0',b'A'*100003,random_bytes):
            for piece in (1,257,2241,32768,65535):
                with self.subTest(length=len(raw),piece=piece):
                    source=C.create_string_buffer(raw);out=C.create_string_buffer(len(raw)*2+1024)
                    used=C.c_size_t()
                    self.assertEqual(self.lib.stream(source,len(raw),piece,out,len(out),C.byref(used),0),1)
                    encoded=out.raw[:used.value]
                    self.assertEqual(zlib.decompress(encoded),raw)
                    if raw==random_bytes:
                        self.assertEqual((encoded[2]>>1)&3,0,'Uniform random bytes should exercise stored fallback')
        raw=random_bytes[:6001];source=C.create_string_buffer(raw)
        for piece in (1,257,2241):
            out=C.create_string_buffer(100000);used=C.c_size_t()
            self.assertEqual(self.lib.stream(source,len(raw),piece,out,len(out),C.byref(used),1),1)
            self.assertEqual(zlib.decompress(out.raw[:used.value]),raw)

    def test_output_failure_stops_and_reports_failure(self):
        raw=random.Random(52).randbytes(100003);source=C.create_string_buffer(raw)
        for capacity in (0,1,128,22000):
            out=C.create_string_buffer(max(1,capacity));used=C.c_size_t()
            self.assertEqual(self.lib.stream(source,len(raw),2241,out,capacity,C.byref(used),0),-1)
            self.assertLessEqual(used.value,capacity)


if __name__=='__main__':unittest.main()
