"""Offline retained normal-failure header comparison; never accesses hardware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--slots',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--prior-bad',type=Path,required=True)
    p.add_argument('--analyzer',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    raw=a.slots.read_bytes();assert len(raw)==576
    header=raw[64:576];reference=a.reference.read_bytes();prior=a.prior_bad.read_bytes()
    assert len(header)==len(reference)==len(prior)==512
    sha=lambda d:hashlib.sha256(d).hexdigest()
    assert sha(reference)=='fa6a9fc6d2fdd48e921c7a3b2d794e78477934056895190cc78449c4fcb05598'
    assert sha(prior)=='99acb3960c29159b74c99b3b4c1a6700e09c5c85f7cacb63eb508e6a70eb0429'
    spec=importlib.util.spec_from_file_location('sector_models',a.analyzer)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.model_report(reference,header)
    report.update(hardware_access=False,slots_path=str(a.slots),slots_sha256=sha(raw),
        io_offset_bytes=64,io_bytes=512,reference_path=str(a.reference),
        prior_bad_path=str(a.prior_bad),prior_bad_sha256=sha(prior),
        identical_to_prior_bad=header==prior,prior_bad_differing_bytes=sum(x!=y for x,y in zip(header,prior)),
        analyzer_path=str(a.analyzer),analyzer_sha256=sha(a.analyzer.read_bytes()),
        caution='CRC-failed retained bytes remain untrusted. A matching deletion/CRC-prefix model is not a wire capture or electrical root-cause proof.')
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    a.out.with_suffix('.bin').write_bytes(header)
    print(json.dumps({k:report[k] for k in ('observed_sha256','identical','differing_bytes','identical_to_prior_bad','fitted_k','first_difference_byte')},indent=2))


if __name__=='__main__':main()
