"""Create an exact-policy adapter for O2/hoisted-literal/owned-CPACR MVE."""
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
base=HERE/'mve_run.py'
if hashlib.sha256(base.read_bytes()).hexdigest()!='45fec039f7d757859ea9cca019a0a6f5bb2678c6c800d6cbfe8f67db2871b238':raise ValueError('Reviewed base changed')
src=base.read_text()
def sub(old,new):
    global src
    if src.count(old)!=1:raise ValueError('Unique fragment missing: '+old)
    src=src.replace(old,new)
for old,new in (
 ('b23d4dd80b0b197755d69370e6696b18de4b026184134659f3bf62c24f02aded','2cb1b549758f086aaf02af5f2d832e6423e0ec7eb66e6eaf815fe6143bd79e91'),
 ('9f2f297e3aa6c68b80340df462a0014b3b5ead9dc560cad05530923c9b9a9d8a','5c6fe87250998a7f5778a187b8e45d874f9b22fe0c47a671a6f2a5a4683fe165'),
 ('MVE candidate02 is supported','MVE owned-CPACR local-O2 candidate01 is supported'),
 ('binary_bytes=16660', 'binary_bytes=20176'),
 ("optimization='Os'", "optimization='O2'"),
 ('bss_end=0x343541e0','bss_end=0x34354fa0'),
 ("'tmp/png-bench-20261024/huffman-os-v1'", "'tmp/bringup/png-row-study-20261024/scalar-local-o2-reference-01'"),
):sub(old,new)
sub("        report['reserved4']&0x00f00000!=0x00f00000 or\n        any(report['reserved'+str(i)] for i in range(5,53))):", """        report['reserved4']!=(report['reserved5']|0x00f00000) or
        report['reserved6']!=1 or report['reserved7']!=report['reserved5'] or
        any(report['reserved'+str(i)] for i in range(8,53))):""")
sub("    context=dict(registers=context,stack=stack,ccr=ccr,fpccr=fpccr)", """    cpacr,=struct.unpack('<I',b.upload(0xe000ed88,4,label+'-cpacr.bin'))
    context=dict(registers=context,stack=stack,ccr=ccr,fpccr=fpccr,cpacr=cpacr)""")
sub("    final=exact_code_context(b,code,final_park,'final')", """    final=exact_code_context(b,code,final_park,'final')
    if report['reserved5']!=context['cpacr'] or report['reserved7']!=final['cpacr']:
        raise ValueError('Actual initial/final CPACR differs from ownership proof')""")
sub("        adapter_sha256=sha(Path(__file__).read_bytes()),normalization_checked_after_C=True,", "        adapter_sha256=sha(Path(__file__).read_bytes()),normalization_checked_after_C=True,cpacr_restored_each_invocation=True,")
out=HERE/'mve_owned_o2_run.py';out.write_text(src)
test=(HERE/'test_mve_runner.py').read_text().replace("HERE/'mve_run.py'", "HERE/'mve_owned_o2_run.py'").replace("HERE/'mve-bench-02'", "HERE/'mve-local-o2-owned-01'")
test=test.replace('reserved2=0x343b0000,reserved3=0x343a0000,reserved4=0x00f00000)', 'reserved2=0x343b0000,reserved3=0x343a0000,reserved4=0x00f00000,reserved6=1)')
test=test.replace("0xe000ef34:bytes(4),r.LOAD", "0xe000ef34:bytes(4),0xe000ed88:bytes(4),r.LOAD")
test=test.replace("('reserved4',0),('reserved5',1)", "('reserved4',0),('reserved5',1),('reserved6',0),('reserved7',1),('reserved8',1)")
needle='    def test_scalar_protocol_unmodified(self):'
assert test.count(needle)==1
test=test.replace(needle,"""    def test_initial_cpacr_preserved_exactly_in_proof(self):
        a,q=ready()
        for initial in (0,0x00300000,0x00f00000,0x00000300):
            b=dict(a,reserved5=initial,reserved4=initial|0x00f00000,reserved7=initial)
            self.assertEqual(p.validate(b,q),b)
            b['reserved7']^=1
            with self.assertRaises(ValueError):p.validate(b,q)
"""+needle)
(HERE/'test_mve_owned_o2_runner.py').write_text(test)
print(out);print(hashlib.sha256(out.read_bytes()).hexdigest())
