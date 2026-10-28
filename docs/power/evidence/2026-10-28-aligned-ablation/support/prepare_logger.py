from pathlib import Path
root=Path(__file__).resolve().parents[3]
src=(root/'tmp/bringup/js-gpi-smoke-20261028/gpi_capture.py').read_text()
old="    ap.add_argument('--pd0-test',action='store_true')"
assert src.count(old)==1
src=src.replace(old,old+"\n    ap.add_argument('--armed-file',type=Path); ap.add_argument('--duration',type=float,default=6)")
old="                    else:time.sleep(1)"
assert src.count(old)==1
src=src.replace(old,"""                    elif a.armed_file:
                        a.armed_file.write_text(json.dumps(stamp()))
                        event('recorder_armed')
                        until=time.monotonic()+a.duration
                        while time.monotonic()<until: observations();time.sleep(.05)
                    else:time.sleep(1)""")
(Path(__file__).parent/'aligned_logger.py').write_text(src)
