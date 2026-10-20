"""Offline shutdown proof decoder/reader tests. No device process is launched."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

import read_proof

HERE = Path(__file__).resolve().parent


def checksum(words):
    # Independent word/byte implementation of completion.c's publish().
    result = 2166136261
    for value in words[1:62]:
        for shift in (0, 8, 16, 24):
            result = ((result ^ ((value >> shift) & 255)) * 16777619) & 0xffffffff
    return result


def proof():
    words = [0] * 128
    words[:6] = [0x4c504d31, 1, 64, 2, 40, 0]
    words[38] = 400000000
    words[60] = 0x12345678  # Reserved fields are still checksum protected.
    words[62] = checksum(words)
    words[63] = 0x4c50454e
    words[64:69] = [0x504c5031, 1, 2, 7, 0]
    words[64+8] = 12
    words[64+60] = 0xc000001c
    words[127] = 0x50444f4e
    return words


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.receiver = self.build / "receiver"
        self.receiver.mkdir(parents=True)
        for name in ("completion.h", "peripherals.h"):
            shutil.copyfile(HERE / name, self.receiver / name)
        self.code = bytes.fromhex("0050 3b34") + struct.pack("<I",64_000_000)
        self.live = self.code[:-4] + struct.pack("<I",400_000_000)
        (self.receiver / "capture.bin").write_bytes(self.code)
        (self.receiver / "symbols.txt").write_text(
            "34300004 D _sdata\n34300004 d SystemCoreClock\n34300008 D _edata\n")
        self.manifest = dict(
            sources={str(self.receiver/name): hashlib.sha256((self.receiver/name).read_bytes()).hexdigest()
                     for name in ("completion.h", "peripherals.h")},
            vector_address="0x34300000", raw_bytes=len(self.code),
            raw_sha256=hashlib.sha256(self.code).hexdigest())
        self.save_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def save_manifest(self):
        (self.receiver / "manifest.json").write_text(json.dumps(self.manifest))

    def add_late(self):
        self.late_dir = self.build / "late"
        self.late_dir.mkdir()
        for name in ("completion.h", "peripherals.h"):
            shutil.copyfile(self.receiver / name, self.late_dir / name)
            # Deliberately remove early copies so the test cannot decode them.
            (self.receiver / name).unlink()
        self.manifest["sources"] = {}
        self.late_code = bytes.fromhex("fee7 00bf 00bf fee7")
        (self.late_dir / "late.bin").write_bytes(self.late_code)
        self.late_manifest = dict(
            schema=1, binary_file="late.bin", binary_bytes=len(self.late_code),
            binary_sha256=hashlib.sha256(self.late_code).hexdigest(),
            crc32=hex(zlib.crc32(self.late_code)), flash_offset=0xE000,
            load_address="0x343c0000", entry_address="0x343c0001",
            loader_proof_address="0x343f9b00", sleep_idle_address="0x343c0000",
            failure_park_address="0x343c0006", no_initialized_data_or_bss=True,
            section_sizes=dict(text=len(self.late_code), data=0, bss=0),
            sources={str(self.late_dir/name): hashlib.sha256(
                (self.late_dir/name).read_bytes()).hexdigest()
                for name in ("completion.h", "peripherals.h")})
        self.refresh_late()
        words = [0x4C504C31,1,2,0,100,200,2,2,len(self.late_code),
                 zlib.crc32(self.late_code),0x343c0001,987,513,12,0xc000001c,0x4c504c44]
        self.late_proof = struct.pack("<16I", *words)
        return read_proof.load_late_build(self.receiver,self.manifest)

    def refresh_late(self):
        path=self.late_dir/"manifest.json"
        path.write_text(json.dumps(self.late_manifest))
        identity={k:v for k,v in self.late_manifest.items()
                  if k not in ("schema","binary_file","sources")}
        identity.update(manifest_path=str(path),
                        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.manifest["low_power"]=dict(late_module=identity)
        self.manifest["sleep_idle_address"]=self.late_manifest["sleep_idle_address"]
        self.save_manifest()

    def decode(self, words=None):
        return read_proof.decode(struct.pack("<128I", *(words or proof())), self.receiver)

    def test_actual_enum_offsets_and_le_words_match_firmware(self):
        c, p = read_proof.layout(self.receiver)
        self.assertEqual((c["cpu_hz"], c["checksum"], c["terminal"]), (38, 62, 63))
        self.assertEqual((p["control"], p["fpccr"], p["terminal"]), (8, 60, 63))
        value = self.decode()
        self.assertTrue(value["stable_checksum_valid"])
        self.assertEqual(value["completion"]["cpu_hz"], 400000000)
        self.assertEqual(value["peripherals"]["control"], 12)
        self.assertEqual(value["peripherals"]["fpccr"], 0xc000001c)
        self.assertFalse(value["physical_entry_proven"])

    def test_every_completion_payload_word_is_fnv_protected(self):
        for index in range(1, 63):
            with self.subTest(index=index):
                words = proof()
                words[index] ^= 1
                self.assertFalse(self.decode(words)["stable_checksum_valid"])

    def test_magic_schema_length_and_terminal_have_independent_gates(self):
        for index in (0, 1, 2, 63):
            with self.subTest(index=index):
                words = proof()
                words[index] ^= 1
                words[62] = checksum(words)
                self.assertFalse(self.decode(words)["stable_checksum_valid"])

    def test_peripheral_snapshot_is_explicitly_not_checksum_protected(self):
        words = proof()
        words[100] ^= 0x1234
        value = self.decode(words)
        self.assertTrue(value["stable_checksum_valid"])
        self.assertIn("peripheral snapshot has no checksum", value["checksum_scope"])

    def test_refused_or_returned_state_is_diagnostic_not_entry_success(self):
        for state in (255, 50):
            words = proof()
            words[4:6] = [state, 11]
            words[62] = checksum(words)
            value = self.decode(words)
            self.assertTrue(value["stable_checksum_valid"])
            self.assertFalse(value["physical_entry_proven"])
            self.assertEqual(value["completion"]["error"], 11)

    def test_truncated_or_extended_proof_is_rejected(self):
        raw = struct.pack("<128I", *proof())
        for data in (raw[:-1], raw+b"\0", b""):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                read_proof.decode(data, self.receiver)

    def test_enum_comments_hex_and_noncontiguous_assignment(self):
        path = self.root / "enum.h"
        path.write_text("enum { LP_MAGIC, /* LP_FAKE */ LP_SCHEMA, LP_LAST=0x3fU };")
        self.assertEqual(read_proof.enum_fields(path, "LP_"),
                         dict(magic=0, schema=1, last=63))
        for body in ("LP_MAGIC, LP_A=1<<2", "LP_MAGIC, LP_A=64",
                     "LP_MAGIC, LP_A=0", "LP_MAGIC, LP_MAGIC",
                     "LP_MAGIC, LP_A=-1", "LP_MAGIC, OTHER_A"):
            path.write_text("enum {" + body + "};")
            with self.assertRaises(ValueError):
                read_proof.enum_fields(path, "LP_")

    def test_missing_or_ambiguous_enum_rejected(self):
        path = self.root/"enum.h"
        for text in ("enum { LP_A };", "enum { LP_MAGIC }; enum { LP_MAGIC };"):
            path.write_text(text)
            with self.assertRaises(ValueError):
                read_proof.enum_fields(path,"LP_")

    def test_frozen_lookup_uses_manifest_sources_not_working_headers(self):
        receiver, manifest, code = read_proof.load_build(self.build)
        self.assertEqual(receiver,self.receiver)
        self.assertEqual(code,self.code)
        self.assertEqual(manifest,self.manifest)
        (self.receiver/"completion.h").write_text("// changed")
        with self.assertRaisesRegex(ValueError,"Changed frozen source"):
            read_proof.load_build(self.build)

    def test_unlisted_decoder_header_and_changed_binary_rejected(self):
        self.manifest["sources"].pop(str(self.receiver/"completion.h"))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,"Decoder header missing"):
            read_proof.load_build(self.build)
        self.manifest["sources"][str(self.receiver/"completion.h")]=hashlib.sha256(
            (self.receiver/"completion.h").read_bytes()).hexdigest()
        self.save_manifest()
        (self.receiver/"capture.bin").write_bytes(b"changed!")
        with self.assertRaisesRegex(ValueError,"Receiver differs"):
            read_proof.load_build(self.build)

    def test_receiver_bound_and_vector_rejected_before_any_bench(self):
        for key,value in (("raw_bytes",0x20001),("vector_address","0x50000000")):
            with self.subTest(key=key):
                old=self.manifest[key]
                self.manifest[key]=value
                self.save_manifest()
                with patch.object(read_proof,"Bench",side_effect=AssertionError("Must not construct bench")):
                    with self.assertRaisesRegex(ValueError,"Receiver differs"):
                        read_proof.main(["--build",str(self.build),"--out",str(self.root/"out")])
                self.manifest[key]=old

    def test_only_exact_runtime_clock_word_is_allowed(self):
        result=read_proof.validate_live_receiver(self.receiver,self.code,self.live)
        self.assertTrue(result["live_immutable_code_matches"])
        self.assertFalse(result["live_code_matches"])
        self.assertEqual(result["immutable_bytes"],4)
        self.assertEqual(result["system_core_clock"]["runtime_hz"],400_000_000)
        for clock in (64_000_000,200_000_000,0,0xffffffff):
            with self.subTest(clock=clock),self.assertRaisesRegex(ValueError,"400 MHz"):
                read_proof.validate_live_receiver(self.receiver,self.code,
                                                 self.code[:-4]+struct.pack("<I",clock))
        changed=bytes([self.live[0]^1])+self.live[1:]
        with self.assertRaisesRegex(ValueError,"immutable bytes"):
            read_proof.validate_live_receiver(self.receiver,self.code,changed)
        with self.assertRaisesRegex(ValueError,"immutable bytes"):
            read_proof.validate_live_receiver(self.receiver,self.code,self.live+b"\0")

    def test_clock_layout_never_authorizes_other_data_or_guessed_offset(self):
        bad_texts=(
            "34300000 d SystemCoreClock\n34300000 D _sdata\n34300008 D _edata\n",
            "34300004 d SystemCoreClock\n34300000 D _sdata\n34300008 D _edata\n",
            "34300004 d SystemCoreClock\n34300004 D _sdata\n3430000c D _edata\n",
            "34300004 t SystemCoreClock\n34300004 D _sdata\n34300008 D _edata\n",
            "34300004 D _sdata\n34300008 D _edata\n",
            "34300004 d SystemCoreClock\n34300004 d SystemCoreClock\n"
            "34300004 D _sdata\n34300008 D _edata\n",
        )
        for text in bad_texts:
            with self.subTest(text=text):
                (self.receiver/"symbols.txt").write_text(text)
                with self.assertRaises(ValueError):
                    read_proof.checked_clock_word(self.receiver,self.code)
        (self.receiver/"symbols.txt").write_text(
            "34300004 D _sdata\n34300004 d SystemCoreClock\n34300008 D _edata\n")
        with self.assertRaisesRegex(ValueError,"64 MHz"):
            read_proof.checked_clock_word(self.receiver,self.live)

    def run_fake(self, raw, live=None, late_proof=None, late_code=None):
        calls=[]
        output=self.root/"out"
        class ReadOnlyFake:
            def __init__(self, path):
                self.output=path
                path.mkdir(exist_ok=False)
            def upload(self, address, length, name):
                calls.append((address,length,name))
                data={0x343f9c00:raw,
                      0x34300000:self_code if live is None else live,
                      0x343f9b00:late_proof,0x343c0000:late_code}[address]
                (self.output/name).write_bytes(data)
                return data
        self_code=self.live
        with patch.object(read_proof,"Bench",ReadOnlyFake),redirect_stdout(io.StringIO()):
            try:
                read_proof.main(["--build",str(self.build),"--out",str(output)])
            except ValueError as error:
                return calls,output,error
        return calls,output,None

    def test_success_reads_only_proof_and_matching_code_without_mutation_api(self):
        calls,output,error=self.run_fake(struct.pack("<128I",*proof()))
        self.assertIsNone(error)
        self.assertEqual([(a,n) for a,n,_ in calls],[(0x343f9c00,512),(0x34300000,len(self.code))])
        result=json.loads((output/"result.json").read_text())
        self.assertTrue(result["no_halt_reset_or_peripheral_access"])
        self.assertFalse(result["physical_entry_proven"])

    def test_late_headers_loader_and_exact_live_bytes_are_all_required(self):
        late=self.add_late()
        read_proof.load_build(self.build)
        self.assertEqual(late["directory"],self.late_dir)
        calls,output,error=self.run_fake(struct.pack("<128I",*proof()),
                                        late_proof=self.late_proof,late_code=self.late_code)
        self.assertIsNone(error)
        self.assertEqual([(a,n) for a,n,_ in calls],
                         [(0x343f9c00,512),(0x34300000,len(self.code)),
                          (0x343f9b00,64),(0x343c0000,len(self.late_code))])
        result=json.loads((output/"result.json").read_text())
        self.assertTrue(result["late_validation"]["live_code_matches"])
        self.assertTrue(result["late_loader_validation"]["verified"])
        self.assertFalse(result["physical_entry_proven"])

    def test_late_manifest_source_identity_crc_bounds_and_state_layout_rejected(self):
        self.add_late()
        for key,value in (("load_address","0x343b0000"),
                          ("entry_address","0x343c0005"),("flash_offset",0x6000),
                          ("binary_bytes",0x2004),("crc32","0x0"),
                          ("no_initialized_data_or_bss",False),
                          ("section_sizes",dict(text=8,data=4,bss=0)),
                          ("failure_park_address","0x343c2000")):
            with self.subTest(key=key):
                old=self.late_manifest[key]
                self.late_manifest[key]=value
                self.refresh_late()
                with self.assertRaises(ValueError):
                    read_proof.load_build(self.build)
                self.late_manifest[key]=old
        self.refresh_late()
        identity=self.manifest["low_power"]["late_module"]
        identity["binary_bytes"] += 4
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,"identity disagrees"):
            read_proof.load_build(self.build)
        self.refresh_late()
        (self.late_dir/"completion.h").write_text("// changed")
        with self.assertRaisesRegex(ValueError,"Changed frozen source"):
            read_proof.load_build(self.build)

    def test_late_manifest_hash_and_decoder_header_membership_are_bound(self):
        self.add_late()
        path=self.late_dir/"manifest.json"
        path.write_text(path.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"Changed late manifest"):
            read_proof.load_build(self.build)
        self.late_manifest["sources"].pop(str(self.late_dir/"completion.h"))
        self.refresh_late()
        with self.assertRaisesRegex(ValueError,"Decoder header missing"):
            read_proof.load_build(self.build)

    def test_failed_partial_or_changed_loader_never_authorizes_blob_read(self):
        late=self.add_late()
        original=list(struct.unpack("<16I",self.late_proof))
        for index,value in ((0,0),(1,2),(2,1),(2,3),(3,1),(6,0x20),
                            (7,0),(7,3),(8,0),(9,0),(10,0),(11,0),
                            (12,0x10000),(13,1),(14,1),(15,0)):
            with self.subTest(index=index,value=value):
                words=original.copy()
                words[index]=value
                with self.assertRaises(ValueError):
                    read_proof.validate_late_loader(struct.pack("<16I",*words),late,{})
        with self.assertRaisesRegex(ValueError,"SAVE-return"):
            read_proof.validate_late_loader(self.late_proof,late,dict(loader_return=1))
        bad=original.copy()
        bad[2]=3
        calls,output,error=self.run_fake(struct.pack("<128I",*proof()),
                                        late_proof=struct.pack("<16I",*bad))
        self.assertIn("Late-loader proof",str(error))
        self.assertEqual(len(calls),3)
        self.assertNotIn("late_validation",json.loads((output/"result.json").read_text()))

    def test_live_late_byte_change_has_no_mutable_word_exception(self):
        self.add_late()
        bad=self.late_code[:-1]+bytes([self.late_code[-1]^1])
        calls,output,error=self.run_fake(struct.pack("<128I",*proof()),
                                        late_proof=self.late_proof,late_code=bad)
        self.assertIn("Live late completion bytes differ",str(error))
        self.assertEqual(len(calls),4)
        self.assertNotIn("late_validation",json.loads((output/"result.json").read_text()))

    def test_corrupt_proof_stops_before_live_code_and_retains_raw_evidence(self):
        words=proof()
        words[17]^=1
        raw=struct.pack("<128I",*words)
        calls,output,error=self.run_fake(raw)
        self.assertIn("No stable checksum-valid",str(error))
        self.assertEqual(len(calls),1)
        self.assertEqual((output/"shutdown-proof.bin").read_bytes(),raw)
        self.assertFalse(json.loads((output/"result.json").read_text())["stable_checksum_valid"])

    def test_live_code_mismatch_never_claims_receiver_verification(self):
        calls,output,error=self.run_fake(struct.pack("<128I",*proof()),live=b"\0"*len(self.code))
        self.assertIn("Live receiver immutable bytes differ",str(error))
        self.assertEqual(len(calls),2)
        result=json.loads((output/"result.json").read_text())
        self.assertNotIn("receiver_sha256",result)
        self.assertFalse(result["physical_entry_proven"])


if __name__=="__main__":
    unittest.main()
