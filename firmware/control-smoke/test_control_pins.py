"""Execute actual pin setup/stop code with adversarial initial GPIO state."""
import ast
import copy
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def function(source, name):
    declaration = re.search(r'static void ' + name + r'\([^;{}]*\)\s*\{', source)
    begin = declaration.start()
    opening = declaration.end() - 1
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[begin:end]


class ControlPinRegression(unittest.TestCase):
    def test_actual_pin_setup_and_stop_preserve_hold_and_unrelated_pins(self):
        source = (HERE / 'control.c').read_text()
        setup = '\n'.join(function(source, name) for name in
                          ('output', 'configure_control_pins', 'excitation_off'))
        # The first peripheral operation asserts PA2; none of the endpoint
        # setup, sampling or terminal paths may lower or float it.
        main = source[source.index('void control_main(void)'):]
        self.assertLess(main.index('output(GPIOA,2,1);'), main.index('for(unsigned i=0;i<64;i++)'))
        self.assertNotIn('output(GPIOA,2,0)', source)
        self.assertNotIn('GPIOH->', source)
        self.assertNotIn('GPIOD->', source)
        self.assertNotIn('PWR_SVMCR1_VDDIO4', source)
        self.assertIn('excitation_off();', function(source, 'finish'))
        harness = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint32_t MODER,OTYPER,PUPDR,OSPEEDR,BSRR,ODR;} GPIO_TypeDef;
static GPIO_TypeDef ga,gc,gf;
struct {uint32_t AHB4ENR;} rcc;
#define GPIOA (&ga)
#define GPIOC (&gc)
#define GPIOF (&gf)
#define RCC (&rcc)
#define RCC_AHB4ENR_GPIOFEN 0x20U
static void barrier(void) {
 GPIO_TypeDef *ports[]={&ga,&gc,&gf};
 for(unsigned i=0;i<3;i++) {
  GPIO_TypeDef *p=ports[i];
  p->ODR=(p->ODR|(p->BSRR&0xffffU))&~(p->BSRR>>16);p->BSRR=0;
 }
}
#define __DSB() barrier()
SOURCE
static uint32_t seed=0x1459bc31U;
static uint32_t next(void) {seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void randomize(GPIO_TypeDef *p) {
 p->MODER=next();p->OTYPER=next();p->PUPDR=next();p->OSPEEDR=next();p->ODR=next()&0xffffU;p->BSRR=0;
}
#define CHECK(x) do {if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void) {
 const uint32_t analog=(3U<<16)|(3U<<18)|(3U<<20)|(3U<<24);
 const uint32_t ends=(3U<<10)|(3U<<12),end_bits=(1U<<5)|(1U<<6);
 for(unsigned i=0;i<4096;i++) {
  randomize(&ga);randomize(&gc);randomize(&gf);
  output(GPIOA,2,1);
  GPIO_TypeDef olda=ga,oldc=gc,oldf=gf;
  configure_control_pins();
  CHECK(ga.MODER==(olda.MODER|analog));CHECK(ga.PUPDR==(olda.PUPDR&~analog));
  CHECK(ga.OTYPER==olda.OTYPER&&ga.OSPEEDR==olda.OSPEEDR&&ga.ODR==olda.ODR);
  CHECK((ga.MODER&(3U<<4))==(1U<<4));CHECK(ga.ODR&(1U<<2));
  CHECK(gc.MODER==(oldc.MODER&~(3U<<20)));CHECK(gc.PUPDR==(oldc.PUPDR&~(3U<<20)));
  CHECK(gc.ODR==oldc.ODR&&gc.OTYPER==oldc.OTYPER&&gc.OSPEEDR==oldc.OSPEEDR);
  CHECK(gf.MODER==((oldf.MODER&~ends)|(1U<<10)|(1U<<12)));
  CHECK(gf.PUPDR==(oldf.PUPDR&~ends));CHECK(gf.OSPEEDR==(oldf.OSPEEDR&~ends));
  CHECK(gf.OTYPER==(oldf.OTYPER&~end_bits));CHECK(gf.ODR==(oldf.ODR&~end_bits));
  output(GPIOF,6,1);CHECK((gf.ODR&end_bits)==(1U<<6));
  olda=ga;oldc=gc;oldf=gf;rcc.AHB4ENR=RCC_AHB4ENR_GPIOFEN;
  excitation_off();barrier();
  CHECK(memcmp(&ga,&olda,sizeof ga)==0);CHECK(memcmp(&gc,&oldc,sizeof gc)==0);
  oldf.ODR&=~(1U<<6);CHECK(memcmp(&gf,&oldf,sizeof gf)==0);
  CHECK(ga.ODR&(1U<<2));
  rcc.AHB4ENR=0;gf.BSRR=0;excitation_off();CHECK(gf.BSRR==0);
 }
 puts("4096 canonical pin/stop cases preserved HOLD and unrelated GPIOs");return 0;
}
'''.replace('SOURCE', setup)
        compiler = shutil.which('clang') or shutil.which('gcc')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='control-pins-') as folder:
            folder = Path(folder)
            c, exe = folder / 'pins.c', folder / 'pins.exe'
            c.write_text(harness)
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(c), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn('4096 canonical pin/stop cases preserved HOLD', result.stdout)

    def test_old_schema_cannot_be_launched_as_current_wiring(self):
        # Compile only the pure contract function; never import a bench client.
        tree = ast.parse((HERE / 'console.py').read_text())
        target = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                      and x.name == 'require_current_wiring')
        namespace = {}
        exec(compile(ast.Module(body=[target], type_ignores=[]), 'contract', 'exec'), namespace)
        check = namespace['require_current_wiring']
        good = dict(schema=3, adc='ADC1_INP10/PA9',
                    wiring=dict(low='A0/CN4.1/PF5', wiper='A1/CN4.2/PA9',
                                high='A2/CN4.3/PF6', hold='A3/CN4.4/PA2'),
                    endpoint_channels={'A0': 'ADC1_INP5/PA8', 'A2': 'ADC1_INP11/PA10'})
        check(good)
        for key, value in (('schema', 1), ('schema', 2), ('adc', 'ADC1_INP16/PF3')):
            bad = copy.deepcopy(good);bad[key] = value
            with self.assertRaises(ValueError):
                check(bad)
        for key in ('low', 'wiper', 'high', 'hold'):
            bad = copy.deepcopy(good);bad['wiring'][key] = 'historical mapping'
            with self.assertRaises(ValueError):
                check(bad)
        # Both mutation entry points must check the new build before opening
        # any output folder or constructing a hardware client.
        for name in ('prepare', 'replace'):
            target = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name)
            text = ast.unparse(target)
            self.assertLess(text.index('require_current_wiring(m)'), text.index('args.out.mkdir'))


if __name__ == '__main__':
    unittest.main()
