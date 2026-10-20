import sys,time,json,pathlib,threading
sys.path[:0]=['tmp/bringup/saleae-deps','tmp/bringup/vcp-deps','firmware/boot-timing']
from saleae import automation
from test_vcp_signal import summarize
out=pathlib.Path('tmp/bringup/vcp-install-20261019')/sys.argv[1]
out.mkdir()
control=pathlib.Path('tmp/bringup/vcp-install-20261019/js/control.json')
response=control.with_name('response.json')
def command(state):
    ident=state+'-'+str(time.monotonic_ns())
    control.write_text(json.dumps(dict(id=ident,state=state)))
    for _ in range(80):
        time.sleep(.1)
        r=json.loads(response.read_text(encoding='utf-8-sig'))
        if r.get('id')==ident:
            (out/(state+'.json')).write_text(json.dumps(r,indent=2))
            print(state,r['ok'],r['range'],flush=True)
            if not r['ok']: raise RuntimeError('power command failed')
            return r
    raise RuntimeError('mailbox timeout')
with automation.Manager.connect(port=10430,connect_timeout_seconds=5) as m:
    dc=automation.LogicDeviceConfiguration(enabled_digital_channels=[0,6],
        digital_sample_rate=6250000,digital_threshold_volts=3.3,
        enabled_analog_channels=[0,6],analog_sample_rate=31250)
    cc=automation.CaptureConfiguration(capture_mode=automation.ManualCaptureMode())
    with m.start_capture(device_id='6753424D9C96677D',
        device_configuration=dc,capture_configuration=cc) as c:
        uart=None
        writer=None
        try:
            time.sleep(.3);command('off');time.sleep(15)
            if len(sys.argv)>2:
                import serial
                from serial.tools import list_ports
                ports=[p for p in list_ports.comports() if p.vid==0x0483 and
                       p.pid==0x3754 and p.serial_number=='002100203335511035383531']
                assert len(ports)==1
                uart=serial.Serial(ports[0].device,1000000,write_timeout=2)
                uart.break_condition=False
                value=int(sys.argv[2],0)
                writer=threading.Thread(target=lambda:uart.write(bytes([value])*32768))
                writer.start()
            command('auto');time.sleep(1)
        finally:
            if writer:writer.join(3)
            if uart:
                uart.break_condition=False
                uart.reset_output_buffer()
                uart.close()
            command('auto');time.sleep(.3);c.stop()
            c.save_capture(str(out.resolve()/'power-cycle.sal'))
            c.export_raw_data_csv(str(out.resolve()),digital_channels=[0,6],analog_channels=[0,6])
s=summarize(out)
print(json.dumps(s['analog']),flush=True)
