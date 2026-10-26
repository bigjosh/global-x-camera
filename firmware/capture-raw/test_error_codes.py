"""Compile and execute the actual pure blink classifier; no bench access."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ErrorCodeTests(unittest.TestCase):
    def test_compiled_error_origin_and_cause_precedence(self):
        compiler = shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "host C compiler required")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "error-codes.c"
            executable = Path(temp) / "error-codes.exe"
            source.write_text(HARNESS)
            subprocess.run([
                compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I" + str(HERE), "-I" + str(HERE.parent / "sd-storage"),
                "-I" + str(HERE.parent / "raw-slots"), str(source),
                "-o", str(executable),
            ], check=True)
            subprocess.run([str(executable)], check=True, timeout=10)


HARNESS = r'''
#include <assert.h>
#include "error_codes.h"

static uint32_t classify(uint32_t result,uint32_t where,uint32_t fault,
                         uint32_t sd,uint32_t slot,uint32_t armed)
{ return raw_error_blink_code(result,where,fault,sd,slot,armed); }

int main(void)
{
    _Static_assert(RAW_ERROR_LOW_BATTERY==1U,"battery policy");
    _Static_assert(RAW_ERROR_CAMERA_INIT==2U,"camera-init policy");
    _Static_assert(RAW_ERROR_FRAME==3U,"frame policy");
    _Static_assert(RAW_ERROR_STORAGE==4U,"storage policy");
    _Static_assert(RAW_ERROR_SAVE==5U,"save policy");
    _Static_assert(RAW_ERROR_INDEX==6U,"index policy");
    _Static_assert(RAW_ERROR_FULL==7U,"full policy");
    _Static_assert(RAW_ERROR_INTERNAL==8U,"explicit internal fallback");

    /* Successful records cannot acquire an error from stale auxiliary fields. */
    assert(classify(0,0xAF,1,SD_ERR_PRODUCER,MAGIC_SLOTS_ERR_FULL,1)==0);
    for(uint32_t r=0x100;r<0x200;r++)
        assert(classify(r,0,0,0,0,0)==2);
    for(uint32_t r=0x200;r<0x300;r++)
        assert(classify(r,0,0,0,0,1)==4);
    for(uint32_t r=0x500;r<0x600;r++)
        assert(classify(r,0,0,0,0,1)==3);

    assert(classify(0x605,5,0,0,0,0)==2);
    assert(classify(0x681,0x81,0,0,0,1)==3);
    assert(classify(0x675,0x75,0,0,0,1)==2);
    assert(classify(0x676,0x76,0,0,0,1)==2);
    assert(classify(0x675,0,0,0,0,1)==2);
    assert(classify(0x6AF,0,0,0,0,1)==8);
    assert(classify(0x6FF,0x7FFF,0,0,0,1)==8);
    assert(classify(0x6FF,0,0,0,0,1)==8);

    /* A failed scan is never permission to call the card full. */
    assert(classify(0x320|MAGIC_SLOTS_ERR_FULL,0,0,0,MAGIC_SLOTS_ERR_FULL,1)==7);
    assert(classify(0x320|MAGIC_SLOTS_ERR_IO,0,0,SD_ERR_DATA,MAGIC_SLOTS_ERR_IO,1)==4);
    assert(classify(0x325,0,0,0,0,1)==8);
    assert(classify(0x320|MAGIC_SLOTS_ERR_STATE,0,0,0,MAGIC_SLOTS_ERR_STATE,1)==8);

    /* SCR errors above 15 collide with slot-open result prefixes. */
    for(uint32_t sd=SD_ERR_ARGUMENT;sd<=SD_ERR_PRODUCER;sd++)
        assert(classify(0x300|sd,0,0,sd,0,1)==4);
    assert(classify(0x310|MAGIC_SLOTS_ERR_CAPACITY,0,0,0,MAGIC_SLOTS_ERR_CAPACITY,1)==8);
    assert(classify(0x310|MAGIC_SLOTS_ERR_ARGUMENT,0,0,0,MAGIC_SLOTS_ERR_ARGUMENT,1)==8);

    /* New-object marker/length/transport failure is code 5; an established
     * camera publication failure propagating through storage remains code 3. */
    for(uint32_t slot=MAGIC_SLOTS_ERR_ARGUMENT;slot<=MAGIC_SLOTS_ERR_NOT_IDLE;slot++) {
        assert(classify(0x330|slot,0,0,SD_ERR_DATA,slot,1)==5);
        assert(classify(0x330|slot,0,1,SD_ERR_DATA,slot,1)==3);
        assert(classify(0x330|slot,0,0,SD_ERR_PRODUCER,slot,1)==3);
    }
    assert(classify(0x340|1,0,0,0,0,1)==5);
    assert(classify(SD_ERR_COMMAND_TIMEOUT,0,0,SD_ERR_COMMAND_TIMEOUT,0,1)==5);
    assert(classify(SD_ERR_PRODUCER,0,0,SD_ERR_PRODUCER,0,1)==3);
    assert(classify(1,0,0,0,0,0)==8);
    assert(classify(2,0,0,0,0,0)==8);
    assert(classify(SD_ERR_PRODUCER+1,0,0,0,0,1)==8);
    assert(classify(0xF002,0,1,SD_ERR_PRODUCER,0,1)==8);
    assert(classify(0xFFFFFFFFU,0,1,SD_ERR_PRODUCER,0,1)==8);
    assert(classify(0x400|SD_ERR_DATA,0,0,SD_ERR_DATA,0,1)==8);

    /* No guessed battery/index condition from an arbitrary result value. */
    for(uint32_t r=1;r<0x10000U;r++) {
        uint32_t code=classify(r,0,0,0,0,1);
        assert(code>=2 && code<=8 && code!=6);
    }
    return 0;
}
'''


if __name__ == "__main__":
    unittest.main()
