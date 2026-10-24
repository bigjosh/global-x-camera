"""Freeze the optional scalar Huffman promotion; never accesses hardware."""
from pathlib import Path
import argparse
from add_trial import ROOT,HERE,read,sha,dump


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--encoding-repair',action='store_true')
    args=p.parse_args()
    source=ROOT/'tmp/png-bench-20261024/promotion-paired-v1'
    if args.encoding_repair:
        repair=read(source/'encoding-repair.json')
        original=HERE/'canonical-promotion/source/README.md'
        current=ROOT/'firmware/png-encoder/README.md'
        assert sha(original.read_bytes())==repair['before_sha256']
        assert sha(current.read_bytes())==repair['after_sha256']
        assert repair['binary_source_changed'] is False
        out=HERE/'canonical-promotion/encoding-repair';out.mkdir(exist_ok=False)
        files=[]
        for path in (source/'encoding-repair.json',source/'post-promotion-validation.json',current):
            raw=path.read_bytes();(out/path.name).write_bytes(raw)
            files.append(dict(original_path=path.relative_to(ROOT).as_posix(),archived_path=path.name,
                              bytes=len(raw),sha256=sha(raw)))
        dump(out/'archive.json',dict(schema=1,files=files,scope='UTF-8 documentation repair only; original frozen promotion retained',
                                    hardware_accessed_by_archiver=False,binary_source_changed=False))
        print({'encoding_repair_archived':True});return
    validation=read(source/'post-promotion-validation.json')
    assert validation['passed'] and validation['canonical_tests']==29
    assert validation['production_SAVE_default']==1
    assert validation['SAVE_mode3_not_enabled'] and validation['MVE_not_promoted']
    expected='6f2997efa6e21872e4a940e3616f8cce5a5b33618b2b7cf90fd14402954c5d2a'
    binary=source/'canonical-o2-build/bench.bin'
    assert sha(binary.read_bytes())==validation['canonical_O2_binary_sha256']==expected
    assert binary.read_bytes()==(HERE/'trials/pair-o2/build/bench.bin').read_bytes()
    assert sha((source/'canonical-tests.log').read_bytes())==validation['canonical_test_log_sha256']
    out=HERE/'canonical-promotion';out.mkdir(exist_ok=False);files=[]
    def copy(path,relative):
        raw=path.read_bytes();dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append(dict(original_path=path.relative_to(ROOT).as_posix(),archived_path=relative.as_posix(),
                          bytes=len(raw),sha256=sha(raw)))
    for name in ('applied.json','post-promotion-validation.json','canonical-tests.log'):
        copy(source/name,Path(name))
    for item in validation['source_files']:
        path=ROOT/item['path'];assert sha(path.read_bytes())==item['after_sha256']
        copy(path,Path('source')/path.relative_to(ROOT/'firmware/png-encoder'))
    for name in ('manifest.json','bench.bin'):
        copy(source/'canonical-o2-build'/name,Path('build')/name)
    dump(out/'archive.json',dict(schema=1,files=files,hardware_accessed_by_archiver=False,
        canonical_binary_byte_identical_to_qualified_scalar=True,binary_sha256=expected,
        independent_review=dict(all_seven_after_hashes_checked=True,normalized_frozen_source_equal=True,
            supplier_patch_reversal_test_passed=True,old_mode_output_golden_test_passed=True),
        limits=['Optional mode-3 encoder source only; installed firmware and SAVE default remain unchanged',
                'MVE remains experimental and is not promoted',
                'Measured mode-1 CPU regression is retained; output byte equality does not imply equal speed']))
    print({'passed':True,'files':len(files),'binary_sha256':expected})


if __name__=='__main__':main()
