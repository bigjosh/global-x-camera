import sys
from pathlib import Path
sys.path.insert(0,str(Path('firmware/boot-timing').resolve()))
from nor_bench import Bench
b=Bench(Path(sys.argv[1]))
b.upload(0x341037F0,2048,'secure-trace.bin')
b.upload(0x241077F0,2048,'nonsecure-trace.bin')
