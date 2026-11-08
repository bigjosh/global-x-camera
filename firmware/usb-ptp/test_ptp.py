"""Native tests of the actual PTP dispatcher, storage and PNG implementation.

The USB transport is replaced with a byte-collecting mock. No target or USB
device is opened. WPD host/device interoperability remains hardware work.
"""
import ctypes as C
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('photo_store_tests',HERE/'storage/test_photo_store.py')
storage=importlib.util.module_from_spec(spec);spec.loader.exec_module(storage)


def containers(data):
    out=[];pos=0
    while pos<len(data):
        n,kind,code,tid=struct.unpack_from('<IHHI',data,pos)
        if n<12 or pos+n>len(data):
            raise AssertionError('truncated PTP container')
        out.append((kind,code,tid,data[pos+12:pos+n]));pos+=n
    return out


def ptp_string(data,offset):
    count=data[offset]
    return data[offset+1:offset+1+count*2].decode('utf-16-le').rstrip('\0'),offset+1+count*2


class PtpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='gx-ptp-protocol-')
        native=Path(cls.temp.name)/'ptp.dll'
        compiler=shutil.which('gcc') or shutil.which('clang')
        if not compiler:raise RuntimeError('native C compiler required')
        subprocess.run([compiler,'-shared','-std=c11','-O2','-Wall','-Wextra','-Werror',
            str(HERE/'ptp.c'),str(HERE/'storage/photo_store.c'),str(HERE/'test_ptp_transport_mock.c'),
            str(HERE/'thumbnail/thumbnail_bmp.c'),
            '-o',str(native)],check=True)
        cls.lib=C.CDLL(str(native))
        cls.lib.photo_store_open.argtypes=[C.POINTER(storage.Store),C.POINTER(storage.Io),C.c_uint64,C.c_uint32]
        cls.lib.ptp_init.argtypes=[C.POINTER(storage.Store),C.c_void_p]
        cls.lib.mock_feed.argtypes=[C.c_void_p,C.c_uint32]
        cls.lib.mock_queue.argtypes=[C.c_void_p,C.c_uint32]
        cls.lib.mock_cancel.argtypes=[C.c_uint32]
        cls.lib.mock_data.restype=C.c_void_p;cls.lib.mock_events.restype=C.c_void_p
        cls.lib.mock_cancel_on_tx.argtypes=[C.c_uint32,C.c_uint32]
        cls.lib.mock_status.restype=C.c_uint16
        cls.lib.mock_abort_failures.argtypes=[C.c_uint32]
        cls.lib.mock_block_on_tx.argtypes=[C.c_uint32]
        cls.lib.mock_reset_on_tx.argtypes=[C.c_uint32]

    @classmethod
    def tearDownClass(cls):
        if hasattr(C,'windll'):
            handle=cls.lib._handle;del cls.lib;C.windll.kernel32.FreeLibrary(C.c_void_p(handle))
        cls.temp.cleanup()

    def setUp(self):
        self.card=storage.Card()
        self.card.put(0);self.card.put(2,legacy=True)
        self.store=storage.Store()
        self.frame=(C.c_uint32*(storage.SIZE//4))()
        self.assertEqual(self.lib.photo_store_open(C.byref(self.store),C.byref(self.card.io),len(self.card.data)//512,255),0)
        self.assertEqual(self.lib.ptp_init(C.byref(self.store),self.frame),0)
        self.lib.mock_clear();self.tid=0

    def command(self,op,*args,clear=True):
        if clear:self.lib.mock_clear()
        self.tid+=1
        p=struct.pack('<IHHI',12+len(args)*4,1,op,self.tid)+struct.pack('<'+'I'*len(args),*args)
        self.lib.mock_feed(p,len(p))
        return C.string_at(self.lib.mock_data(),self.lib.mock_size())

    def response(self,data,code=0x2001):
        cs=containers(data)
        self.assertEqual(cs[-1][:3],(3,code,self.tid))
        return cs

    def open(self):self.response(self.command(0x1002,1))
    def events(self):return containers(C.string_at(self.lib.mock_events(),self.lib.mock_event_size()))

    def test_device_info_supported_operations_and_no_partial_download(self):
        cs=self.response(self.command(0x1001))
        data=cs[0][3]
        self.assertEqual(cs[0][0:2],(2,0x1001))
        _,pos=ptp_string(data,8);pos+=2
        n=struct.unpack_from('<I',data,pos)[0];pos+=4
        ops=struct.unpack_from('<'+'H'*n,data,pos)
        self.assertIn(0x1009,ops);self.assertIn(0x100B,ops)
        self.assertNotIn(0x101B,ops)
        self.open();self.response(self.command(0x101B,1,0,100),0x2005)

    def test_session_and_bad_parameters(self):
        self.response(self.command(0x1004),0x2003)
        self.response(self.command(0x1002,0),0x201D)
        self.open();self.response(self.command(0x1002,2),0x201E)
        self.response(self.command(0x1005,0xDEADBEEF),0x2008)
        self.response(self.command(0x1007,0x10001,0x3801,0),0x2014)
        self.response(self.command(0x1003))
        self.response(self.command(0x1004),0x2003)

    def test_handles_holes_object_info_and_no_dates(self):
        self.open()
        cs=self.response(self.command(0x1007,0xFFFFFFFF,0,0))
        self.assertEqual(struct.unpack('<3I',cs[0][3]),(2,1,3))
        cs=self.response(self.command(0x1008,1))
        data=cs[0][3]
        self.assertEqual(struct.unpack_from('<IHHI',data,0),(0x10001,0x380B,0,storage.PNG_SIZE))
        self.assertEqual(struct.unpack_from('<3I',data,26),(1120,1364,16))
        name,pos=ptp_string(data,52)
        self.assertEqual(name,'GX_0000001.png')
        for _ in range(3):
            text,pos=ptp_string(data,pos);self.assertEqual(text,'')
        self.assertEqual(pos,len(data))
        self.response(self.command(0x1008,2),0x2009)
        self.assertEqual(self.card.writes,[])

    def test_get_object_has_exact_png_and_reads_fresh_without_deleting(self):
        self.open();self.card.reads.clear()
        cs=self.response(self.command(0x1009,1))
        self.assertEqual(cs[0][:3],(2,0x1009,self.tid))
        png=cs[0][3]
        self.assertEqual(len(png),storage.PNG_SIZE)
        self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(sum(n for _,n in self.card.reads),storage.STRIDE)
        self.assertEqual(self.card.writes,[])
        self.card.data[1234]^=128
        cs2=self.response(self.command(0x1009,1))
        self.assertNotEqual(cs2[0][3],png)

    def test_thumbnail_describes_and_streams_this_photo(self):
        self.open()
        cs=self.response(self.command(0x1008,3))
        self.assertEqual(struct.unpack_from('<HIII',cs[0][3],12),(0x3804,59958,128,156))
        self.card.reads.clear()
        cs=self.response(self.command(0x100A,3))
        self.assertEqual(cs[0][:3],(2,0x100A,self.tid))
        bmp=cs[0][3]
        self.assertEqual(len(bmp),59958)
        self.assertEqual(bmp[:2],b'BM')
        self.assertEqual(struct.unpack_from('<iiHH',bmp,18),(128,156,1,24))
        self.assertEqual(bmp[54:],b'\x37'*(128*156*3))
        self.assertEqual(sum(n for _,n in self.card.reads),storage.STRIDE)
        self.assertEqual(self.card.writes,[])

    def test_new_read_warning_updates_filename_and_event_after_response(self):
        self.open();self.card.bad.add(100)
        cs=self.response(self.command(0x1009,1))
        self.assertIn(b'RECOVERED',cs[0][3])
        self.assertEqual(self.events(),[(4,0x4007,self.tid,struct.pack('<I',1))])
        self.card.bad.clear()
        cs=self.response(self.command(0x1008,1))
        name,_=ptp_string(cs[0][3],52)
        self.assertEqual(name,'GX_0000001_RECOVERED.png')
        self.assertEqual(self.events(),[])
        # A successful later download still reads new pixels and reports its
        # own current read outcome, without fabricating another failed attempt.
        cs=self.response(self.command(0x1009,1))
        self.assertIn(b'no reported read errors',cs[0][3])
        self.assertEqual(self.events(),[])

    def test_header_read_error_still_exports_known_layout_best_effort(self):
        self.open();self.card.bad.add(0)
        cs=self.response(self.command(0x1009,1))
        self.assertEqual(len(cs[0][3]),storage.PNG_SIZE)
        self.assertIn(b'RECOVERED',cs[0][3])
        self.assertIn(b'zero_filled_sectors=1',cs[0][3])
        self.assertTrue(self.events())

    def test_single_photo_delete_optional_format_and_no_bulk_delete(self):
        self.open()
        left=bytes(self.card.data[:storage.SIZE])
        self.response(self.command(0x100B,0xFFFFFFFF,0),0x201D)
        self.assertEqual(self.card.writes,[])
        self.response(self.command(0x100B,3))
        self.assertEqual(self.events(),[(4,0x4003,self.tid,struct.pack('<I',3))])
        self.assertEqual(self.card.data[:storage.SIZE],left)
        cs=self.response(self.command(0x1007,0x10001,0,0))
        self.assertEqual(struct.unpack('<2I',cs[0][3]),(1,1))
        self.response(self.command(0x100B,1,0))
        self.response(self.command(0x100B,1),0x2009)

    def test_failed_delete_retains_catalogue_handle(self):
        self.open();self.card.fail_write=2
        self.response(self.command(0x100B,1),0x2002)
        cs=self.response(self.command(0x1007,0x10001,0,0))
        self.assertEqual(struct.unpack('<3I',cs[0][3]),(2,1,3))
        self.assertEqual(self.events(),[])

    def test_late_delete_failure_reconciles_only_after_safe_recovery(self):
        self.open();self.card.fail_sync=2
        self.response(self.command(0x100B,1),0x2002)
        self.assertEqual(self.events(),[(4,0x4003,self.tid,struct.pack('<I',1))])
        self.assertEqual(self.card.recoveries,1)
        cs=self.response(self.command(0x1007,0x10001,0,0))
        self.assertEqual(struct.unpack('<2I',cs[0][3]),(1,3))

    def test_late_delete_with_uncertain_transport_keeps_catalogue(self):
        self.open();self.card.fail_sync=2;self.card.recovery_ok=False
        self.response(self.command(0x100B,1),0x2002)
        self.assertEqual(self.events(),[])
        cs=self.response(self.command(0x1007,0x10001,0,0))
        self.assertEqual(struct.unpack('<3I',cs[0][3]),(2,1,3))

    def test_host_cancel_during_download_sends_no_bulk_response(self):
        self.open();self.lib.mock_clear()
        self.lib.mock_cancel_on_tx(2,self.tid+1)
        data=self.command(0x1009,1,clear=False)
        self.assertEqual(len(data),32768)
        self.assertGreater(self.lib.mock_aborts(),0)
        self.assertEqual(self.card.writes,[])
        self.response(self.command(0x1006,0x10001,0,0))

    def test_cancel_during_response_finishes_cleanup_and_returns_ok_status(self):
        self.open();self.lib.mock_clear()
        self.lib.mock_cancel_on_tx(2,self.tid+1)
        self.command(0x1004,clear=False)
        self.assertEqual(self.lib.mock_status(),0x2001)
        self.assertEqual(self.lib.mock_aborts(),1)
        self.response(self.command(0x1004))

    def test_failed_response_cancel_cleanup_blocks_next_command_until_retry(self):
        self.open();self.lib.mock_clear();self.lib.mock_abort_failures(2)
        self.lib.mock_cancel_on_tx(2,self.tid+1)
        self.command(0x1004,clear=False)
        self.assertEqual(self.lib.mock_status(),0x2019)
        before=self.lib.mock_size();self.tid+=1
        command=struct.pack('<IHHIIII',24,1,0x1006,self.tid,0x10001,0,0)
        self.lib.mock_queue(command,len(command))
        self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2019)
        self.assertEqual(self.lib.mock_size(),before)
        self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2001)
        self.assertEqual(self.lib.mock_size(),before)
        self.lib.ptp_poll()
        data=C.string_at(self.lib.mock_data(),self.lib.mock_size())[before:]
        self.response(data)

    def test_class_reset_cleanup_retries_before_reporting_idle(self):
        self.open();self.lib.mock_clear();self.lib.mock_abort_failures(2)
        self.lib.mock_usb_reset();self.assertEqual(self.lib.mock_status(),0x2019)
        self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2019)
        self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2001)
        self.response(self.command(0x1004),0x2003)

    def test_timeout_keeps_data_and_response_buffers_until_abort_succeeds(self):
        for nth in (1,2):
            with self.subTest(transmit=nth):
                self.open();self.lib.mock_clear();self.lib.mock_abort_failures(2)
                self.lib.mock_block_on_tx(nth)
                self.command(0x1004,clear=False)
                self.assertEqual(self.lib.mock_status(),0x2019)
                self.assertTrue(self.lib.mock_owned_unchanged())
                self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2019)
                self.assertTrue(self.lib.mock_owned_unchanged())
                self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2001)
                self.assertFalse(self.lib.mock_owned_unchanged())
                self.response(self.command(0x1003))

    def test_class_reset_during_response_uses_the_same_cleanup_gate(self):
        self.open();self.lib.mock_clear();self.lib.mock_abort_failures(1)
        self.lib.mock_reset_on_tx(2)
        self.command(0x1004,clear=False)
        self.assertEqual(self.lib.mock_status(),0x2019)
        self.lib.ptp_poll();self.assertEqual(self.lib.mock_status(),0x2001)
        self.response(self.command(0x1004),0x2003)

    def test_physical_disconnect_invalidates_failed_cleanup_ownership(self):
        self.open();self.lib.mock_clear();self.lib.mock_abort_failures(10)
        self.lib.mock_block_on_tx(2)
        self.command(0x1004,clear=False)
        self.assertTrue(self.lib.mock_owned_unchanged())
        self.lib.mock_physical_disconnect()
        self.assertFalse(self.lib.mock_owned_unchanged())
        self.assertEqual(self.lib.mock_status(),0x2001)
        self.lib.mock_reconnect();self.response(self.command(0x1004),0x2003)

    def test_malformed_container_and_usb_reset(self):
        self.open()
        malformed=struct.pack('<IHHI',16,1,0x1004,100)
        self.lib.mock_clear();self.lib.mock_feed(malformed,len(malformed))
        self.assertEqual(self.lib.mock_size(),0)
        self.assertGreater(self.lib.mock_aborts(),0)
        self.lib.mock_usb_reset()
        self.response(self.command(0x1004),0x2003)
        self.open();self.response(self.command(0x1004))

    def test_cancel_queued_command_survives_dispatch(self):
        self.open();self.lib.mock_clear();self.tid+=1
        p=struct.pack('<IHHII',16,1,0x1009,self.tid,1)
        self.lib.mock_queue(p,len(p));self.lib.mock_cancel(self.tid)
        self.lib.ptp_poll()
        data=C.string_at(self.lib.mock_data(),self.lib.mock_size())
        self.assertEqual(data,b'')
        self.response(self.command(0x1006,0x10001,0,0))

    def test_stale_cancel_does_not_cancel_a_later_download(self):
        self.open();self.lib.mock_cancel(self.tid)
        cs=self.response(self.command(0x1009,1))
        self.assertEqual(len(cs[0][3]),storage.PNG_SIZE)


if __name__=='__main__':unittest.main()
