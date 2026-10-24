"""Offline tests of the exact target polling code; never opens a device."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def function(source, signature):
    start = source.index(signature)
    first = source.index('{', start)
    depth = 1
    end = first + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t s[128], d[64];
#define S s
#define D d
#define CYCLES_PER_US 400UL
static struct { uint32_t CYCCNT; } timer;
#define DWT (&timer)
ENUMS
struct context { uint32_t result, uncertain; };
FAIL
static uint32_t values[16], value_count, calls, increment, failure_at;
static uint32_t security_calls, security_value, security_failure;
static int status(struct context *c) {
    ++calls; timer.CYCCNT += increment;
    if (calls == failure_at) { c->uncertain=1; fail(c, TRANSFER_TIMEOUT); return 0; }
    S[NOR_STATUS]=values[calls<=value_count ? calls-1 : value_count-1];
    return 1;
}
static int security(struct context *c) {
    ++security_calls;
    if (security_failure) { c->uncertain=1; fail(c, TRANSFER_TIMEOUT); return 0; }
    S[NOR_SECURITY]=security_value;
    return 1;
}
HEALTHY
#include "completion_poll.h"
FINISHED
static void setup(const uint32_t *v, uint32_t n) {
    memset(s,0,sizeof(s)); memset(d,0,sizeof(d));
    memcpy(values,v,n*sizeof(*v)); value_count=n;
    calls=security_calls=security_value=security_failure=failure_at=0;
    timer.CYCCNT=0; increment=400;
    S[STAGE]=ST_PROGRAM; S[ADDRESS]=0x6200;
}
#define SET(...) do { const uint32_t a[]={__VA_ARGS__}; setup(a,sizeof(a)/sizeof(a[0])); c=(struct context){0}; } while(0)
int main(void) {
    struct context c;
    SET(0,0); assert(write_finished(&c,10000)); assert(calls==2 && security_calls==1);
    SET(3,3,0,0); assert(write_finished(&c,10000)); assert(calls==4 && D[WEL_PENDING_READS]==0);
    SET(3,2,2,0); assert(write_finished(&c,10000));
    assert(calls==4 && D[WEL_PENDING_READS]==2 && D[PENDING_OPERATIONS]==1);
    assert(D[FIRST_PENDING_STAGE]==ST_PROGRAM && D[FIRST_PENDING_ADDRESS]==0x6200);
    assert(D[FIRST_PENDING_STATUS]==2 && D[FIRST_PENDING_ELAPSED]==800);
    SET(2,0); assert(write_finished(&c,10000)); assert(calls==2);
    SET(0,3,0,0); assert(write_finished(&c,10000)); assert(calls==4);
    SET(2); assert(!write_finished(&c,10)); assert(c.result==WEL_FAILURE && calls==10 && !security_calls);
    assert(D[FIRST_FAILURE_STATUS]==2 && D[FIRST_FAILURE_RESULT]==WEL_FAILURE);
    /* Cleanup-like later status/failure cannot erase the primary evidence. */
    c.result=OK; S[NOR_STATUS]=0; S[ADDRESS]=0; fail(&c,TRANSFER_ERROR);
    assert(D[FIRST_FAILURE_STATUS]==2 && D[FIRST_FAILURE_ADDRESS]==0x6200);
    SET(3); assert(!write_finished(&c,10)); assert(c.result==NOR_BUSY && calls==10 && !security_calls);
    SET(0,0); increment=2000; assert(!write_finished(&c,10)); assert(!security_calls && c.result);
    SET(2,0); failure_at=2; assert(!write_finished(&c,10000));
    assert(c.result==TRANSFER_TIMEOUT && c.uncertain && calls==2 && !security_calls);
    SET(0,0); security_failure=1; assert(!write_finished(&c,10000));
    assert(c.result==TRANSFER_TIMEOUT && c.uncertain && security_calls==1);
    SET(4,4); assert(!write_finished(&c,10000)); assert(c.result==PROTECTED_OR_FAILED);
    SET(0,0); security_value=0x20; assert(!write_finished(&c,10000)); assert(c.result==PROTECTED_OR_FAILED);
    SET(0,0); timer.CYCCNT=0xFFFFFF00U; assert(write_finished(&c,10000)); assert(D[LAST_ELAPSED]==800);
    SET(3); increment=0; assert(!write_finished(&c,10000)); assert(calls==1000000 && c.result==NOR_BUSY);
    SET(2); increment=0; assert(!write_finished(&c,10000)); assert(calls==1000000 && c.result==WEL_FAILURE);
    SET(2,0); assert(write_finished(&c,10000));
    value_count=1; values[0]=0; calls=0; S[ADDRESS]=0x6300;
    assert(write_finished(&c,10000));
    assert(D[COMPLETE_CALLS]==2 && D[TOTAL_READS]==4 && D[PENDING_OPERATIONS]==1);
    assert(D[FIRST_PENDING_ADDRESS]==0x6200 && D[LAST_ADDRESS]==0x6300);
    puts("16 exact-C completion scenarios passed");
    return 0;
}
'''


class CompletionTests(unittest.TestCase):
    def test_actual_target_polling(self):
        source = (HERE/'programmer.c').read_text()
        enums = '\n'.join(re.findall(r'enum \{.*?\};', source, re.S))
        code = HARNESS.replace('ENUMS', enums)
        code = code.replace('\nFAIL\n', '\n'+function(source, 'static void fail(')+'\n')
        code = code.replace('\nHEALTHY\n', '\n'+function(source, 'static int healthy(')+'\n')
        code = code.replace('\nFINISHED\n', '\n'+function(source, 'static int write_finished(')+'\n')
        with tempfile.TemporaryDirectory() as td:
            c = Path(td)/'test.c'
            exe = Path(td)/'test.exe'
            c.write_text(code)
            built = subprocess.run([shutil.which('clang'), '-std=c11', '-O2', '-Wall',
                            '-Wextra', '-Werror', '-I', str(HERE), str(c),
                            '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([exe], check=True, capture_output=True, text=True)
            self.assertIn('16 exact-C completion scenarios passed', result.stdout)

    def test_legacy_guard_transfer_and_verification_unchanged(self):
        old = (HERE.parent/'rom-nor-programmer/programmer.c').read_text()
        new = (HERE/'programmer.c').read_text()
        for signature in ('static int gap(', 'static int transfer(',
                          'static int status(', 'static int security(',
                          'static int healthy(', 'static int wait_idle(',
                          'static int write_enable(', 'static int preflight(',
                          'static void execute(', 'static uint32_t crc32_bytes(',
                          'static int compare('):
            self.assertEqual(function(old, signature), function(new, signature), signature)
        old_fields = re.search(r'enum \{ MAGIC,.*?STATUS_WORDS \};', old, re.S).group()
        self.assertIn(old_fields, new)
        for filename in ('entry.S', 'programmer.ld'):
            self.assertEqual((HERE/filename).read_bytes(),
                             (HERE.parent/'rom-nor-programmer'/filename).read_bytes())


if __name__ == '__main__':
    unittest.main()
