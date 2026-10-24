"""Pin the reviewed owned-CPACR runner to the frozen batch8 MVE experiment."""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
base=HERE/'mve_owned_o2_run.py'
if hashlib.sha256(base.read_bytes()).hexdigest()!='f4e8a38c7c7a7598f99a7b44a5e0f0b91703e129d99e2033d40f45ccda59ebaa':raise ValueError('Owned adapter changed')
src=base.read_text()
for old,new in (
 ('2cb1b549758f086aaf02af5f2d832e6423e0ec7eb66e6eaf815fe6143bd79e91','f4e5f5c78ab70eb1cfc5defda9d097ecf6c7719d5fa1367075ecc21bb99e453b'),
 ('5c6fe87250998a7f5778a187b8e45d874f9b22fe0c47a671a6f2a5a4683fe165','1ac5fbc955ba5710a43be03dd961d68d3f88abd32a4f3e14899f2290ee970dd3'),
 ('MVE owned-CPACR local-O2 candidate01 is supported','MVE owned-CPACR batch8-O2 candidate01 is supported'),
 ('binary_bytes=20176','binary_bytes=20472'),
 ('bss_end=0x34354fa0','bss_end=0x343550c0'),
 ("'tmp/bringup/png-row-study-20261024/scalar-local-o2-reference-01'","'tmp/png-bench-20261024/huffman-batch8-o2-v1'"),
):
    if src.count(old)!=1:raise ValueError('Unique fragment missing: '+old)
    src=src.replace(old,new)
out=HERE/'mve_batch8_o2_run.py';out.write_text(src)
tests=(HERE/'test_mve_owned_o2_runner.py').read_text().replace("HERE/'mve_owned_o2_run.py'", "HERE/'mve_batch8_o2_run.py'").replace("HERE/'mve-local-o2-owned-01'", "HERE/'mve-batch8-o2-owned-01'")
(HERE/'test_mve_batch8_o2_runner.py').write_text(tests)
print(out);print(hashlib.sha256(out.read_bytes()).hexdigest())
