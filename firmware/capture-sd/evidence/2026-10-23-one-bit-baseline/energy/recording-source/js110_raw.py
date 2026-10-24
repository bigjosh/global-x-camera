"""Optional raw-sample sink for the existing JS110 owner; no device API here.

The factory extends the existing queue/worker and settings lifecycle. Each
signal is an append-only little-endian float32 file. Native sample IDs and file
offsets are in chunks.jsonl; manifest.json is published only after the worker
has stopped. A byte-budget failure invalidates the recording, never truncates
a supposedly successful waveform.
"""
import hashlib
import json
from pathlib import Path
import zlib

MEASUREMENT_TOPICS = (
    "s/i/range/select", "s/v/range/select", "s/i/range/mode",
    "s/i/range/pre", "s/i/range/win", "s/i/range/win_sz", "s/i/range/post",
    "s/i/lsb_src", "s/v/lsb_src",
)


def make_raw_stream(base_class, directory, max_bytes=4 * 1024**3, *, queue_chunks=64):
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("Raw byte budget must be a positive integer")
    if type(queue_chunks) is not int or not 1 <= queue_chunks <= 1024:
        raise ValueError("Raw queue size must be an integer between 1 and 1024")

    class RawStream(base_class):
        def __init__(self):
            self.raw_root = Path(directory)
            self.raw_root.mkdir(parents=True, exist_ok=False)
            self.raw_files = {}
            self.raw_hashes = {}
            self.raw_bytes = {}
            self.raw_total = 0
            self.raw_finalized = False
            self.measurement_settings = None
            self.range_commands = []
            try:
                for signal in ("current", "voltage", "power"):
                    self.raw_files[signal] = (self.raw_root / (signal + ".f32")).open("xb")
                    self.raw_hashes[signal] = hashlib.sha256()
                    self.raw_bytes[signal] = 0
                super().__init__(self.raw_root / "chunks.jsonl", include_power=True,
                                 queue_chunks=queue_chunks)
            except BaseException:
                for output in self.raw_files.values():
                    output.close()
                raise

        def snapshot_measurement_settings(self, device):
            # Read only. In particular do not turn suppression off or change
            # an LSB/GPIO route while trying to improve a measurement.
            self.measurement_settings = {
                topic: device.query(topic, timeout=5.0) for topic in MEASUREMENT_TOPICS}
            return dict(self.measurement_settings)

        def note_range_command(self, state, value, command_start, command_end):
            self.range_commands.append(dict(state=state, retained_range=value,
                command_start=command_start, command_end=command_end,
                scope="host diagnostics only; not physical sample boundaries"))

        def _write(self, record):
            if record.get("event") == "stream_start":
                record.update(raw_schema=1, raw_dtype="<f4", raw_max_bytes=max_bytes,
                              raw_queue_chunks=queue_chunks,
                              aggregation="Exact float32 samples plus per-chunk summaries",
                              raw_signal_files={s: s + ".f32" for s in self.raw_files})
            return super()._write(record)

        def summarize(self, topic, received, value):
            record = super().summarize(topic, received, value)
            data = self.np.asarray(value["data"])
            # The official JS110 float streams are f32. Do not silently round
            # another representation and then attach the original summaries.
            if data.dtype.kind != "f" or data.dtype.itemsize != 4:
                raise ValueError("Raw recording requires delivered float32 samples")
            payload = data.astype("<f4", copy=False).tobytes(order="C")
            if self.raw_total + len(payload) > max_bytes:
                raise RuntimeError("Raw recording byte budget exceeded")
            signal = record["signal"]
            record.update(raw_file=signal + ".f32",
                          raw_byte_offset=self.raw_bytes[signal],
                          raw_byte_count=len(payload),
                          raw_crc32=f"{zlib.crc32(payload):08x}")
            written = self.raw_files[signal].write(payload)
            if written != len(payload):
                raise OSError("Short raw waveform write")
            self.raw_hashes[signal].update(payload)
            self.raw_bytes[signal] += written
            self.raw_total += written
            return record

        def close(self):
            result = super().close()
            if not self.raw_finalized and not self.thread.is_alive():
                self.raw_finalized = True
                close_errors = []
                for output in self.raw_files.values():
                    try:
                        output.close()
                    except OSError as exc:
                        close_errors.append(str(exc))
                if close_errors:
                    with self.lock:
                        self.error = self.error or "; ".join(close_errors)
                    result = self.status()
                manifest = {
                    "schema": 1,
                    "dtype": "<f4",
                    "raw_queue_chunks": queue_chunks,
                    "sample_ids": "native ticks, shared current/voltage/power timeline",
                    "finalized": result["complete"] and result["coverage"]["passed"],
                    "status": result,
                    "starting_measurement_settings": self.measurement_settings,
                    "range_commands": list(self.range_commands),
                    "files": {
                        signal: {"path": signal + ".f32", "bytes": self.raw_bytes[signal],
                                 "sha256": self.raw_hashes[signal].hexdigest()}
                        for signal in self.raw_files},
                    "chunks_sha256": hashlib.sha256(
                        (self.raw_root / "chunks.jsonl").read_bytes()).hexdigest(),
                    "measurement_boundary": "JS110 input, not isolated DUT energy",
                    "limits": [
                        "IN+ voltage does not observe the switched target rail.",
                        "No GPIO marker is captured or configured.",
                        "Range, suppression, clipping and analog accuracy need separate qualification.",
                        "Logging completion alone does not qualify a power or sleep transition.",
                    ],
                }
                try:
                    (self.raw_root / "manifest.json").write_text(
                        json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                except OSError as exc:
                    with self.lock:
                        self.error = self.error or str(exc)
                    result = self.status()
            return result

    return RawStream()
