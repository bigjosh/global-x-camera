"""Pin owned-CPACR execution policy to final noinline paired-emitter candidate."""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
base=HERE/'mve_owned_o2_run.py'
if hashlib.sha256(base.read_bytes()).hexdigest()!='f4e8a38c7c7a7598f99a7b44a5e0f0b91703e129d99e2033d40f45ccda59ebaa':raise ValueError('Owned adapter changed')
src=base.read_text()
for old,new in (
 ('2cb1b549758f086aaf02af5f2d832e6423e0ec7eb66e6eaf815fe6143bd79e91','eb59e3b724bdff4e361179aeb7b24c540594afcd0ec838895f817e7cf0616543'),
 ('5c6fe87250998a7f5778a187b8e45d874f9b22fe0c47a671a6f2a5a4683fe165','6f2997efa6e21872e4a940e3616f8cce5a5b33618b2b7cf90fd14402954c5d2a'),
 ('MVE owned-CPACR local-O2 candidate01 is supported','MVE owned-CPACR paired-noinline-O2 candidate01 is supported'),
 ('binary_bytes=20176','binary_bytes=20976'),
 ('bss_end=0x34354fa0','bss_end=0x343552c0'),
 ("'tmp/bringup/png-row-study-20261024/scalar-local-o2-reference-01'","'tmp/png-bench-20261024/huffman-pair-noinline-o2-v2'"),
):
    if src.count(old)!=1:raise ValueError('Unique fragment missing: '+old)
    src=src.replace(old,new)
out=HERE/'mve_pair_o2_run.py';out.write_text(src)
tests=(HERE/'test_mve_owned_o2_runner.py').read_text().replace("HERE/'mve_owned_o2_run.py'", "HERE/'mve_pair_o2_run.py'").replace("HERE/'mve-local-o2-owned-01'", "HERE/'mve-pair-noinline-o2-owned-01'")
(HERE/'test_mve_pair_o2_runner.py').write_text(tests)
print(out);print(hashlib.sha256(out.read_bytes()).hexdigest())
