"""Actual bit-clock/framing/restore C on a software-only rising-edge PHY model."""
from pathlib import Path
import ast,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
source=(HERE/'power_aba.c').read_text()
tree=ast.parse((HERE.parent/'v2/test_edge_model.py').read_text())
prefix=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='prefix' for t in n.targets))
enum=source[source.index('enum { MAGIC'):source.index('enum { OK')]
prefix=prefix.replace('enum {CLOCK_LOW_FAIL=25,CLOCK_HIGH_FAIL=26,BIT_COUNT=27};',enum)
prefix=prefix.replace('static uint32_t tx[65],pos,response,host_released=1,phy_value=1;',
 'static uint32_t tx[65],pos,response,host_released=1,phy_value=1;\nstatic uint32_t registers[32],writes,badrestore;')
prefix=prefix.replace('assert(bits(32,2)==1&&bits(34,2)==2&&bits(36,5)==0&&bits(41,5)==2);',
 'assert(bits(32,2)==1&&(bits(34,2)==1||bits(34,2)==2)&&bits(36,5)==0);\n  response=registers[bits(41,5)];')
prefix=prefix.replace('/* Output for NEXT sampling edge changes after THIS rising edge. */',
 '''if(pos==63 && bits(34,2)==1) {
  assert(bits(41,5)==0 && bits(46,2)==2);uint32_t v=bits(48,16);
  assert(v==0x3000||v==0x3800);writes++;
  if(!(badrestore&&v==0x3000))registers[0]=v;
 }
 /* Output for NEXT sampling edge changes after THIS rising edge. */''')
prefix=prefix.replace('if(pos==47)phy_value=0;', 'if(bits(34,2)!=2)phy_value=1;\n else if(pos==47)phy_value=0;')
body=source[source.index('static int clock_bit'):source.index('static int wait_cycles')]
restore=source[source.index('static int restore_bmcr'):source.index('__attribute__((used,noreturn,noinline))')]
suffix=r'''
static void setup(void) {
 memset(tx,0,sizeof(tx));memset(proof,0,sizeof(proof));memset(registers,0,sizeof(registers));
 pos=writes=badrestore=0;host_released=phy_value=1;f.ODR=16;g.ODR=g.IDR=0;line();
 registers[0]=0x3000;registers[2]=7;registers[3]=0xC131;
}
int main(void) {
 setup();assert(identify(A_ID1)==0);assert(stable_bmcr(0x3000,A_BMCR0)==0);
 assert(write_bmcr(0x3800)==0&&writes==1);assert(stable_bmcr(0x3800,A_AFTER0)==0);
 assert(restore_bmcr()==0&&registers[0]==0x3000&&writes==2);
 assert(P[A_RESTORED]==1&&P[A_RESTORE_WRITES]==1&&P[A_POLLS]==1&&P[A_RESTORE_ID2]==0xC131);
 assert(P[BIT_COUNT]==780&&pos==0&&P[CLOCK_LOW_FAIL]==0&&P[CLOCK_HIGH_FAIL]==0);
 setup();assert(write_bmcr(0x1000)==8&&writes==0&&P[BIT_COUNT]==0);
 setup();registers[3]=0xC132;assert(identify(A_ID1)==6&&writes==0);
 setup();registers[0]=0x3100;assert(stable_bmcr(0x3000,A_BMCR0)==9&&writes==0);
 setup();assert(write_bmcr(0x3800)==0);badrestore=1;
 assert(restore_bmcr()==9&&writes==2&&P[A_POLLS]==100&&P[A_RESTORED]==0);
 assert(P[A_RESTORE_WRITES]==1&&registers[0]==0x3800&&pos==0);
 puts("PASS: matched write/read/restore; bad ID/config refuses; restore timeout bounded with exactly one restore write");
 return 0;
}
'''
harness=HERE/'protocol_model.c';exe=HERE/'protocol_model.exe'
harness.write_text(prefix+body+'\nstatic int wait_cycles(uint32_t c,uint32_t *n){(void)c;(void)n;return 0;}\n'+restore+suffix)
subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror',str(harness),'-o',str(exe)],check=True)
result=subprocess.check_output([str(exe)],text=True).strip()
(HERE/'protocol-model-result.json').write_text(json.dumps({'hardware_access':False,'result':result,
 'source_sha256':hashlib.sha256((HERE/'power_aba.c').read_bytes()).hexdigest(),
 'scope':'Actual clock_bit/read/write/stability/restore functions retained; GPIO edges and delays simulated, no electrical qualification.'},indent=2)+'\n')
print(result)
