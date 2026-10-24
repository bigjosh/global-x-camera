"""Optional literal optimization: exact historical bytes and bounded C emission.

All data is synthetic and stays in host memory. No hardware/device access.
"""
import ctypes as C
import hashlib,json,random,shutil,subprocess,tempfile,unittest,zlib
from pathlib import Path
from test_huffman_path import HARNESS
from test_png16 import HERE,close_library

PAIR_SOURCE=r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "png16_miniz.c"
#define CHECK(x) do { if(!(x)){fprintf(stderr,"failure line %u\n",__LINE__);return 1;} } while(0)
static tdefl_compressor d;
static unsigned seed=82;
static unsigned rnd(void){seed=seed*1664525U+1013904223U;return seed;}
static void put(unsigned value,unsigned len,unsigned *bits,unsigned *buffer,unsigned char **out,unsigned char *end) {
 *buffer|=value<<*bits;*bits+=len;
 while(*bits>=8){if(*out<end)*(*out)++=(unsigned char)*buffer;*buffer>>=8;*bits-=8;}
}
int main(void) {
 unsigned cases=0,extended_pairs=0;
 for(unsigned cap=0;cap<=48;cap++) for(unsigned pending=0;pending<8;pending++)
 for(unsigned count=0;count<=17;count++) for(unsigned trial=0;trial<3;trial++) {
  unsigned char actual[80],expected[80],literal[18],*p=d.m_lz_code_buf;
  memset(actual,0xa5,sizeof(actual));memset(expected,0xa5,sizeof(expected));
  for(unsigned i=0;i<257;i++) {
   unsigned n=rnd()%15+1;
   d.m_huff_code_sizes[0][i]=(unsigned char)n;
   d.m_huff_codes[0][i]=(uint16_t)(rnd()&((1U<<n)-1));
  }
  /* Force both the <=24 join boundary and 15+15 fallback frequently. */
  d.m_huff_code_sizes[0][0]=trial==0?12:15;d.m_huff_codes[0][0]=0xfff;
  d.m_huff_code_sizes[0][1]=trial==0?12:15;d.m_huff_codes[0][1]=0xaaa;
  for(unsigned i=0;i<count;i++) {
   if(i%8==0)*p++=0;
   literal[i]=i<2?(unsigned char)i:(unsigned char)rnd();*p++=literal[i];
  }
  d.m_pLZ_code_buf=p;d.m_pOutput_buf=actual+16;d.m_pOutput_buf_end=actual+16+cap;
  d.m_bits_in=pending;d.m_bit_buffer=rnd()&((1U<<pending)-1U);
  unsigned bits=d.m_bits_in,buffer=d.m_bit_buffer;unsigned char *out=expected+16;
  for(unsigned i=0;i<count;i++)put(d.m_huff_codes[0][literal[i]],d.m_huff_code_sizes[0][literal[i]],&bits,&buffer,&out,expected+16+cap);
  put(d.m_huff_codes[0][256],d.m_huff_code_sizes[0][256],&bits,&buffer,&out,expected+16+cap);
  int ok=tdefl_compress_huffman_lz_codes(&d);
  CHECK(ok==(out<expected+16+cap));CHECK(d.m_bits_in==bits && d.m_bit_buffer==buffer);
  CHECK(d.m_pOutput_buf-actual==out-expected);CHECK(memcmp(actual,expected,sizeof(actual))==0);
  ++cases;if(count>=2 && trial>0)++extended_pairs;
 }
 printf("cases=%u forced_long_pairs=%u\n",cases,extended_pairs);return 0;
}
'''

class OptimizedLiteralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='literal-optimized-')
        cls.folder=Path(cls.temp.name);parent=cls.folder/'parent';parent.mkdir()
        for name in ('png16.c','png16.h','png16_miniz.c','miniz_config.h'):
            shutil.copyfile(HERE/name,parent/name)
        shutil.copytree(HERE/'vendor',parent/'vendor')
        meta=json.loads((HERE/'vendor/miniz/LOCAL_PATCHES.json').read_text())
        record=next(x for x in meta['additional_patches'] if x['patch_file']=='huffman-batch-pair.patch')
        patch=(HERE/'vendor/miniz'/record['patch_file']).resolve()
        if hashlib.sha256(patch.read_bytes()).hexdigest()!=record['patch_sha256']:
            raise AssertionError('Optimization patch identity mismatch')
        subprocess.run(['git','-c','core.autocrlf=false','-c','core.eol=lf','apply','--reverse',str(patch)],
            cwd=parent/'vendor/miniz',check=True,capture_output=True)
        if hashlib.sha256((parent/'vendor/miniz/miniz_tdef.c').read_bytes()).hexdigest()!=record['files'][0]['before_sha256']:
            raise AssertionError('Pre-optimization source hash mismatch')
        harness=cls.folder/'stream.c';harness.write_text(HARNESS);cls.libs=[]
        for i,root in enumerate((parent,HERE)):
            path=cls.folder/f'lib{i}.dll'
            subprocess.run(['clang','-shared','-O2','-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(root),str(harness),str(root/'png16_miniz.c'),'-o',str(path)],check=True,capture_output=True)
            lib=C.CDLL(str(path));lib.stream.argtypes=[C.c_void_p,C.c_size_t,C.c_size_t,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t),C.c_int]
            cls.libs.append(lib)
    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:close_library(lib)
        cls.temp.cleanup()
    def compare(self,raw,piece,flush):
        source=C.create_string_buffer(raw);outputs=[]
        for lib in self.libs:
            out=C.create_string_buffer(max(100000,len(raw)*2+1024));used=C.c_size_t()
            self.assertEqual(lib.stream(source,len(raw),piece,out,len(out),C.byref(used),flush),1)
            outputs.append(out.raw[:used.value])
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(zlib.decompress(outputs[1]),raw)
    def test_exact_bytes_across_input_token_dictionary_boundaries(self):
        rng=random.Random(483)
        for raw in (b'',b'X',b'A'*100003,bytes(range(256))*391,rng.randbytes(100003)):
            for piece in (1,7,8,9,15,16,17,257,2241,21831,21839,32767,32768,65535):
                with self.subTest(size=len(raw),piece=piece):self.compare(raw,piece,0)
    def test_exact_full_flush_bytes(self):
        raw=random.Random(32).randbytes(6001)
        for piece in (1,7,8,9,257,2241):self.compare(raw,piece,1)
    def test_actual_c_pair_bounds_and_capacity_with_sanitizers(self):
        source=self.folder/'pair.c';source.write_text(PAIR_SOURCE);exe=self.folder/'pair.exe'
        subprocess.run(['clang','-O2','-std=c11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-fno-sanitize-recover=all',
            '-I',str(HERE),str(source),'-o',str(exe)],check=True,capture_output=True)
        run=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
        self.assertIn('cases=21168 forced_long_pairs=12544',run.stdout)
if __name__=='__main__':unittest.main()
