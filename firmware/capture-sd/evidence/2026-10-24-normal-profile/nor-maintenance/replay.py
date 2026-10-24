"""Offline NOR incident evidence replay. No hardware dependencies or operations."""
import hashlib
import json
from pathlib import Path
import struct
import zlib


def main():
    root = Path(__file__).resolve().parent
    def blob(name):
        return (root/name).read_bytes()
    def js(name):
        return json.loads(blob(name))
    def digest(data):
        return hashlib.sha256(data).hexdigest()
    def require(value, message):
        if not value:
            raise ValueError(message)
    manifest = js('manifest.json')
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        require(path.is_relative_to(root), 'Path escapes archive')
        require(digest(path.read_bytes()) == expected, 'Hash mismatch: '+name)
    originals = blob('inputs/v59-before.bin')
    desired = blob('inputs/v62-desired.bin')
    revised = blob('inputs/v62b-desired.bin')
    partial1 = blob('operations/nor-partial/nor.bin')
    partial2 = blob('operations/nor-partial-02/nor.bin')
    final = blob('operations/install-v62b-v2/readback.bin')
    require(all(len(p)==65536 for p in (originals,desired,revised,partial1,partial2,final)), 'NOR lengths')
    for name, current, target in [('install-v62',originals,desired),
                                   ('repair-v62',partial1,desired),
                                   ('install-v62b-v2',partial2,revised)]:
        prefix = 'operations/'+name+'/'
        request, status = js(prefix+'request.json'), js(prefix+'status.json')
        command = list(struct.unpack('<8I',blob(prefix+'command.bin')))
        require(command == request['command'], 'Command/request mismatch')
        require(command[1] == status['sequence'] and command[2:6] == [3,65536,0,0x57524954], 'Wrong write identity')
        require(command[6:] == [zlib.crc32(current), zlib.crc32(target)], 'Exact input CRC mismatch')
        require(request['current_sha256'] == digest(current) and request['desired_sha256']==digest(target), 'Exact input SHA mismatch')
        helper = 'programmer-v2' if name.endswith('-v2') else 'programmer-v1'
        hm = js('helpers/'+helper+'/build/manifest.json')
        require(request['helper_sha256'] == hm['binary_sha256'], 'Helper identity mismatch')
        status_bytes = [blob(str(p.relative_to(root)).replace('\\','/')) for p in (root/prefix).glob('status-*.bin')]
        expected = struct.pack('<56I',*(status[f] for f in hm['status_fields_in_word_order']))
        require(expected in status_bytes, 'Final status JSON lacks matching raw bytes')
    for name, addr, part in [('install-v62',0x6200,partial1),('repair-v62',0x7500,partial2)]:
        s=js('operations/'+name+'/status.json')
        require((s['result'],s['failure_stage'],s['failure_address'],s['failure_opcode'],s['cleanup_result'],s['flags']) == (16,8,addr,0x2B,0,47), 'Failure was altered')
        require(part[addr:addr+256] == desired[addr:addr+256], 'Later reported-page bytes differ')
    for name in ('nor-after-write-failure','nor-after-repair-failure','nor-v2-info'):
        s=js('operations/'+name+'/status.json')
        require((s['result'],s['flags'],s['nor_status'],s['nor_security'],s['jedec_id']) == (0,39,0,0,0xC2803A), 'Fresh INFO not idle')
    for helper, binary in [('programmer-v1','programmer'),('programmer-v2','programmer'),('readonly-reader','read')]:
        prefix='helpers/'+helper+'/'
        m=js(prefix+'build/manifest.json')
        require(digest(blob(prefix+'build/'+binary+'.bin'))==m['binary_sha256'], 'Built helper mismatch')
        for filename, expected in m['source_sha256'].items():
            require(digest(blob(prefix+'source/'+filename))==expected, 'Source mismatch')
    s=js('operations/install-v62b-v2/status.json')
    require((s['result'],s['cleanup_result'],s['flags'],s['pages_programmed'])==(0,0,47,184),'V2 failed')
    require(s['changed_mask']==s['erased_mask']==s['completed_mask']==32703,'Incomplete sector mask')
    require(final==revised and zlib.crc32(final)==s['final_crc'],'Final bytes mismatch')
    before=blob('operations/preflight-nor-following/nor.bin')
    after=blob('operations/following-after-v62b/nor.bin')
    require(len(before)==4096 and before==after,'Following guard changed')
    m=js('helpers/programmer-v2/build/manifest.json')
    raw=blob('operations/install-v62b-v2-diag02/completion.bin')
    diag=dict(zip(m['completion_diagnostic_fields_in_word_order'],struct.unpack('<26I',raw)))
    require(diag==js('operations/install-v62b-v2-diag02/result.json'),'Decoded diagnostic mismatch')
    require((diag['diag_magic'],diag['diag_schema'],diag['diag_sequence'],diag['diag_state'],diag['diag_terminal'])==(0x4E435032,1,241012,2,0x4E43444E),'Stale/nonterminal proof')
    require(diag['complete_calls']==198 and diag['wel_pending_reads']==0 and diag['first_failure_result']==0,'Unexpected completion evidence')
    require(blob('operations/install-v62b-v2-diag02/helper.bin')==blob('helpers/programmer-v2/build/programmer.bin'),'Live helper mismatch')
    print(json.dumps({'passed':True,'hashes_verified':len(manifest['files']),
        'original_failures_preserved':2,'full_final_bytes_verified':len(final),
        'following_guard_bytes':len(after),'v2_completion_checks':198,
        'v2_wel_pending_observations':0,'cause_established':False},indent=2))


if __name__=='__main__':
    main()
