"""Create the scoped cold-cycle variant of the reviewed current bin logger."""
from pathlib import Path
base=Path(__file__).resolve().parent
source=Path('tmp/bringup/error-blinks-20261026/led_current_trace.py').read_text()
def once(old,new):
    global source
    assert source.count(old)==1,old
    source=source.replace(old,new)
once('        self.pending = {}','        self.pending = {}\n        self.latest = {}\n        self.recent_current = []')
once('        self.emit(row)', '''        row['processed_monotonic'] = time.monotonic()
        self.latest[signal] = dict(row)
        if signal == 'current':
            self.recent_current.append(dict(row))
            self.recent_current = self.recent_current[-40:]
        self.emit(row)''')
once('power_or_gpio_control=False,','power_or_gpio_control="one measured cold cycle; no GPIO",')
once('                        ready = False','                        ready = False\n                        off_at = None\n                        on_at = None')
once('                            time.sleep(0.02)', '''                            if ready and off_at is None:
                                if initial[RANGE] != 128 or args.duration < 45:
                                    raise RuntimeError("Cold trace requires starting auto range and >=45s")
                                voltage=logger.latest.get("voltage",{})
                                v=voltage.get("mean")
                                if (v is None or not 4.5 < v < 5.5 or voltage.get('nonfinite_count',1) or
                                    not voltage.get('complete_bin') or time.monotonic()-voltage.get('processed_monotonic',0)>.5):
                                    raise RuntimeError("No valid 5V source; no power cycle")
                                off_start_sample=logger.latest.get('current',{}).get('sample_id_end_exclusive',0)
                                device.publish(RANGE,0,timeout=5.0)
                                if device.query(RANGE,timeout=5.0)!=0:
                                    raise RuntimeError("OFF range readback failed")
                                off_at=time.monotonic()
                                logger.emit(dict(event="power_off",**stamp(),range=0))
                            if off_at is not None and on_at is None and time.monotonic()-off_at>=15:
                                recent=list(logger.recent_current)[-20:]
                                if (len(recent)!=20 or any(
                                    x.get('mean') is None or abs(x['mean'])>=.0001 or x['nonfinite_count'] or
                                    not x['complete_bin'] or x['sample_id']<=off_start_sample or
                                    time.monotonic()-x['processed_monotonic']>.5 for x in recent) or
                                    any(a['sample_id_end_exclusive']!=b['sample_id'] for a,b in zip(recent,recent[1:]))):
                                    raise RuntimeError("Cold-cycle off verification failed; initial range is restored during cleanup, not a qualified boot")
                                if device.query(RANGE,timeout=5.0)!=0:
                                    raise RuntimeError("OFF range changed")
                                logger.emit(dict(event="off_verified",**stamp(),current=recent[-1],contiguous_bins=len(recent)))
                                device.publish(RANGE,128,timeout=5.0)
                                if device.query(RANGE,timeout=5.0)!=128:
                                    raise RuntimeError("ON range readback failed")
                                on_at=time.monotonic()
                                event=dict(event="power_on",**stamp(),range=128,off_s=on_at-off_at)
                                logger.emit(event)
                                args.output.with_suffix('.power-on.json').write_text(json.dumps(event,indent=2))
                                print(json.dumps(event),flush=True)
                            time.sleep(0.02)''')
once('                        if not ready:\n                            raise RuntimeError("Duration ended before both streams arrived")',
     '                        if not ready or on_at is None:\n                            raise RuntimeError("Duration ended without a verified cold-cycle launch")')
once('                                    device.publish(topic, initial[topic], timeout=5.0)',
     '                                    logger.emit(dict(event="cleanup_setting_restore", **stamp(), topic=topic, value=initial[topic], qualified_boot=False))\n                                    device.publish(topic, initial[topic], timeout=5.0)')
once('default=40.0','default=50.0')
source=source.replace('Range is not changed during acquisition. Restore only',
                      'A single authorized cold cycle changes range. Restore only')
source='''"""Root-only cold-cycle variant: starts powered/auto, switches off15s, verifies
near-zero current, switches on once and leaves power on after trace. The user
authorized cold firmware/error qualification. No UART, GPIO, flash or SD commands.
Generated from the reviewed bin logger; consult make_cold_trace.py for exact diff.
"""\n'''+source[source.index('import argparse'):]
(base/'cold_led_trace.py').write_text(source,newline='\n')
print(base/'cold_led_trace.py')
