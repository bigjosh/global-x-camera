"""Render the verified numeric comparison; all timing models remain labelled."""
from pathlib import Path
import statistics
import replay

HERE=Path(__file__).resolve().parent
NAMES={0:'Stored',1:'Fast / None',2:'Fast / Sub',3:'Literal Huffman / Sub'}

def main():
    result=replay.replay();lines=['# Fixed-frame MCU comparison','',
        'Measured times are medians of the repetitions listed. CPU excludes the complete output callback. '
        'The frame, 400 MHz clock, sink behavior and every executable are bound by the archived records.','',
        '| Executable | Mode | Runs | PNG bytes | CPU ms | Conversion ms | DEFLATE ms | Framing ms |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    groups=[]
    for trial in result['trials']:
        if trial['diagnostic_only']:continue
        for g in trial['groups']:
            groups.append((trial,g))
            phase=g['phases_s'];lines.append(f"| {trial['name']} | {NAMES[g['mode']]} | {g['runs']} | {g['png_bytes']:,} | "
                f"{g['metrics']['cpu_s']['median']*1000:.3f} | {phase['conversion']['median']*1000:.3f} | "
                f"{phase['deflate']['median']*1000:.3f} | {phase['framing']['median']*1000:.3f} |")
    lines+=['','The following values are hypothetical payload-transfer models using 2,649,960 bytes/s '
        'from the prior one-bit SD test. They exclude storage initialization, metadata, altered busy time and contention; '
        'no concurrent write or DMA occurred in these compute trials.','',
        '| Executable | Mode | Serial CPU + write ms | Ideal max(CPU, write) ms | Two-buffer proxy ms | 32 KiB producer mean / p95 ms |',
        '|---|---|---:|---:|---:|---:|']
    for trial,g in groups:
        rows=[r for r in trial['runs'] if r['mode']==g['mode']];m=g['metrics']
        mean=statistics.median(r['producer_interval_proxy_full32k_s']['mean'] for r in rows)*1000
        p95=statistics.median(r['producer_interval_proxy_full32k_s']['p95'] for r in rows)*1000
        lines.append(f"| {trial['name']} | {NAMES[g['mode']]} | {m['modeled_serial_cpu_plus_write_s']['median']*1000:.3f} | "
            f"{m['modeled_ideal_overlap_s']['median']*1000:.3f} | {m['modeled_two_buffer_proxy_s']['median']*1000:.3f} | {mean:.3f} / {p95:.3f} |")
    lines+=['','Producer means/p95s are medians of each run’s full 32 KiB interval statistics; the final partial interval is excluded '
        'from that column but included in the two-buffer model. The producer clock excludes sink-body time only, '
        'so callback/timer-edge overhead remains. It is not interchangeable with total CPU time.','',
        'No speed result is assigned to failed PREPARE attempts. See [README.md](README.md) for context, '
        'the preserved failures and qualification limits.','']
    for trial in result['trials']:
        if not trial['diagnostic_only']:continue
        lines+=['## Instrumented diagnostic: '+trial['name'],'',
                'These coarse probes perturb execution and are excluded from the speed tables. '
                'The following disjoint intervals include probe/layout overhead.','',
                '| Run | Region | ms |','|---|---|---:|']
        for row in trial['runs']:
            for key,value in row['miniz_profile']['cpu_ms'].items():
                lines.append(f"| mode {row['mode']} / {row['repeat']} | {key} | {value:.3f} |")
        lines.append('')
    (HERE/'comparison.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':main()
