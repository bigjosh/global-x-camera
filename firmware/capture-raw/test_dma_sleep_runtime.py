"""Execute the actual transport coordinator; build admission is offline only."""
import argparse
import ast
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_dma_tail_wait import function

HERE = Path(__file__).resolve().parent

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "sd_card.h"
#define RP_FIRST_WRITE 0
#define RP_CHUNK_COUNT 1
static volatile uint32_t P[2],row[8];
static uintptr_t trace_address(void) {return (uintptr_t)row;}
#define RAW_CHUNK_TRACE_ADDRESS trace_address()
static struct {uint32_t CYCCNT;} dwt;
#define DWT (&dwt)
static sd_stream_t raw_stream;
static sd_dma_wait_t raw_dma_wait;
static uint32_t valid,stopped,available,prepare_calls,normal_calls,wait_calls,probe_calls;
static int prepare_result,driver_result;
static uint32_t order[8],order_count;
static sd_card_t card;
static uint8_t data[512];
uint32_t raw_capture_frame_validated(void) {return valid;}
uint32_t raw_capture_sensor_stopped(void) {return stopped;}
static uint32_t raw_capture_available(void) {return available;}
static int phase_gpio_emit(uint32_t event) {order[order_count++]=event;return 1;}
static void __DMB(void) {}
int raw_dma_sleep_prepare(void) {
    ++prepare_calls;order[order_count++]=100U;return prepare_result;
}
int sd_write_blocks_stream_preerase(sd_card_t *c,uint32_t lba,const void *buffer,
                                    uint32_t count,sd_stream_t *stream) {
    assert(c==&card && lba==100U && buffer==data && count==3730U && stream==&raw_stream);
    ++normal_calls;order[order_count++]=101U;return driver_result;
}
int sd_write_blocks_stream_preerase_wait(sd_card_t *c,uint32_t lba,const void *buffer,
                                         uint32_t count,sd_stream_t *stream,sd_dma_wait_t *wait) {
    assert(c==&card && lba==100U && buffer==data && count==3730U && stream==&raw_stream);
    /* A NULL fallback would call this and fail, rather than being mistaken
     * for the regular polling API. */
    assert(wait==&raw_dma_wait && valid && stopped && prepare_calls==1U && !prepare_result);
    ++wait_calls;order[order_count++]=102U;return driver_result;
}
int raw_dma_sleep_probe_run(sd_card_t *c,sd_dma_wait_t *wait) {
    assert(c==&card);
    assert(wait==((valid && stopped)?&raw_dma_wait:0));
    ++probe_calls;order[order_count++]=103U;return SD_ERR_WAIT;
}
'''

SUFFIX = r'''
static void reset(void) {
    memset((void *)P,0,sizeof(P));memset((void *)row,0xA5,sizeof(row));
    memset(order,0,sizeof(order));order_count=0;
    valid=stopped=1;available=1909600U;dwt.CYCCNT=123456U;
    prepare_calls=normal_calls=wait_calls=probe_calls=0;
    prepare_result=driver_result=0;
    card.last_ready_r1=0x900;card.transfer_cycles=1234U;
}
int main(void) {
    for(uint32_t conditions=0;conditions<4U;++conditions) {
        reset();valid=conditions&1U;stopped=(conditions>>1)&1U;
        int result=magic_transport(&card,100U,data,3730U,0);
#if RAW_DMA_SLEEP_PROBE
        assert(result==SD_ERR_WAIT && probe_calls==1U && !wait_calls && !normal_calls);
        assert(prepare_calls==(conditions==3U) && !P[RP_CHUNK_COUNT]);
        assert(row[0]==0xA5A5A5A5U && order[order_count-1U]==103U);
#else
        assert(!result && !probe_calls);
#if SD_DMA_SLEEP_PROFILE
        assert(prepare_calls==(conditions==3U) && wait_calls==(conditions==3U));
        assert(normal_calls==(conditions!=3U));
#else
        assert(!prepare_calls && !wait_calls && normal_calls==1U);
#endif
        assert(P[RP_CHUNK_COUNT]==1U && row[0]==123456U && row[1]==123456U);
        assert(row[2]==0 && row[3]==3730U && row[4]==1909600U && row[5]==0x900U);
        assert(row[6]==0 && row[7]==1234U && order[order_count-1U]==7U);
#endif
        assert(P[RP_FIRST_WRITE]==123456U && order[0]==6U);
    }
#if SD_DMA_SLEEP_PROFILE
    reset();prepare_result=SD_ERR_WAIT;
    assert(magic_transport(&card,100U,data,3730U,0)==SD_ERR_WAIT);
    assert(prepare_calls==1U && !wait_calls && !normal_calls && !probe_calls);
    assert(!P[RP_CHUNK_COUNT] && row[0]==0xA5A5A5A5U);
    assert(order_count==2U && order[0]==6U && order[1]==100U);
#endif
#if !RAW_DMA_SLEEP_PROBE
    /* Driver/producer-guard faults must reach the owner without a success
     * marker. The real publication/guard code is independently tested. */
    for(uint32_t complete=0;complete<2U;++complete) {
        reset();valid=stopped=complete;driver_result=SD_ERR_PRODUCER;
        assert(magic_transport(&card,100U,data,3730U,0)==SD_ERR_PRODUCER);
        assert(row[6]==SD_ERR_PRODUCER && P[RP_CHUNK_COUNT]==1U);
        assert(order[order_count-1U]!=7U && !probe_calls);
    }
#endif
    puts("actual DMA sleep transport selection/error cases passed");return 0;
}
'''


class DmaSleepRuntimeTests(unittest.TestCase):
    def test_actual_transport_selection_failure_and_probe_no_write(self):
        compiler = shutil.which('clang') or shutil.which('gcc')
        self.assertIsNotNone(compiler, 'host C compiler required')
        body = function((HERE / 'magic_runtime.inc').read_text(), 'static int magic_transport(')
        with tempfile.TemporaryDirectory(prefix='dma-sleep-runtime-') as temp:
            source = Path(temp) / 'transport.c'
            source.write_text(PREFIX + body + SUFFIX)
            for profile, probe in ((0, 0), (1, 0), (1, 1)):
                with self.subTest(profile=profile, probe=probe):
                    executable = Path(temp) / f'transport-{profile}-{probe}.exe'
                    result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-DSD_REVIEW_PROFILE=1', f'-DSD_DMA_SLEEP_PROFILE={profile}',
                        f'-DRAW_DMA_SLEEP_PROBE={probe}', '-I'+str(HERE.parent / 'sd-storage'),
                        str(source), '-o', str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_builder_admits_only_the_reviewed_magic_profile(self):
        # Execute the real main() parser and all admission branches, stopping
        # immediately before frozen-build input reads. No guards are mirrored.
        tree = ast.parse((HERE / 'build.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        boundary = next(index for index, node in enumerate(main.body)
                        if isinstance(node, ast.Assign) and any(
                            isinstance(target, ast.Name) and target.id == 'rbase' for target in node.targets))
        main.body = main.body[:boundary] + [ast.Return(ast.Name('a', ast.Load()))]
        module = ast.fix_missing_locations(ast.Module(body=[main], type_ignores=[]))
        scope = {'argparse': argparse, 'Path': Path, 'BASE': Path('unused-frozen-base')}
        exec(compile(module, str(HERE / 'build.py'), 'exec'), scope)
        selected = ['--out', 'not-created', '--sd-bus-width', '4', '--sd-clock-hz', '25000000',
                    '--sd-clock-negedge', '--sd-clock-negedge-init', '--sd-review-profile',
                    '--sd-startup-opt', '--magic-format', '--line-stream', '--async-stop',
                    '--ethernet-powerdown', '--sensor-single-frame', '--dma-sleep']

        def run(options):
            with patch.object(sys, 'argv', ['build.py', *options]), contextlib.redirect_stderr(io.StringIO()):
                return scope['main']()

        for suffix in ([], ['--dma-sleep-probe'], ['--flash', '--error-blinks'],
                       ['--flash', '--error-blinks', '--standby']):
            with self.subTest(allowed=suffix):
                options = run(selected + suffix)
                self.assertTrue(options.dma_sleep and options.magic_format and options.sensor_single_frame)
        for removed in ('--sensor-single-frame', '--ethernet-powerdown', '--sd-review-profile',
                        '--sd-startup-opt', '--line-stream', '--async-stop', '--sd-clock-negedge',
                        '--sd-clock-negedge-init'):
            with self.subTest(removed=removed), self.assertRaises(SystemExit) as error:
                run([value for value in selected if value != removed])
            self.assertEqual(error.exception.code, 2)
        for suffix in (['--sd-bus-width', '1'], ['--sd-clock-hz', '12500000'],
                       ['--sd-clock-hz', '50000000'], ['--cycle-trace'], ['--sd-init-gap-ms', '200'],
                       ['--transport', 'pio'], ['--preinit'], ['--snapshot'], ['--poison'],
                       ['--whole-image-preerase'], ['--raw-dma-tail-wait'], ['--sd-idma-read'],
                       ['--sd-read-diagnostics'], ['--sd-gpio-speed', '2'], ['--sd-fixed-compensation'],
                       ['--pattern', 'diagonal'], ['--exposure-coarse', '30000'],
                       ['--sensor-autostop'], ['--flash'],
                       ['--dma-sleep-probe', '--flash', '--error-blinks'],
                       ['--dma-sleep-probe', '--error-blinks'],
                       ['--dma-sleep-probe', '--standby']):
            with self.subTest(rejected=suffix), self.assertRaises(SystemExit) as error:
                run(selected + suffix)
            self.assertEqual(error.exception.code, 2)
        without_sleep = [value for value in selected if value != '--dma-sleep']
        with self.assertRaises(SystemExit) as error:
            run(without_sleep + ['--dma-sleep-probe'])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
