"""Fail-closed host handling of explicitly skipped normal-profile checks."""
import struct
import unittest
import bench


def fixture(diagnostic=False, saving=True):
    w=[0]*128
    values=dict(magic=0x53564431,schema=2,words=128,state=2,operation=1 if saving else 4,
        mode=1,cpu_hz=400000000,media_idle=1,width=1120,height=1364,
        frame_bytes=bench.FRAME_BYTES,buffer_bytes=32768,buffer_address=bench.LOAD+4096,
        stack_canary=0x5354414B,initial_msplim=0x343A0000,nonce=77)
    for k,v in values.items(): w[bench.FIELDS.index(k)]=v
    w[63]=0x444F4E45; w[68]=1; w[69]=4; w[70]=0x201
    w[16]=180; w[75]=200; w[79]=int(diagnostic)
    w[80]=(0x1FF if diagnostic else 0x1E1) if saving else (0xB0 if diagnostic else 0xA0)
    if saving:
        w[18]=120; w[32]=1364; w[36]=99
        w[89]=100; w[91]=10; w[93]=40; w[95]=10; w[97]=30; w[99]=10
        w[101]=80; w[103]=40; w[105]=40; w[107]=30; w[109]=20
        w[111]=0x7F if diagnostic else 0x1F
        if diagnostic: w[38]=w[39]=w[77]=w[112]=123; w[78]=1
    m=dict(buffer_address=hex(bench.LOAD+4096),cache_report_extension=1,
        data_cache_enabled=True,report_schema=2,fine_timing_extension=1,
        diagnostics_profile='diagnostic' if diagnostic else 'normal',expensive_checks=diagnostic)
    return bench.decode_report(struct.pack('<128I',*w)),m


class ProfileReport(unittest.TestCase):
    def test_both_profiles_and_operations(self):
        for diagnostic in (False,True):
            for saving in (False,True):
                r,m=fixture(diagnostic,saving)
                bench.validate_success(r,m)

    def test_normal_does_not_accept_fabricated_diagnostics(self):
        r,m=fixture()
        for key in ('fnv_before','fnv_after','postclean_fnv','postclean_validated',
                    'postclean_validate','posthash','stack_scan','stack_used','receiver_fnv'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bench.validate_success(dict(r,**{key:1}),m)

    def test_profile_and_completion_fail_closed(self):
        r,m=fixture()
        for key,value in (('schema',1),('profile',1),('checks_performed',0x1FF),
                ('checks_performed',0x1C1),('receiver_flags',0x7F),('media_idle',0),
                ('terminal',0),('state',1),('final_ccr',0x20000),('stack_canary',0)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                bench.validate_success(dict(r,**{key:value}),m)
        with self.assertRaises(ValueError): bench.validate_success(r,dict(m,report_schema=1))
        with self.assertRaises(ValueError): bench.validate_success(r,dict(m,expensive_checks=True))

    def test_diagnostic_requires_actual_matching_hashes(self):
        r,m=fixture(True)
        for key,value in (('postclean_validated',0),('postclean_fnv',9),
                ('receiver_fnv',9),('fnv_after',9),('checks_performed',0x1E1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                bench.validate_success(dict(r,**{key:value}),m)

    def test_timing_partition_and_nonimage_claims(self):
        r,m=fixture()
        for key,value in (('png_clock_calls',0),('png_clock_error',1),('png_other',11),
                ('png_deflate_output',39),('png_framing_callback',29),('flush',1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                bench.validate_success(dict(r,**{key:value}),m)
        r,m=fixture(False,False)
        with self.assertRaises(ValueError): bench.validate_success(dict(r,png_total=1),m)


if __name__=='__main__': unittest.main()
