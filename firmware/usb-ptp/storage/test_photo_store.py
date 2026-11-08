"""Offline tests of the actual portable C backend; no device access.

Uses a memory-backed card, injected I/O failures and independent PNG/zlib/TIFF
parsing. This does not qualify SD power-loss behavior or USB host integration.
"""
from pathlib import Path
import ctypes as C
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parent
STRIDE, SECTOR, WIDTH, HEIGHT = 3730, 512, 1120, 1364
SIZE, IMAGE, PREFIX = STRIDE * SECTOR, 1909600, 156
PNG_SIZE = 8 + 25 + 13 + 12 + 556 + 12 + 2 + HEIGHT * (5 + 2241) + 4 + 12
READ = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint32)
WRITE = READ
CALL = C.CFUNCTYPE(C.c_int, C.c_void_p)


class Io(C.Structure):
    _fields_ = [("user", C.c_void_p), ("read", READ), ("write", WRITE),
                ("sync", CALL), ("recover", CALL), ("service", CALL)]


class Info(C.Structure):
    _fields_ = [(k, C.c_uint32) for k in ("handle", "slot_index", "slot_lba", "start_magic",
                "image_offset", "flags", "read_errors", "unreadable_sectors", "first_bad_lba")]
    _fields_ += [("metadata", C.c_uint8 * 152)]


class Store(C.Structure):
    _fields_ = [("io", Io)] + [(k, C.c_uint32) for k in ("slot_count", "erased_byte",
                 "scanned_slots", "known_objects", "unknown_occupied", "unreadable_headers")]
    _fields_ += [("scratch", C.c_uint32 * (32 * 128))]


VISIT = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(Info))
EMIT = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_size_t)


class Card:
    def __init__(self, slots=3, erased=255):
        self.data = bytearray([erased]) * (slots * SIZE + 257 * SECTOR)
        self.slots, self.erased = slots, erased
        self.reads, self.writes, self.events = [], [], []
        self.bad = set()
        self.fail_burst_once = False
        self.recovery_ok = True
        self.recoveries = 0
        self.fail_write = 0
        self.cancel_after = None
        self.service_calls = 0
        self.fail_sync = 0
        self.syncs = 0
        self.cb = [READ(self.read), WRITE(self.write), CALL(self.sync),
                   CALL(self.recover), CALL(self.service)]
        self.io = Io(None, *self.cb)

    def read(self, _, lba, out, count):
        self.reads.append((lba, count))
        if lba + count > len(self.data) // SECTOR:
            raise AssertionError("out-of-range read")
        if (self.fail_burst_once and count > 1) or any(n in self.bad for n in range(lba, lba+count)):
            self.fail_burst_once = False
            C.memset(out, 0xA5, count * SECTOR)  # untrusted failed DMA must never escape
            return 0
        C.memmove(out, bytes(self.data[lba * SECTOR:(lba+count) * SECTOR]), count * SECTOR)
        return 1

    def write(self, _, lba, buf, count):
        self.writes.append((lba, count))
        self.events.append(("write", lba, count))
        if self.fail_write and len(self.writes) == self.fail_write:
            return 0
        if lba + count > len(self.data) // SECTOR:
            raise AssertionError("out-of-range write")
        self.data[lba * SECTOR:(lba+count) * SECTOR] = C.string_at(buf, count * SECTOR)
        return 1

    def sync(self, _):
        self.syncs += 1
        self.events.append(("sync",))
        return int(self.syncs != self.fail_sync)

    def recover(self, _):
        self.recoveries += 1
        return int(self.recovery_ok)

    def service(self, _):
        self.service_calls += 1
        return int(self.cancel_after is None or self.service_calls <= self.cancel_after)

    def put(self, slot=0, legacy=False, partial=False, image=None):
        offset = slot * SIZE
        block = bytearray(SIZE)
        block[:4] = b"GXRS" if legacy else b"GXR2"
        start = 4 if legacy else PREFIX
        if not legacy:
            block[4:PREFIX] = bytes(range(152))
        block[start:start + IMAGE] = image if image is not None else bytes([0x37]) * IMAGE
        if not partial:
            block[start + IMAGE:start + IMAGE + 4] = b"GXRE"
        self.data[offset:offset + SIZE] = block


class PhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="gx-ptp-store-")
        native = Path(cls.temp.name) / "store.dll"
        compiler = shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            raise RuntimeError("A native C compiler is required")
        subprocess.run([compiler, "-shared", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(HERE / "photo_store.c"), "-o", str(native)], check=True)
        cls.lib = C.CDLL(str(native))
        cls.lib.photo_store_open.argtypes = [C.POINTER(Store), C.POINTER(Io), C.c_uint64, C.c_uint32]
        cls.lib.photo_store_scan.argtypes = [C.POINTER(Store), VISIT, C.c_void_p]
        cls.lib.photo_store_info.argtypes = [C.POINTER(Store), C.c_uint32, C.POINTER(Info)]
        cls.lib.photo_store_load.argtypes = [C.POINTER(Store), C.POINTER(Info), C.c_void_p, C.c_size_t]
        cls.lib.photo_store_delete.argtypes = [C.POINTER(Store), C.c_uint32]
        cls.lib.photo_store_filename.argtypes = [C.POINTER(Info), C.c_char_p, C.c_size_t]
        cls.lib.photo_store_png.argtypes = [C.POINTER(Info), C.c_void_p, C.c_size_t,
                                          C.c_void_p, C.c_size_t, EMIT, C.c_void_p]

    @classmethod
    def tearDownClass(cls):
        # Windows cannot remove a loaded DLL; release it before removing scratch.
        if hasattr(C, "windll"):
            handle = cls.lib._handle
            del cls.lib
            C.windll.kernel32.FreeLibrary(C.c_void_p(handle))
        cls.temp.cleanup()

    def setUp(self):
        self.card = Card()
        self.store = Store()
        self.assertEqual(self.lib.photo_store_open(C.byref(self.store), C.byref(self.card.io),
                         len(self.card.data) // SECTOR, self.card.erased), 0)

    def info(self, handle=1):
        info = Info()
        self.assertEqual(self.lib.photo_store_info(C.byref(self.store), handle, C.byref(info)), 0)
        return info

    def load(self, info=None):
        info = info or self.info()
        buffer = (C.c_uint32 * (SIZE // 4))()
        C.memset(buffer, 0xCB, SIZE)
        self.assertEqual(self.lib.photo_store_load(C.byref(self.store), C.byref(info), buffer, SIZE), 0)
        return info, buffer

    def scan(self):
        found = []
        @VISIT
        def visit(_, ptr):
            found.append((ptr.contents.handle, ptr.contents.image_offset, ptr.contents.flags))
            return 1
        result = self.lib.photo_store_scan(C.byref(self.store), visit, None)
        return result, found

    def test_geometry_and_no_implicit_io(self):
        self.assertEqual(self.store.slot_count, 3)
        self.assertEqual(self.card.reads + self.card.writes, [])
        for size, erased in [(3730-1,255), (1<<32|1,255), (3730,1)]:
            self.assertEqual(self.lib.photo_store_open(C.byref(self.store), C.byref(self.card.io), size, erased), -1)
        self.assertEqual(self.lib.photo_store_open(C.byref(self.store), C.byref(self.card.io), 1<<32, 0), 0)

    def test_scan_holes_legacy_unknown_and_no_payload_reads(self):
        self.card.put(0)
        self.card.put(2, legacy=True)
        result, found = self.scan()
        self.assertEqual(result, 0)
        self.assertEqual(found, [(1,156,1), (3,4,33)])
        self.assertEqual(self.card.reads, [(0,1),(STRIDE,1),(STRIDE*2,1)])
        self.card.data[SIZE:SIZE+4] = b"BAD!"
        self.assertEqual(self.scan()[0], 0)
        self.assertEqual(self.store.unknown_occupied, 1)
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store), 2), -4)
        self.assertEqual(self.card.writes, [])

    def test_scan_read_error_never_claims_complete_or_free(self):
        self.card.put(0)
        self.card.bad.add(STRIDE)
        result, found = self.scan()
        self.assertEqual(result, -2)
        self.assertEqual(len(found), 1)
        self.assertEqual(self.store.unreadable_headers, 1)

    def test_partial_and_metadata_remain_opaque(self):
        self.card.put(0, partial=True)
        info = self.info()
        self.assertEqual(bytes(info.metadata), bytes(range(152)))
        self.assertTrue(info.flags & 64)
        name = C.create_string_buffer(48)
        self.assertGreater(self.lib.photo_store_filename(C.byref(info), name, 48), 0)
        self.assertEqual(name.value, b"GX_0000001_RECOVERED.png")

    def test_fresh_download_reads_and_exact_buffer(self):
        self.card.put()
        info, out = self.load()
        self.assertEqual(C.string_at(out,SIZE), self.card.data[:SIZE])
        self.assertEqual(info.flags, 7)
        self.card.data[3000] ^= 1
        info, other = self.load(info)
        self.assertEqual(C.string_at(other,SIZE), self.card.data[:SIZE])
        self.assertNotEqual(C.string_at(out,SIZE), C.string_at(other,SIZE))

    def test_failed_burst_retry_preserves_image_and_reports_error(self):
        self.card.put()
        info = self.info()
        self.card.fail_burst_once = True
        info, out = self.load(info)
        self.assertEqual(C.string_at(out,SIZE), self.card.data[:SIZE])
        self.assertEqual(info.read_errors, 1)
        self.assertEqual(info.unreadable_sectors, 0)
        self.assertTrue(info.flags & 8)

    def test_unreadable_sectors_zero_filled_not_failed_dma(self):
        self.card.put()
        info = self.info()
        self.card.bad.update([0,100,STRIDE-1])
        info, out = self.load(info)
        actual = C.string_at(out,SIZE)
        expected = bytearray(self.card.data[:SIZE])
        for bad in self.card.bad:
            expected[bad*SECTOR:(bad+1)*SECTOR] = bytes(SECTOR)
        self.assertEqual(actual, expected)
        self.assertEqual(info.unreadable_sectors,3)
        self.assertTrue(info.flags & 64)
        self.assertFalse(info.flags & 1)

    def test_recovery_failure_stops_io_and_retains_readable_prefix(self):
        self.card.put()
        info = self.info()
        self.card.bad.add(40)
        self.card.recovery_ok = False
        self.card.reads.clear()
        info, out = self.load(info)
        self.assertEqual(self.card.reads,[(0,32),(32,32)])
        self.assertEqual(info.unreadable_sectors,STRIDE-32)
        self.assertEqual(C.string_at(out,32*SECTOR),self.card.data[:32*SECTOR])
        self.assertEqual(C.string_at(C.addressof(out)+32*SECTOR,SIZE-32*SECTOR),bytes(SIZE-32*SECTOR))

    def test_changed_and_deleted_object_not_exported(self):
        self.card.put()
        info = self.info()
        out = (C.c_uint32 * (SIZE//4))()
        self.card.data[:4]=b"GXRS"
        self.assertEqual(self.lib.photo_store_load(C.byref(self.store),C.byref(info),out,SIZE),-6)
        self.card.data[:4]=b"\xff"*4
        self.assertEqual(self.lib.photo_store_load(C.byref(self.store),C.byref(info),out,SIZE),-3)

    def test_delete_preserves_neighbors_clears_header_last_and_reuses(self):
        for erased in [0,255]:
            self.card = Card(erased=erased)
            self.assertEqual(self.lib.photo_store_open(C.byref(self.store),C.byref(self.card.io),len(self.card.data)//SECTOR,erased),0)
            for slot in range(3): self.card.put(slot)
            left, right = bytes(self.card.data[:SIZE]),bytes(self.card.data[2*SIZE:])
            self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),2),0)
            self.assertEqual(self.card.data[:SIZE],left)
            self.assertEqual(self.card.data[2*SIZE:],right)
            self.assertEqual(self.card.data[SIZE:2*SIZE],bytes([erased])*SIZE)
            self.assertEqual(self.card.writes[-1],(STRIDE,1))
            self.assertEqual(sum(n for _,n in self.card.writes),STRIDE)
            self.assertEqual(self.card.events[-3:],[('sync',),('write',STRIDE,1),('sync',)])
            self.assertEqual([h for h,_,_ in self.scan()[1]],[1,3])
            self.card.put(1)  # models existing allocator reusing the first blank header
            self.assertEqual([h for h,_,_ in self.scan()[1]],[1,2,3])

    def test_delete_failure_or_cancel_never_releases_header_early(self):
        for fail_at in [1,30,117]:
            self.card.put(1)
            self.card.writes.clear()
            self.card.fail_write=fail_at
            self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),2),-2)
            self.assertEqual(self.card.data[SIZE:SIZE+4],b'GXR2')
        self.card.fail_write=0
        self.card.cancel_after=self.card.service_calls+2
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),2),-5)
        self.assertEqual(self.card.data[SIZE:SIZE+4],b'GXR2')

    def test_delete_tail_sync_failure_keeps_header_occupied(self):
        self.card.put()
        self.card.fail_sync=1
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),1),-2)
        self.assertEqual(self.card.data[:4],b'GXR2')
        self.assertNotIn((0,1),self.card.writes)

    def test_delete_final_sync_failure_can_leave_media_free_despite_error(self):
        self.card.put()
        neighbor=bytes(self.card.data[SIZE:])
        self.card.fail_sync=2
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),1),-2)
        self.assertEqual(self.card.data[:SIZE],b'\xff'*SIZE)
        self.assertEqual(self.card.data[SIZE:],neighbor)
        # A later independently safe header read, not the failed operation's
        # return code, can reconcile the now-absent catalogue object.
        info=Info()
        self.assertEqual(self.lib.photo_store_info(C.byref(self.store),1,C.byref(info)),-3)

    def test_delete_final_readback_failure_can_leave_media_free_despite_error(self):
        self.card.put()
        neighbor=bytes(self.card.data[SIZE:])
        failed=[False]
        @READ
        def fail_final_read(user,lba,dst,count):
            if self.card.writes and lba==0 and not failed[0]:
                failed[0]=True
                C.memset(dst,0xA5,count*SECTOR)
                return 0
            return self.card.read(user,lba,dst,count)
        self.store.io.read=fail_final_read
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),1),-2)
        self.assertTrue(failed[0])
        self.assertEqual(self.card.data[:SIZE],b'\xff'*SIZE)
        self.assertEqual(self.card.data[SIZE:],neighbor)
        info=Info()
        self.assertEqual(self.lib.photo_store_info(C.byref(self.store),1,C.byref(info)),-3)

    def test_cancelled_delete_keeps_handle_but_image_is_now_partial(self):
        self.card.put()
        self.card.cancel_after=1
        self.assertEqual(self.lib.photo_store_delete(C.byref(self.store),1),-5)
        self.assertEqual(self.card.data[:4],b'GXR2')
        self.card.cancel_after=None
        info=self.info()
        self.assertTrue(info.flags&64)
        self.assertFalse(info.flags&4)

    def png(self, info, out, fail_call=0):
        pieces=[]
        @EMIT
        def emit(_, ptr, count):
            self.assertLessEqual(count,2241)
            pieces.append(C.string_at(ptr,count))
            return int(not fail_call or len(pieces)!=fail_call)
        row=(C.c_uint8*2241)()
        result=self.lib.photo_store_png(C.byref(info),out,SIZE,row,len(row),emit,None)
        return result,b''.join(pieces)

    def decode(self,png):
        self.assertEqual(len(png),PNG_SIZE)
        self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
        chunks={};p=8
        while p<len(png):
            n=struct.unpack_from('>I',png,p)[0]
            kind=png[p+4:p+8];data=png[p+8:p+8+n]
            self.assertEqual(zlib.crc32(kind+data),struct.unpack_from('>I',png,p+8+n)[0])
            chunks[kind]=data;p+=12+n
        self.assertEqual(p,len(png))
        self.assertEqual(chunks[b'IHDR'],struct.pack('>IIBBBBB',WIDTH,HEIGHT,16,0,0,0,0))
        self.assertEqual(chunks[b'sBIT'],b'\x0a')
        tiff=chunks[b'eXIf']
        self.assertEqual(tiff[:8],b'MM\x00*\x00\x00\x00\x08')
        self.assertEqual(struct.unpack_from('>HHII',tiff,10),(0x8769,4,1,26))
        self.assertEqual(struct.unpack_from('>HHII',tiff,28),(0x9286,7,512,44))
        self.assertEqual(tiff[44:52],b'ASCII\0\0\0')
        comment=tiff[52:].split(b'\0',1)[0]
        return zlib.decompress(chunks[b'IDAT']),comment

    def test_png_every_pixel_mapping_both_layouts_fixed_size_and_metadata(self):
        # Include every 10-bit value and shifting low-bit patterns across rows.
        raw=bytearray();expected=bytearray()
        for y in range(HEIGHT):
            expected.append(0)
            for x in range(0,WIDTH,4):
                values=[((x+j)*17+y*43)&1023 for j in range(4)]
                raw.extend(v>>2 for v in values)
                raw.append(sum((v&3)<<(j*2) for j,v in enumerate(values)))
                expected.extend(struct.pack('>4H',*(v<<6 for v in values)))
        for legacy in [False,True]:
            self.card.put(legacy=legacy,image=raw)
            info,out=self.load()
            result,png=self.png(info,out)
            self.assertEqual(result,0)
            actual,comment=self.decode(png)
            self.assertEqual(actual,expected)
            self.assertIn(b'No stored payload checksum',comment)
            self.assertIn(b'date/orientation unavailable',comment)
            self.assertNotIn(b'RECOVERED',comment)

    def test_png_recovered_exif_and_cancellation(self):
        self.card.put(partial=True)
        info,out=self.load()
        result,png=self.png(info,out)
        self.assertEqual(result,0)
        _,comment=self.decode(png)
        self.assertIn(b'RECOVERED',comment)
        self.assertIn(b'completion_marker=missing/unreadable',comment)
        self.assertEqual(self.png(info,out,fail_call=15)[0],-7)


if __name__=='__main__':
    unittest.main()
