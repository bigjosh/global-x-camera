"""No instruments: mock the complete bench boundary and test load rejection."""
import importlib.util,json,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('mdio_test_module',HERE/'run.py')
module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)

class Tests(unittest.TestCase):
 def test_frozen_binary_and_source(self):
  m,code=module.checked_probe();self.assertEqual(len(code),2264)
  self.assertLess(m['load']+len(code),m['proof'])
 def test_proof_decoder_and_no_response_success(self):
  m,code=module.checked_probe();w=[0]*512
  w[:5]=[0x3144494d,1,4,0,0];w[7]=400000000
  w[19:25]=[1,0,1,0,1,0];w[27:32]=[4160,32,0,0xffffffff,1]
  for i in range(32):w[64+i*8:72+i*8]=[i,1,65535,1,65535,0,0,0]
  d=module.decode(struct.pack('<512I',*w))
  result=module.validate(d,m['park'],code,0,0,m)
  self.assertTrue(result['completed_and_restored']);self.assertFalse(result['phy_found'])
  for key in ('error','cleanup','clock_low_fail','clock_high_fail'):
   changed=dict(d);changed[key]=1
   self.assertFalse(module.validate(changed,m['park'],code,0,0,m)['completed_and_restored'])
  self.assertFalse(module.validate(d,m['park'],code,1,0,m)['completed_and_restored'])
  d['state']=15
  self.assertFalse(module.validate(d,m['park'],code,0,0,m)['completed_and_restored'])
 def test_disabled_or_reset_sram_stops_before_high_sram(self):
  main,code=module.isolated.checked(module.ISOLATED_BUILD)
  for enabled,reset in [(0x180,0),(0x18f,8)]:
   with self.subTest(enabled=enabled,reset=reset), tempfile.TemporaryDirectory(dir=HERE) as td:
    prior=Path(td)/'prior.json'
    prior.write_text(json.dumps({'passed':True,'session':main,'proof':{}}))
    calls=[]
    class FakeBench:
     def __init__(self,output):self.output=output
     def upload(self,address,size,name):
      calls.append(address)
      if address==0x5602824c:return struct.pack('<I',enabled)
      if address==0x5602820c:return struct.pack('<I',reset)
      raise AssertionError('Unexpected access beyond SRAM guard')
     def call(self,*a,**k):raise AssertionError('No halt or write allowed')
    with patch.object(module,'Bench',FakeBench),patch.object(module.isolated,'validate'):
     with self.assertRaisesRegex(ValueError,'gated/reset'):
      module.prepare(Path(td)/'run',prior)
    self.assertEqual(calls,[0x5602824c,0x5602820c])
 def test_failed_main_result_does_not_open_bench(self):
  with tempfile.TemporaryDirectory(dir=HERE) as td:
   prior=Path(td)/'prior.json';prior.write_text('{"passed":false}')
   with patch.object(module,'Bench',side_effect=AssertionError('No bench allowed')):
    with self.assertRaisesRegex(ValueError,'did not succeed'):module.prepare(Path(td)/'run',prior)

if __name__=='__main__':unittest.main()
