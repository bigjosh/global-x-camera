"""Real FatFs + project save layer on a sparse fake card; no hardware access.

Requires a native clang toolchain. The independent FAT32 reader below does not
call FatFs. Build products live in a temporary directory outside the repository.
"""
from __future__ import annotations
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

HERE=Path(__file__).resolve().parent
FS=HERE.parent
CAPTURE=FS.parent
REPO=FS.parents[2]
IO=C.CFUNCTYPE(C.c_int,C.c_uint32,C.c_void_p,C.c_uint32)
SYNC=C.CFUNCTYPE(C.c_int)
PNG_WRITE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p,C.c_size_t)


class PngStats(C.Structure):
    _fields_=[("output_bytes",C.c_uint64),("rows_encoded",C.c_uint32),
              ("idat_chunks",C.c_uint32),("callback_calls",C.c_uint32)]


def decode_png(encoded):
    """Independent PNG chunk CRC, zlib and filter verification."""
    assert encoded[:8]==b"\x89PNG\r\n\x1a\n"
    pos=8
    chunks=[]
    while pos<len(encoded):
        length,kind=struct.unpack_from(">I4s",encoded,pos)
        data=encoded[pos+8:pos+8+length]
        crc=struct.unpack_from(">I",encoded,pos+8+length)[0]
        assert crc==zlib.crc32(kind+data)
        chunks.append((kind,data))
        pos+=length+12
    assert pos==len(encoded) and chunks[-1]==(b"IEND",b"")
    width,height,depth,color,compression,filtering,interlace=struct.unpack(
        ">IIBBBBB",chunks[0][1])
    assert (depth,color,compression,filtering,interlace)==(16,0,0,0,0)
    assert chunks[1]==(b"sBIT",b"\x0a")
    raw=zlib.decompress(b"".join(data for kind,data in chunks if kind==b"IDAT"))
    assert len(raw)==height*(width*2+1)
    pixels=[]
    for row in range(height):
        scanline=bytearray(raw[row*(width*2+1):(row+1)*(width*2+1)])
        if scanline[0]==1:
            for i in range(3,len(scanline)):
                scanline[i]=(scanline[i]+scanline[i-2])&255
        else:
            assert scanline[0]==0
        pixels.extend(struct.unpack(">"+"H"*width,scanline[1:]))
    return width,height,pixels


class Report(C.Structure):
    _fields_=[(n,C.c_uint32) for n in
        ("state","stage","fat_result","bytes_written","expected_max_bytes",
         "file_number","cluster_bytes","free_clusters","completed")]
    _fields_ += [("sector_count",C.c_uint64),
                 ("final_name",C.c_char*13),("temporary_name",C.c_char*13)]


class SparseCard:
    def __init__(self):
        self.sectors={}
        self.sector_count=8388608
        self.calls=[]
        self.fail_write=False
        self.fail_sync=False

    def read(self,lba,buffer,count):
        self.calls.append(("read",lba,count))
        C.memmove(buffer,b"".join(self.sectors.get(lba+i,bytes(512))
                                 for i in range(count)),count*512)
        return 0

    def write(self,lba,buffer,count):
        self.calls.append(("write",lba,count))
        if self.fail_write:
            return 1
        data=C.string_at(buffer,count*512)
        for i in range(count):
            sector=data[i*512:(i+1)*512]
            if sector==bytes(512):
                self.sectors.pop(lba+i,None)
            else:
                self.sectors[lba+i]=sector
        return 0

    def sync(self):
        self.calls.append(("sync",0,0))
        return int(self.fail_sync)

    def sector(self,lba):
        return self.sectors.get(lba,bytes(512))

    def independent_files(self):
        """Parse MBR/BPB/FAT/root without using the implementation under test."""
        mbr=self.sector(0)
        assert mbr[510:]==b"\x55\xaa"
        partitions=[mbr[446+16*i:462+16*i] for i in range(4)]
        used=[p for p in partitions if p[4]]
        assert len(used)==1 and used[0][4] in (0x0b,0x0c)
        start,length=struct.unpack_from("<II",used[0],8)
        assert start>0 and start+length<=self.sector_count
        boot=self.sector(start)
        assert boot[510:]==b"\x55\xaa"
        bps=struct.unpack_from("<H",boot,11)[0]
        spc=boot[13]
        reserved=struct.unpack_from("<H",boot,14)[0]
        fats=boot[16]
        fat_size=struct.unpack_from("<I",boot,36)[0]
        root=struct.unpack_from("<I",boot,44)[0]
        assert (bps,spc,fats)==(512,64,2)
        fat_start=start+reserved
        data_start=fat_start+fats*fat_size

        def chain(cluster):
            seen=set()
            while cluster<0xffffff8:
                assert 2<=cluster<0xffffff0 and cluster not in seen
                seen.add(cluster)
                base=data_start+(cluster-2)*spc
                yield b"".join(self.sector(base+i) for i in range(spc))
                offset=cluster*4
                a=self.sector(fat_start+offset//512)
                b=self.sector(fat_start+fat_size+offset//512)
                assert a==b, "the two FAT copies disagree"
                cluster=struct.unpack_from("<I",a,offset%512)[0]&0x0fffffff

        directory=b"".join(chain(root))
        result={}
        for offset in range(0,len(directory),32):
            entry=directory[offset:offset+32]
            if entry[0]==0:
                break
            if entry[0]==0xe5 or entry[11] in (0x0f,0x08):
                continue
            name=entry[:8].decode().rstrip()+"."+entry[8:11].decode().rstrip()
            cluster=(struct.unpack_from("<H",entry,20)[0]<<16 |
                     struct.unpack_from("<H",entry,26)[0])
            size=struct.unpack_from("<I",entry,28)[0]
            payload=b"".join(chain(cluster))[:size] if cluster else b""
            assert len(payload)==size
            result[name]=payload
        return result


class FilesystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="photo-fs-test-")
        cls.library=Path(cls.temp.name)/"photo_fs_test.dll"
        command=[shutil.which("clang") or "clang","-shared","-O2","-Wall",
                 "-Wextra","-Werror","-Wl,--export-all-symbols",
                 "-I"+str(FS),"-I"+str(REPO/"firmware"/"sd-storage"),
                 str(FS/"ff.c"),str(FS/"sd_diskio.c"),
                 str(CAPTURE/"photo_fs.c"),str(HERE/"host_sd.c"),
                 str(REPO/"firmware"/"png-encoder"/"png16.c"),
                 str(REPO/"firmware"/"png-encoder"/"png16_miniz.c"),
                 "-o",str(cls.library)]
        subprocess.run(command,check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.lib=C.CDLL(str(self.library))
        self.lib.host_callbacks.argtypes=[IO,IO,SYNC]
        self.lib.host_card.argtypes=[C.c_uint64]
        self.lib.host_card.restype=C.c_void_p
        self.lib.photo_fs_mount.argtypes=[C.c_void_p]
        self.lib.photo_fs_format.argtypes=[C.c_void_p]
        self.lib.photo_fs_open.argtypes=[C.c_uint32]
        self.lib.photo_fs_append.argtypes=[C.c_void_p,C.c_size_t]
        self.lib.photo_fs_write_callback.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]
        self.lib.photo_fs_readback.argtypes=[C.c_char_p,C.c_uint32,C.c_void_p,
                                            C.c_uint32,C.POINTER(C.c_uint32)]
        self.lib.photo_fs_get_report.restype=C.POINTER(Report)
        self.lib.png16_workspace_size.restype=C.c_size_t
        self.lib.png16_encode.argtypes=[
            C.c_void_p,C.c_size_t,C.c_uint32,C.c_uint32,C.c_size_t,C.c_int,
            C.c_void_p,C.c_size_t,PNG_WRITE,C.c_void_p,C.POINTER(PngStats)]
        self.disk=SparseCard()
        self.callbacks=[IO(self.disk.read),IO(self.disk.write),SYNC(self.disk.sync)]
        self.lib.host_callbacks(*self.callbacks)
        self.card=self.lib.host_card(8388608)  # sparse 4 GiB, no giant host file

    def tearDown(self):
        # A fresh module per case resets the embedded application's static state.
        handle=self.lib._handle
        del self.lib
        C.windll.kernel32.FreeLibrary.argtypes=[C.c_void_p]
        C.windll.kernel32.FreeLibrary.restype=C.c_int
        self.assertTrue(C.windll.kernel32.FreeLibrary(handle))

    def format(self):
        self.assertEqual(self.lib.photo_fs_format(self.card),0)
        self.assertEqual(self.lib.photo_fs_get_report().contents.cluster_bytes,32768)

    def append(self,data):
        data=C.create_string_buffer(data,len(data))
        self.assertEqual(self.lib.photo_fs_append(data,len(data)),0)

    def save(self,data):
        self.assertEqual(self.lib.photo_fs_open(len(data)),0)
        self.append(data)
        self.assertEqual(self.lib.photo_fs_finish(),0)

    def test_mount_never_formats(self):
        self.assertEqual(self.lib.photo_fs_mount(self.card),-1)
        self.assertFalse(any(call[0]=="write" for call in self.disk.calls))
        self.assertEqual(self.disk.sectors,{})

    def test_format_stream_finish_independent_read_and_readback(self):
        self.format()
        payload=bytes((i*29+i//251)&255 for i in range(100003))
        self.assertEqual(self.lib.photo_fs_open(len(payload)),0)
        for start,end in ((0,333),(333,33333),(33333,33334),(33334,len(payload))):
            self.append(payload[start:end])
        self.assertEqual(self.lib.photo_fs_finish(),0)
        report=self.lib.photo_fs_get_report().contents
        self.assertEqual((report.completed,report.bytes_written),(1,len(payload)))
        self.assertEqual(report.final_name,b"IMG00001.PNG")
        self.assertEqual(self.disk.independent_files(),{"IMG00001.PNG":payload})
        for offset,length in ((0,37),(32333,60000),(100002,20),(100003,20)):
            output=C.create_string_buffer(length)
            got=C.c_uint32()
            self.assertEqual(self.lib.photo_fs_readback(
                report.final_name,offset,output,length,C.byref(got)),0)
            self.assertEqual(output.raw[:got.value],payload[offset:offset+length])
        self.assertLessEqual(max(c[2] for c in self.disk.calls),64)
        self.assertEqual(self.disk.calls[-1][0],"read")

    def test_no_overwrite_abort_preserves_partial_and_skips_name(self):
        self.format()
        self.save(b"first retained image")
        self.assertEqual(self.lib.photo_fs_open(100),0)
        self.append(b"partial data")
        self.assertEqual(self.lib.photo_fs_abort(),0)
        self.save(b"third retained image")
        self.assertEqual(self.disk.independent_files(),{
            "IMG00001.PNG":b"first retained image",
            "IMG00002.TMP":b"partial data",
            "IMG00003.PNG":b"third retained image"})

    def test_png_callback_uses_boolean_success_and_failure(self):
        self.assertEqual(self.lib.photo_fs_write_callback(None,b"x",1),0)
        self.format()
        self.assertEqual(self.lib.photo_fs_open(1),0)
        self.assertEqual(self.lib.photo_fs_write_callback(None,b"x",1),1)
        self.assertEqual(self.lib.photo_fs_write_callback(None,b"y",1),0)
        self.assertEqual(self.lib.photo_fs_get_report().contents.bytes_written,1)
        self.assertEqual(self.lib.photo_fs_abort(),0)
        self.assertEqual(self.disk.independent_files(),{"IMG00001.TMP":b"x"})

    def test_png_callback_reports_actual_disk_failure(self):
        self.format()
        self.assertEqual(self.lib.photo_fs_open(32768),0)
        self.disk.fail_write=True
        self.assertEqual(self.lib.photo_fs_write_callback(None,bytes(32768),32768),0)
        self.assertEqual(self.lib.photo_fs_get_report().contents.completed,0)

    def test_actual_png_encoder_through_callback_and_fatfs_roundtrip(self):
        self.format()
        width,height=67,53
        samples=[(i*79+i//31)&1023 for i in range(width*height)]
        raw=struct.pack("<"+"H"*len(samples),*samples)
        frame=C.create_string_buffer(raw,len(raw))
        workspace_bytes=self.lib.png16_workspace_size()
        workspace=(C.c_uint64*((workspace_bytes+7)//8))()
        # Bind the actual compiled C adapter; do not substitute a Python sink.
        callback=PNG_WRITE(("photo_fs_write_callback",self.lib))
        for mode in range(3):
            self.assertEqual(self.lib.photo_fs_open(40000),0)
            stats=PngStats()
            self.assertEqual(self.lib.png16_encode(
                frame,len(raw),width,height,width*2,mode,workspace,
                workspace_bytes,callback,None,C.byref(stats)),0)
            self.assertEqual(self.lib.photo_fs_finish(),0)
            name=f"IMG{mode+1:05}.PNG"
            encoded=self.disk.independent_files()[name]
            self.assertEqual(stats.output_bytes,len(encoded))
            self.assertEqual(decode_png(encoded),
                             (width,height,[sample<<6 for sample in samples]))
            output=C.create_string_buffer(len(encoded))
            got=C.c_uint32()
            self.assertEqual(self.lib.photo_fs_readback(
                name.encode(),0,output,len(encoded),C.byref(got)),0)
            self.assertEqual(output.raw[:got.value],encoded)
            self.assertEqual(frame.raw,raw)

    def test_remount_preserves_file_and_next_name(self):
        self.format()
        self.save(b"before remount")
        self.assertEqual(self.lib.photo_fs_mount(self.card),0)
        self.save(b"after remount")
        self.assertEqual(self.disk.independent_files(),{
            "IMG00001.PNG":b"before remount","IMG00002.PNG":b"after remount"})

    def test_reported_card_capacity_can_format_fat32(self):
        # Reported bench capacity; this is a virtual disk, not validation of
        # physical card capacity or a claim that any hardware format ran.
        self.disk.sector_count=62723719168//512
        self.card=self.lib.host_card(self.disk.sector_count)
        self.format()
        self.save(b"virtual large-card test")
        self.assertEqual(self.disk.independent_files(),
                         {"IMG00001.PNG":b"virtual large-card test"})

    def test_space_preflight_stops_without_writing(self):
        self.format()
        self.save(b"preserved")
        before=dict(self.disk.sectors)
        self.disk.calls.clear()
        self.assertEqual(self.lib.photo_fs_open(0xffffffff),-2)
        self.assertFalse(any(c[0]=="write" for c in self.disk.calls))
        self.assertEqual(self.disk.sectors,before)
        self.assertEqual(self.disk.independent_files(),{"IMG00001.PNG":b"preserved"})

    def test_declared_size_is_enforced_and_abort_keeps_tmp(self):
        self.format()
        self.assertEqual(self.lib.photo_fs_open(1),0)
        self.assertEqual(self.lib.photo_fs_append(b"xx",2),-4)
        self.assertEqual(self.lib.photo_fs_finish(),-3)
        self.assertEqual(self.lib.photo_fs_abort(),0)
        self.assertEqual(self.disk.independent_files(),{"IMG00001.TMP":b""})

    def test_write_failure_never_reports_completed(self):
        self.format()
        self.save(b"existing")
        self.assertEqual(self.lib.photo_fs_open(32768),0)
        self.disk.fail_write=True
        self.assertEqual(self.lib.photo_fs_append(bytes(32768),32768),-1)
        self.assertEqual(self.lib.photo_fs_get_report().contents.completed,0)
        self.assertEqual(self.lib.photo_fs_finish(),-3)
        self.assertEqual(self.disk.independent_files()["IMG00001.PNG"],b"existing")
        self.assertNotIn("IMG00002.PNG",self.disk.independent_files())

    def test_sync_failure_never_reports_completed_or_renames(self):
        self.format()
        self.assertEqual(self.lib.photo_fs_open(5),0)
        self.append(b"hello")
        self.disk.fail_sync=True
        self.assertEqual(self.lib.photo_fs_finish(),-1)
        self.assertEqual(self.lib.photo_fs_get_report().contents.completed,0)
        self.assertNotIn("IMG00001.PNG",self.disk.independent_files())

    def test_paths_and_concurrent_operations_rejected(self):
        self.format()
        self.assertEqual(self.lib.photo_fs_open(100),0)
        self.assertEqual(self.lib.photo_fs_format(self.card),-3)
        self.assertEqual(self.lib.photo_fs_mount(self.card),-3)
        self.assertEqual(self.lib.photo_fs_open(10),-3)
        self.assertEqual(self.lib.photo_fs_abort(),0)
        got=C.c_uint32()
        for name in (b"../x",b"IMG00001.JPG",b"IMGxx001.PNG",b"0:/IMG00001.PNG"):
            self.assertEqual(self.lib.photo_fs_readback(name,0,None,0,C.byref(got)),-4)

    def test_vendor_hashes(self):
        source=json.loads((FS/"upstream-provenance.json").read_text())
        for name,want in source["final_sources"].items():
            self.assertEqual(hashlib.sha256((FS/name).read_bytes()).hexdigest(),want,name)


if __name__=="__main__":
    unittest.main(verbosity=2)
