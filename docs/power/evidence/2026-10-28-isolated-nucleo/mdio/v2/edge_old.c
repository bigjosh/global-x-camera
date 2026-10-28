
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
enum {CLOCK_LOW_FAIL=25,CLOCK_HIGH_FAIL=26,BIT_COUNT=27};
#define OK 0
static uint32_t tx[65],pos,response,host_released=1,phy_value=1;
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
  assert(bits(32,2)==1&&bits(34,2)==2&&bits(36,5)==0&&bits(41,5)==2);
 }
 /* Output for NEXT sampling edge changes after THIS rising edge. */
 pos++;
 if(pos==47)phy_value=0;
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
 put(GPIOG,11,1);e=delay(2000);
 if(!e) {if(!(GPIOG->IDR&(1U<<11)))P[CLOCK_HIGH_FAIL]++;if(in)*in=(GPIOF->IDR>>4)&1;}
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

int main(void) {
 const uint32_t cases[]={0,1,7,0xC131,0x8000,0xAAAA,0x5555,0xFFFF,0x3100};
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
  memset(tx,0,sizeof(tx));memset(proof,0,sizeof(proof));pos=0;host_released=phy_value=1;
  f.ODR=16;g.ODR=g.IDR=0;line();response=cases[i];uint32_t value=0,ta=99;
  assert(read_reg(0,2,&value,&ta)==0&&pos==0&&proof[BIT_COUNT]==65);
  assert(proof[CLOCK_LOW_FAIL]==0&&proof[CLOCK_HIGH_FAIL]==0);
#if NEW_EDGE
  assert(ta==0&&value==response);
#else
  assert(ta==(response>>15)&&value==(((response<<1)|1)&65535));
#endif
 }
 puts("PASS: nine patterns, actual clock_bit retained");return 0;
}
