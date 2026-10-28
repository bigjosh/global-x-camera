"""Read-only SRAM evidence after a failed test; no reset/halt/writes or idle claim."""
import sys, json, struct, importlib.util, hashlib
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location('raw_bench',root/'firmware/capture-raw/bench.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
build,out=map(Path,sys.argv[1:3]);out.mkdir(exist_ok=False)
m=json.loads((build/'manifest.json').read_text());bench.checked_build(build,m['binary_sha256'])
b=bench.sd.Bench(out/'reads')
p=bench.decode(b.upload(m['proof'],384,'proof.bin'),bench.fields(build))
names=('sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned').split()
card=dict(zip(names,struct.unpack('<6Q38I',b.upload(m['card'],200,'card.bin'))))
gpio_raw=b.upload(m['sd_clk_gpio_proof'],48,'clk-gpio.bin')
gpio=dict(zip(('magic','version','requested_speed','clk_mask','c_mask','c_before','c_configured','c_after','e_mask','e_before','e_after','applied'),struct.unpack('<12I',gpio_raw)))
width=bench.width_snapshot(b,m,'failed')
code=b.upload(m['load'],m['immutable_bytes'],'code.bin')
code_match=code==(build/'capture.bin').read_bytes()[:m['immutable_bytes']]
scb=struct.unpack('<16I',b.upload(0xE000ED00,64,'scb.bin'))
result=dict(raw=p,card=card,clk_gpio_speed_proof=gpio,bus_width_proof=width,build=str(build),binary_sha256=m['binary_sha256'],immutable_code_matches=code_match,cfsr=scb[10],hfsr=scb[11],read_only=True,halt=False,reset=False,failed_operation_not_idle_permission=True)
(out/'snapshot.json').write_text(json.dumps(result,indent=2))
print(json.dumps(dict(card=card,clk=gpio,code_match=code_match,cfsr=scb[10],hfsr=scb[11]),indent=2))
