/* Bounded read-only PHY investigation. PF4 MDIO, PG11 MDC; C02/ODB/DS14791.
 * No PHY register writes, MAC enable, reset, storage/camera or supply action.
 * Run only from an owner-verified privileged secure awake RAM park, 400 MHz.
 */
#include "stm32n6xx.h"
#define P ((volatile uint32_t *)0x343C6000U)
#define CLK (RCC_AHB4ENR_GPIOFEN|RCC_AHB4ENR_GPIOGEN)
#define RST (RCC_AHB4RSTR_GPIOFRST|RCC_AHB4RSTR_GPIOGRST)
enum { MAGIC,VERSION,STATE,DIAG_ERROR,CLEANUP,BEGIN,END,DWT_HZ,
       RCC0,RCC1,RSTR0,CFGR1,CFGR2,IC1,PLL1A,PLL1B,PLL1C,DWT_CTRL,DEMCR,
       MDIO_HIGH0,MDIO_LOW,MDIO_HIGH1,MDC_LOW,MDC_HIGH,MDC_LOW2,
       CLOCK_LOW_FAIL,CLOCK_HIGH_FAIL,BIT_COUNT,SCAN_COUNT,MATCH_COUNT,
       FIRST_MATCH,RESTORE_MATCH,F0=32,G0=38,F1=44,G1=50,
       CONTROL=56,IPSR,MSP,MSPLIM,OLD_MSP,OLD_MSPLIM,RESERVED2,RESERVED3,
       ROWS=64 };
enum { OK=0,CONTEXT=1,CLOCK=2,TIMER=3,PAD=4,RESTORE=5,IDENTITY=6 };
typedef struct {uint32_t mode,type,speed,pull,af,odr;} pin_state;
typedef struct {pin_state f,g;uint32_t added,configured;} bus_state;
static int delay(uint32_t cycles)
{
 const uint32_t begin=DWT->CYCCNT;
 for(uint32_t n=0;n<500000U;n++)if((uint32_t)(DWT->CYCCNT-begin)>=cycles)return OK;
 return TIMER;
}
static void field(volatile uint32_t *reg,uint32_t mask,uint32_t bits)
{*reg=(*reg&~mask)|(bits&mask);}
static void put(GPIO_TypeDef *g,uint32_t pin,uint32_t high)
{g->BSRR=1U<<(pin+(high?0U:16U));}
static pin_state snapshot(GPIO_TypeDef *g,uint32_t n)
{
 pin_state s={(g->MODER>>(2*n))&3,(g->OTYPER>>n)&1,(g->OSPEEDR>>(2*n))&3,
              (g->PUPDR>>(2*n))&3,(g->AFR[n/8]>>((n%8)*4))&15,(g->ODR>>n)&1};return s;
}
static void record(uint32_t pos,pin_state s)
{P[pos]=s.mode;P[pos+1]=s.type;P[pos+2]=s.speed;P[pos+3]=s.pull;P[pos+4]=s.af;P[pos+5]=s.odr;}
static int equal(pin_state a,pin_state b)
{return a.mode==b.mode&&a.type==b.type&&a.speed==b.speed&&a.pull==b.pull&&a.af==b.af&&a.odr==b.odr;}
static void restore_pin(GPIO_TypeDef *g,uint32_t n,pin_state s)
{
 field(&g->MODER,3U<<(2*n),0);field(&g->OTYPER,1U<<n,s.type<<n);
 field(&g->OSPEEDR,3U<<(2*n),s.speed<<(2*n));field(&g->PUPDR,3U<<(2*n),s.pull<<(2*n));
 field(&g->AFR[n/8],15U<<((n%8)*4),s.af<<((n%8)*4));put(g,n,s.odr);
 field(&g->MODER,3U<<(2*n),s.mode<<(2*n));
}
static int open_bus(bus_state *b)
{
 b->added=0;b->configured=0;P[RCC0]=RCC->AHB4ENR;P[RSTR0]=RCC->AHB4RSTR;
 if(P[RSTR0]&RST)return CLOCK;
 b->added=CLK&~P[RCC0];if(b->added)RCC->AHB4ENSR=b->added;__DSB();__ISB();
 if((RCC->AHB4ENR&CLK)!=CLK)return CLOCK;
 b->f=snapshot(GPIOF,4);b->g=snapshot(GPIOG,11);record(F0,b->f);record(G0,b->g);
 uint32_t pm=__get_PRIMASK();__disable_irq();
 field(&GPIOF->MODER,3U<<8,0);field(&GPIOG->MODER,3U<<22,0);
 put(GPIOF,4,1);put(GPIOG,11,0);
 field(&GPIOF->OTYPER,1U<<4,1U<<4);field(&GPIOG->OTYPER,1U<<11,0);
 field(&GPIOF->PUPDR,3U<<8,0);field(&GPIOG->PUPDR,3U<<22,0);
 field(&GPIOF->OSPEEDR,3U<<8,0);field(&GPIOG->OSPEEDR,3U<<22,0);
 field(&GPIOF->MODER,3U<<8,1U<<8);field(&GPIOG->MODER,3U<<22,1U<<22);
 b->configured=1;__DSB();__set_PRIMASK(pm);return delay(2000);
}
static int close_bus(bus_state *b)
{
 int e=OK;
 if(b->configured) {
  if((RCC->AHB4ENR&CLK)!=CLK||(RCC->AHB4RSTR&RST))e=CLOCK;
  else {
   uint32_t pm=__get_PRIMASK();__disable_irq();
   put(GPIOF,4,1);put(GPIOG,11,0);restore_pin(GPIOF,4,b->f);restore_pin(GPIOG,11,b->g);
   __DSB();__set_PRIMASK(pm);pin_state f=snapshot(GPIOF,4),g=snapshot(GPIOG,11);
   record(F1,f);record(G1,g);P[RESTORE_MATCH]=equal(f,b->f)&&equal(g,b->g);
   if(!P[RESTORE_MATCH])e=RESTORE;
  }
 }
 if(b->added)RCC->AHB4ENCR=b->added;
 __DSB();__ISB();
 P[RCC1]=RCC->AHB4ENR;if((P[RCC1]&CLK)!=(P[RCC0]&CLK))e=RESTORE;
 return e; /* No GPIO register accesses after removing clocks. */
}
static int pad_checks(void)
{
 P[MDIO_HIGH0]=(GPIOF->IDR>>4)&1;P[MDC_LOW]=(GPIOG->IDR>>11)&1;
 put(GPIOF,4,0);int e=delay(2000);if(e)return e;P[MDIO_LOW]=(GPIOF->IDR>>4)&1;
 put(GPIOF,4,1);e=delay(2000);if(e)return e;P[MDIO_HIGH1]=(GPIOF->IDR>>4)&1;
 /* Released MDIO throughout the MDC pulse: no write frame can be generated. */
 put(GPIOG,11,1);e=delay(2000);if(e)return e;P[MDC_HIGH]=(GPIOG->IDR>>11)&1;
 put(GPIOG,11,0);e=delay(2000);if(e)return e;P[MDC_LOW2]=(GPIOG->IDR>>11)&1;
 return P[MDIO_HIGH0]==1&&P[MDIO_LOW]==0&&P[MDIO_HIGH1]==1&&
        P[MDC_LOW]==0&&P[MDC_HIGH]==1&&P[MDC_LOW2]==0?OK:PAD;
}
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
static int scan(void)
{
 for(uint32_t address=0;address<32;address++) {
  volatile uint32_t *r=P+ROWS+address*8;uint32_t a=0xffff,b=0xffff,ta=1,tb=1;
  r[0]=address;int e=read_reg(address,2,&a,&ta);if(e)return e;
  r[1]=ta;r[2]=a;e=read_reg(address,3,&b,&tb);if(e)return e;r[3]=tb;r[4]=b;
  if(!ta&&!tb&&a==7&&(b&0xfff0)==0xc130) {
   r[5]=1;P[MATCH_COUNT]++;if(P[FIRST_MATCH]==0xffffffff)P[FIRST_MATCH]=address;
   uint32_t c=0xffff,d=0xffff,tc=1,td=1;
   e=read_reg(address,0,&c,&tc);if(e)return e;e=read_reg(address,0,&d,&td);if(e)return e;
   r[6]=c;r[7]=d;if(tc||td||c!=d)r[5]=2; /* ID found, BMCR not stable/acknowledged */
  }
  P[SCAN_COUNT]=address+1;
 }
 return P[CLOCK_LOW_FAIL]||P[CLOCK_HIGH_FAIL]?PAD:OK;
}
__attribute__((used,noreturn,noinline)) void mdio_diag_main(uint32_t old_msp,uint32_t old_msplim)
{
 for(uint32_t n=0;n<512;n++)P[n]=0;
 P[MAGIC]=0x3144494dU;P[VERSION]=2;P[STATE]=1;P[BEGIN]=DWT->CYCCNT;
 P[FIRST_MATCH]=0xffffffff;P[DWT_HZ]=400000000;
 P[CONTROL]=__get_CONTROL();P[IPSR]=__get_IPSR();P[MSP]=__get_MSP();P[MSPLIM]=__get_MSPLIM();
 P[OLD_MSP]=old_msp;P[OLD_MSPLIM]=old_msplim;
 P[CFGR1]=RCC->CFGR1;P[CFGR2]=RCC->CFGR2;P[IC1]=RCC->IC1CFGR;
 P[PLL1A]=RCC->PLL1CFGR1;P[PLL1B]=RCC->PLL1CFGR2;P[PLL1C]=RCC->PLL1CFGR3;
 P[DWT_CTRL]=DWT->CTRL;P[DEMCR]=CoreDebug->DEMCR;
 int e=OK;
 if(P[CONTROL]||P[IPSR]||P[MSPLIM]!=0x343af000||P[MSP]<=0x343af000||P[MSP]>0x343b0000)e=CONTEXT;
 if(!e&&(P[CFGR1]!=0x33330000||P[CFGR2]!=0x00100000||P[PLL1A]!=0x00404b00||
         P[PLL1B]||P[PLL1C]!=0x49000005||
         (P[IC1]&(RCC_IC1CFGR_IC1INT|RCC_IC1CFGR_IC1SEL))!=0x20000))e=CLOCK;
 if(!e&&(!(P[DWT_CTRL]&DWT_CTRL_CYCCNTENA_Msk)||!(P[DEMCR]&CoreDebug_DEMCR_TRCENA_Msk)))e=TIMER;
 if(!e)e=delay(2000);
 bus_state bus={0};
 if(!e) {e=open_bus(&bus);if(!e){P[STATE]=2;e=pad_checks();}if(!e){P[STATE]=3;e=scan();}
          P[CLEANUP]=close_bus(&bus);}
 P[DIAG_ERROR]=e;P[END]=DWT->CYCCNT;P[STATE]=(e||P[CLEANUP])?15U:4U;__DSB();
 __asm volatile(".global mdio_diag_park\nmdio_diag_park:\nb.n .\n");__builtin_unreachable();
}
/* No C prologue may run on the small early recovery stack. Interrupt masking,
 * CONTROL, DWT, clocks and debug configuration remain as supplied by the gate. */
__attribute__((naked,used,noreturn)) void mdio_diag_entry(void)
{
 __asm volatile("mrs r0,msp\n mrs r1,msplim\n mov.w r2,#0\n msr msplim,r2\n"
                "ldr r2,=0x343B0000\n msr msp,r2\n ldr r2,=0x343AF000\n"
                "msr msplim,r2\n isb\n b.w mdio_diag_main\n");
}
