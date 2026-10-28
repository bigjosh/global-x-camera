
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
typedef struct { uint32_t IDR,ODR; } GPIO_TypeDef;
static GPIO_TypeDef f,g;
#define GPIOF (&f)
#define GPIOG (&g)
static uint32_t proof[512];
#define P proof
enum { MAGIC,VERSION,STATE,DIAG_ERROR,CLEANUP,BEGIN,END,DWT_HZ,
       RCC0,RCC1,RSTR0,CFGR1,CFGR2,IC1,PLL1A,PLL1B,PLL1C,DWT_CTRL,DEMCR,
       MDIO_HIGH0,MDIO_LOW,MDIO_HIGH1,MDC_LOW,MDC_HIGH,MDC_LOW2,
       CLOCK_LOW_FAIL,CLOCK_HIGH_FAIL,BIT_COUNT,SCAN_COUNT,MATCH_COUNT,
       FIRST_MATCH,RESTORE_MATCH,F0=32,G0=38,F1=44,G1=50,
       CONTROL=56,IPSR,MSP,MSPLIM,OLD_MSP,OLD_MSPLIM,RESERVED2,RESERVED3,
       A_ID1=64,A_ID2,A_BMCR0,A_BMCR1,A_REQUEST,A_AFTER0,A_AFTER1,
       A_RESTORED0,A_RESTORED1,A_POLLS,A_WRITES,A_RESTORE_WRITES,A_RESTORED,A_FAILURE_STAGE,A_RESTORE_ERROR,
       A_START=80,A_END,B_START,B_END,C_START,C_END,SETTLE_CYCLES,HOLD_CYCLES,
       A_LOOPS,B_LOOPS,C_LOOPS,A_RESTORE_ID1,A_RESTORE_ID2,MARKER_ERROR,D_SAFE,
       D0=96,D1=102 };

#define OK 0
static uint32_t tx[65],pos,response,host_released=1,phy_value=1;
static uint32_t registers[32],writes,badrestore;
static uint32_t bits(unsigned first,unsigned n) {
 uint32_t v=0;while(n--)v=(v<<1)|tx[first++];return v;
}
static void line(void) {f.IDR=(host_released&&phy_value)?16:0;}
static void put(GPIO_TypeDef *port,uint32_t pin,uint32_t high) {
 if(high)port->ODR|=1U<<pin;else port->ODR&=~(1U<<pin);
 if(port==GPIOF){assert(pin==4);host_released=high;line();return;}
 assert(port==GPIOG&&pin==11);g.IDR=high?2048:0;
 if(!high)return;
 tx[pos]=host_released;
 if(pos==45){
  for(unsigned n=0;n<32;n++)assert(tx[n]==1);
  assert(bits(32,2)==1&&(bits(34,2)==1||bits(34,2)==2)&&bits(36,5)==0);
  response=registers[bits(41,5)];
 }
 if(pos==63 && bits(34,2)==1) {
  assert(bits(41,5)==0 && bits(46,2)==2);uint32_t v=bits(48,16);
  assert(v==0x3000||v==0x3800);writes++;
  if(!(badrestore&&v==0x3000))registers[0]=v;
 }
 /* Output for NEXT sampling edge changes after THIS rising edge. */
 pos++;
 if(bits(34,2)!=2)phy_value=1;
 else if(pos==47)phy_value=0;
 else if(pos>=48&&pos<64)phy_value=(response>>(63-pos))&1;
 else phy_value=1;
 if(pos==65)pos=0;
 line();
}
static int delay(uint32_t cycles){assert(cycles==2000);return 0;}
static int clock_bit(uint32_t out,uint32_t *in)
{
 put(GPIOF,4,out);int e=delay(2000);if(e)return e;
 if(GPIOG->IDR&(1U<<11))P[CLOCK_LOW_FAIL]++;
 /* PHY advances data after rising MDC; sample the prior stable bit BEFORE it. */
 if(in)*in=(GPIOF->IDR>>4)&1;
 put(GPIOG,11,1);e=delay(2000);
 if(!e) {if(!(GPIOG->IDR&(1U<<11)))P[CLOCK_HIGH_FAIL]++;}
 put(GPIOG,11,0);P[BIT_COUNT]++;return e;
}
static int send_bits(uint32_t value,uint32_t bits)
{while(bits){--bits;int e=clock_bit((value>>bits)&1,0);if(e)return e;}return OK;}
static int read_reg(uint32_t address,uint32_t reg,uint32_t *value,uint32_t *ta)
{
 int e=send_bits(0xffffffffU,32);if(e)return e;
 e=send_bits(1,2);if(e)return e; /* ST01 */
 e=send_bits(2,2);if(e)return e; /* read OP10, no write operation exists */
 e=send_bits(address,5);if(e)return e;e=send_bits(reg,5);if(e)return e;
 e=clock_bit(1,0);if(e)return e;e=clock_bit(1,ta);if(e)return e;
 uint32_t v=0,bit=0;
 /* Complete the frame even for absent TA, preserving a clean next preamble. */
 for(uint32_t n=0;n<16;n++){e=clock_bit(1,&bit);if(e)return e;v=(v<<1)|bit;}
 e=clock_bit(1,0);if(!e)*value=v;return e;
}
static int checked_read(uint32_t reg,uint32_t *value)
{
 uint32_t ta=1;int e=read_reg(0,reg,value,&ta);return e?e:(ta?7:OK);
}
static int write_bmcr(uint32_t value)
{
 if(value!=0x3000&&value!=0x3800)return 8;
 int e=send_bits(0xffffffff,32);if(e)return e;
 e=send_bits(1,2);if(e)return e; /* ST01 */
 e=send_bits(1,2);if(e)return e; /* write OP01 */
 e=send_bits(0,5);if(e)return e;e=send_bits(0,5);if(e)return e;
 e=send_bits(2,2);if(e)return e;e=send_bits(value,16);if(e)return e;
 return clock_bit(1,0);
}
static int stable_bmcr(uint32_t expected,uint32_t pos)
{
 uint32_t a=0xffff,b=0xffff;int e=checked_read(0,&a);P[pos]=a;if(e)return e;
 e=checked_read(0,&b);P[pos+1]=b;if(e)return e;
 return a==expected&&b==expected?OK:9;
}
static int identify(uint32_t pos)
{
 uint32_t a=0xffff,b=0xffff;int e=checked_read(2,&a);P[pos]=a;if(e)return e;
 e=checked_read(3,&b);P[pos+1]=b;if(e)return e;
 return a==7&&b==0xc131?OK:6;
}

static int wait_cycles(uint32_t c,uint32_t *n){(void)c;(void)n;return 0;}
static int restore_bmcr(void)
{
 /* Exactly one write; retries are read-only. Clearing PD auto-resets the PHY. */
 P[A_RESTORE_WRITES]++;int e=write_bmcr(0x3000);if(e)return e;
 for(uint32_t n=1;n<=100;n++) {
  P[A_POLLS]=n;
  e=stable_bmcr(0x3000,A_RESTORED0);
  if(!e) {e=identify(A_RESTORE_ID1);if(!e){P[A_RESTORED]=1;return OK;}}
  int timer=wait_cycles(400000,0);if(timer)return timer;
 }
 return e?e:11;
}

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
