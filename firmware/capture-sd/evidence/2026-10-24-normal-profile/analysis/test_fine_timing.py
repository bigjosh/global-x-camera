import unittest
import struct
from fine_timing import analyze_report, validate_raw_report


def fixture():
    return dict(magic=0x53564431,schema=2,words=128,state=2,operation=1,result=0,
        terminal=0x444F4E45,cpu_hz=400000000,media_idle=1,card_error=0,
        fs_result=0,png_result=0,png_clock_error=0,width=1120,height=1364,
        frame_bytes=3055360,profile=1,checks_performed=0x1FF,png_clock_calls=20,
        rows=1364,final_ccr=0x201,fnv_before=55,fnv_after=55,postclean_fnv=55,
        postclean_validated=1,total=900,complete=1000,init=100,mount=20,
        validate=10,open=50,encode=500,finish=100,flush=25,posthash=20,
        deinit=10,stack_scan=5,cleanup=10,final_check=5,postclean_validate=20,
        png_total=480,png_conversion=50,png_deflate=200,png_framing=30,
        png_callback=180,png_other=20,png_deflate_inclusive=400,
        png_deflate_output=200,png_framing_inclusive=205,png_framing_callback=175,
        callback=170)


class FineTimingTests(unittest.TestCase):
    def test_json_field_cannot_disagree_with_raw_even_if_raw_words_match(self):
        r={'raw_words':[0]*128,'magic':1}
        with self.assertRaisesRegex(ValueError,'Decoded raw field differs: magic'):
            validate_raw_report(r,struct.pack('<128I',*r['raw_words']))

    def test_exact_disjoint_partition_does_not_double_count_flush(self):
        a=analyze_report(fixture()); d=a['disjoint_cycles']
        self.assertEqual(d['final_partial_buffer_flush'],25)
        self.assertEqual(d['file_commit_and_close_after_flush'],75)
        self.assertEqual(d['pre_cleanup_bookkeeping'],90)
        self.assertEqual(d['final_report_snapshot_led_and_icache_bookkeeping'],60)
        self.assertEqual(sum(d.values()),1000)

    def test_nested_png_is_not_added_twice(self):
        a=analyze_report(fixture());d=a['disjoint_cycles']
        self.assertEqual(d['deflate_including_adler_excluding_output_subtree'],200)
        self.assertEqual(d['png_framing_crc_and_headers_excluding_callbacks'],30)
        self.assertEqual(d['encoder_call_wrapper'],20)

    def test_refuses_stale_failed_active_unknown_or_bad_timing(self):
        for k,v in [('state',1),('result',-1),('terminal',0),('media_idle',0),
                    ('profile',2),('checks_performed',0),('png_clock_error',1),
                    ('png_total',481),('png_deflate_output',201),('callback',181),
                    ('flush',101),('total',799),('complete',900),('encode',True)]:
            r=fixture();r[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):analyze_report(r)

    def test_normal_skips_are_explicit(self):
        r=fixture();r.update(profile=0,checks_performed=0x1E1,fnv_before=0,
            fnv_after=0,postclean_fnv=0,postclean_validated=0,posthash=0,
            postclean_validate=0,stack_scan=0,stack_used=0)
        self.assertEqual(analyze_report(r)['profile'],'normal')
        r['fnv_before']=55
        with self.assertRaises(ValueError):analyze_report(r)


if __name__=='__main__':unittest.main()
