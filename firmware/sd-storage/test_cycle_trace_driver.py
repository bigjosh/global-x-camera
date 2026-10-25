"""Exercise trace hooks against the actual driver and its existing SD model.

The mock records event order, not hardware time. The ARM comparison checks that
disabled instrumentation leaves every allocatable object byte unchanged.
"""
from pathlib import Path
import importlib.util
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRACE = ROOT / 'firmware/capture-raw'
spec = importlib.util.spec_from_file_location('sd_driver_tests', HERE / 'test_sd_driver.py')
driver_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver_tests)
ARM_BIN = Path('D:/ST/STM32CubeIDE_1.15.1/STM32CubeIDE/plugins/') / (
    'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
    '12.3.rel1.win32_1.0.200.202406191623/tools/bin')


def allocatable_sections(path):
    """Avoid flattening overlapping address-zero sections of an ELF object."""
    blob = path.read_bytes()
    if blob[:6] != b'\x7fELF\x01\x01':
        raise ValueError('expected ELF32 little endian')
    offset = struct.unpack_from('<I',blob,32)[0]
    width,count,string_index = struct.unpack_from('<HHH',blob,46)
    headers = [struct.unpack_from('<10I',blob,offset+n*width) for n in range(count)]
    strings = headers[string_index]
    names = blob[strings[4]:strings[4]+strings[5]]
    sections = {}
    for item in headers:
        if not item[2]&2:
            continue
        name = names[item[0]:].split(b'\0',1)[0].decode()
        data = b'' if item[1]==8 else blob[item[4]:item[4]+item[5]]
        sections[name] = (item[1],item[2],item[5],data)
    return sections

TRACE_HEADER = r'''
#pragma once
#include "cycle_trace_sd.h"
static unsigned trace_sequence, trace_events[128], trace_counts[16];
#define CYCLE_MARK(name) (trace_events[CTE_##name]=++trace_sequence)
#define CYCLE_COUNT(name) (++trace_counts[CTC_##name])
static void clear_trace(void) {
    trace_sequence=0;
    for(unsigned &v:trace_events) v=0;
    for(unsigned &v:trace_counts) v=0;
}
'''

TRACE_CASES = r'''
    { auto c=reset_init_model(); clear_trace(); trace_acmd41_pending=3;
      assert(sd_init(&c,25000000U)==SD_OK);
      assert(trace_counts[CTC_SD_INIT_CALLS]==1);
      assert(trace_counts[CTC_SD_ACMD41_ATTEMPTS]==4);
      assert(trace_events[CTE_SD_CMD0_DONE]<trace_events[CTE_SD_CMD8_BEGIN]);
      assert(trace_events[CTE_SD_ACMD41_BEGIN]<trace_events[CTE_SD_ACMD41_DONE]);
      assert(trace_events[CTE_SD_CLOCK_SWITCH_DONE]<trace_events[CTE_SD_INIT_DONE]);
      assert(trace_events[CTE_SD_WIDTH_DONE]<trace_events[CTE_SD_INIT_DONE]);
      unsigned init_done=trace_events[CTE_SD_INIT_DONE];
      unsigned acmd_done=trace_events[CTE_SD_ACMD41_DONE];
      uint8_t block[512]; sd_scr_t scr{};
      assert(sd_read_blocks(&c,0,block,1)==SD_OK);
      assert(sd_read_blocks(&c,1,block,1)==SD_OK);
      assert(sd_read_scr(&c,&scr)==SD_OK);
      assert(trace_counts[CTC_SD_READ_TRANSFERS]==2);
      assert(trace_counts[CTC_SD_SCR_READS]==2);
      assert(trace_events[CTE_SD_READ_CMD_BEGIN_LATEST]<trace_events[CTE_SD_READ_CMD_DONE_LATEST]);
      assert(trace_events[CTE_SD_READ_CMD_DONE_LATEST]<trace_events[CTE_SD_READ_DATAEND_LATEST]);
      assert(trace_events[CTE_SD_READ_DATAEND_LATEST]<trace_events[CTE_SD_READ_LATEST_DONE]);
      assert(sd_deinit(&c)==SD_OK);
      assert(trace_events[CTE_SD_DEINIT_BEGIN]<trace_events[CTE_SD_DEINIT_RELEASE_BEGIN]);
      assert(trace_events[CTE_SD_DEINIT_RELEASE_BEGIN]<trace_events[CTE_SD_DEINIT_DONE]);
      assert(trace_counts[CTC_SD_DEINIT_CALLS]==1 && trace_counts[CTC_SD_SYNC_CALLS]==1);
      assert(trace_events[CTE_SD_INIT_DONE]==init_done && trace_events[CTE_SD_ACMD41_DONE]==acmd_done);
    }
    for(unsigned pio: {0U,1U}) {
      auto c=reset_model(); clear_trace(); stream_time=stream_check=true;
      StreamSource source{2048U,pio?512U:2048U,100U,200U,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_OK);
      assert(trace_counts[CTC_SD_WRITE_TRANSFERS]==1);
      assert(trace_counts[CTC_SD_IDMA_TRANSFERS]==!pio && trace_counts[CTC_SD_PIO_TRANSFERS]==pio);
      assert(trace_counts[CTC_SD_PREANNOUNCE_CALLS]==1 && trace_counts[CTC_SD_CMD25_CALLS]==1);
      assert(trace_counts[CTC_SD_CMD12_WRITE_CALLS]==1);
      assert(trace_events[CTE_SD_WRITE_READY_DONE]<trace_events[CTE_SD_PREANNOUNCE_BEGIN]);
      assert(trace_events[CTE_SD_PREANNOUNCE_DONE]<trace_events[CTE_SD_CMD25_BEGIN]);
      assert(trace_events[CTE_SD_CMD25_BEGIN]<trace_events[CTE_SD_CMD25_DONE]);
      assert(trace_events[CTE_SD_CMD25_DONE]<trace_events[CTE_SD_DATAEND]);
      assert(trace_events[CTE_SD_DATAEND]<trace_events[CTE_SD_CMD12_BEGIN]);
      assert(trace_events[CTE_SD_CMD12_DONE]<trace_events[CTE_SD_WRITE_FINAL_READY_BEGIN]);
      assert(trace_events[CTE_SD_WRITE_FINAL_READY_DONE]<trace_events[CTE_SD_WRITE_DONE]);
      assert(bool(trace_events[CTE_SD_IDMA_RELEASED])==!pio);
    }
    { auto c=reset_model(); clear_trace(); command_error=25;
      assert(sd_write_blocks_dma_preerase(&c,100,reinterpret_cast<void *>(uintptr_t(0x34000000U)),4)==SD_ERR_COMMAND_TIMEOUT);
      assert(trace_events[CTE_SD_CMD25_BEGIN] && !trace_events[CTE_SD_CMD25_DONE]);
      assert(trace_events[CTE_SD_LAST_ERROR] && trace_counts[CTC_SD_ERROR_CALLS]);
      assert(!trace_events[CTE_SD_DATAEND] && !trace_events[CTE_SD_WRITE_DONE]);
      assert(c.media_idle); /* Recovery does not manufacture a success stamp. */
    }
    { auto c=reset_init_model(); clear_trace(); command_error=8;
      assert(sd_init(&c,25000000U)==SD_ERR_COMMAND_TIMEOUT);
      assert(trace_events[CTE_SD_CMD0_DONE] && trace_events[CTE_SD_CMD8_BEGIN]);
      assert(!trace_events[CTE_SD_CMD8_DONE] && !trace_events[CTE_SD_INIT_DONE]);
    }
'''


class CycleTraceDriverTests(unittest.TestCase):
    def test_event_ids_are_unique_in_reserved_ranges(self):
        header = (TRACE / 'cycle_trace_sd.h').read_text()
        for prefix, lo, hi in (('CTE',64,119),('CTC',0,15)):
            values = [int(n) for n in re.findall(r'^#define '+prefix+r'_\w+ (\d+)$',header,re.M)]
            self.assertEqual(len(values),len(set(values)))
            self.assertTrue(all(lo<=v<=hi for v in values))

    def test_enabled_actual_driver_protocol_and_trace_semantics(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='sd-cycle-trace-') as folder:
            temp = Path(folder)
            (temp/'stm32n657xx.h').write_text(driver_tests.mock_header())
            (temp/'cycle_trace.h').write_text(TRACE_HEADER)
            source = (HERE/'test_sd_driver.cpp').read_text()
            source = 'static unsigned trace_acmd41_pending;\n'+source
            source = source.replace('else if(index==41) test_sd.RESP1.value=0xC0300000U;',
                'else if(index==41) test_sd.RESP1.value=trace_acmd41_pending ? '
                '(--trace_acmd41_pending,0x40300000U) : 0xC0300000U;')
            anchor = '#ifdef _WIN32\n    assert(VirtualFree(stream_memory,0,MEM_RELEASE));'
            self.assertEqual(source.count(anchor),1)
            source = source.replace(anchor,TRACE_CASES+'\n'+anchor)
            (temp/'trace_driver.cpp').write_text(source)
            (temp/'hook.cpp').write_text('extern "C" { unsigned sd_hook_calls=0; '
                'void sd_progress(void) { ++sd_hook_calls; } }\n')
            executable = temp/'trace-driver.exe'
            subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-DRAW_CYCLE_TRACE=1','-DSD_BUS_WIDTH=4','-DSD_CLOCK_NEGEDGE=1',
                '-I'+str(temp),'-I'+str(HERE),'-I'+str(TRACE),
                str(temp/'trace_driver.cpp'),str(temp/'hook.cpp'),'-o',str(executable)],check=True)
            result = subprocess.run([str(executable)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('protocol cases passed',result.stdout)

    def test_disabled_object_matches_before_trace(self):
        # Fixed pre-instrumentation revision: later commits must retain this
        # test's reference rather than accidentally comparing HEAD to itself.
        original = subprocess.check_output(['git','show','51c25de2:firmware/sd-storage/sd_card.c'],cwd=ROOT)
        with tempfile.TemporaryDirectory(prefix='sd-trace-identity-') as folder:
            temp = Path(folder)
            outputs = []
            for tag,content in (('before',original),('after',(HERE/'sd_card.c').read_bytes())):
                work=temp/tag;work.mkdir();(work/'sd_card.c').write_bytes(content)
                obj=work/'sd_card.o'
                subprocess.run([str(ARM_BIN/'arm-none-eabi-gcc.exe'),'-std=c11','-Os',
                    '-mcpu=cortex-m55','-mthumb','-DSTM32N657xx','-DCPU_IN_SECURE_STATE',
                    '-DSD_BUS_WIDTH=4','-DSD_CLOCK_NEGEDGE=1',
                    '-I'+str(HERE),'-I'+str(driver_tests.CMSIS/'Include'),
                    '-I'+str(driver_tests.CMSIS/'Device/ST/STM32N6xx/Include'),
                    '-c',str(work/'sd_card.c'),'-o',str(obj)],check=True)
                outputs.append(allocatable_sections(obj))
            self.assertEqual(outputs[0],outputs[1])


if __name__=='__main__':
    unittest.main()
