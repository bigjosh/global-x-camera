/* Bounded PHY BMCR power-down A/B/A probe. PF4 MDIO, PG11 MDC.
 * Only BMCR bit11 changed/restored after exact IDs/stable BMCR checks.
 * No MAC enable, reset, storage/camera or supply/clock-source action.
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
       A_ID1=64,A_ID2,A_BMCR0,A_BMCR1,A_REQUEST,A_AFTER0,A_AFTER1,
       A_RESTORED0,A_RESTORED1,A_POLLS,A_WRITES,A_RESTORE_WRITES,A_RESTORED,A_FAILURE_STAGE,A_RESTORE_ERROR,
       A_START=80,A_END,B_START,B_END,C_START,C_END,SETTLE_CYCLES,HOLD_CYCLES,
       A_LOOPS,B_LOOPS,C_LOOPS,A_RESTORE_ID1,A_RESTORE_ID2,MARKER_ERROR,D_SAFE,
       D0=96,D1=102 };
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
static int wait_cycles(uint32_t cycles,uint32_t *loops)
{
 uint32_t t=DWT->CYCCNT,n=0;
 while((uint32_t)(DWT->CYCCNT-t)<cycles) {
  if(++n>100000000U)return TIMER;
  __NOP();
 }
 if(loops)*loops=n;
 return OK;
}
static int marker(uint32_t id)
{
 if(id<11||id>16)return 10;
 put(GPIOD,12,1);__DSB();int e=delay(id*800U);put(GPIOD,12,0);__DSB();
 if(e)P[MARKER_ERROR]=e;
 return e;
}
static int window(uint32_t event,uint32_t start,uint32_t loops)
{
 int e=wait_cycles(40000000,0);if(e)return e;
 e=marker(event);if(e)return e;P[start]=DWT->CYCCNT;
 uint32_t n=0;e=wait_cycles(120000000,&n);P[loops]=n;P[start+1]=DWT->CYCCNT;
 int end=marker(event+1);return e?e:end;
}
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
__attribute__((used,noreturn,noinline)) void power_aba_main(uint32_t old_msp,uint32_t old_msplim)
{
 for(uint32_t n=0;n<512;n++)P[n]=0;
 P[MAGIC]=0x33414241;P[VERSION]=3;P[STATE]=1;P[BEGIN]=DWT->CYCCNT;
 P[DWT_HZ]=400000000;P[SETTLE_CYCLES]=40000000;P[HOLD_CYCLES]=120000000;
 P[CONTROL]=__get_CONTROL();P[IPSR]=__get_IPSR();P[MSP]=__get_MSP();P[MSPLIM]=__get_MSPLIM();
 P[OLD_MSP]=old_msp;P[OLD_MSPLIM]=old_msplim;
 P[CFGR1]=RCC->CFGR1;P[CFGR2]=RCC->CFGR2;P[IC1]=RCC->IC1CFGR;
 P[PLL1A]=RCC->PLL1CFGR1;P[PLL1B]=RCC->PLL1CFGR2;P[PLL1C]=RCC->PLL1CFGR3;
 P[DWT_CTRL]=DWT->CTRL;P[DEMCR]=CoreDebug->DEMCR;
 int e=OK;bus_state bus={0};pin_state d={0};
 if(P[CONTROL]||P[IPSR]||__get_PRIMASK()!=1||__get_FAULTMASK()||
    P[MSPLIM]!=0x343af000||P[MSP]<=0x343af000||P[MSP]>0x343b0000)e=CONTEXT;
 if(!e&&(P[CFGR1]!=0x33330000||P[CFGR2]!=0x00100000||P[PLL1A]!=0x00404b00||
         P[PLL1B]||P[PLL1C]!=0x49000005||P[IC1]!=0x20000))e=CLOCK;
 if(!e&&(!(P[DWT_CTRL]&1)||!(P[DEMCR]&CoreDebug_DEMCR_TRCENA_Msk)))e=TIMER;
 if(!e)e=delay(2000);
 if(!e&&(!(RCC->AHB4ENR&RCC_AHB4ENR_GPIODEN)||(RCC->AHB4RSTR&RCC_AHB4RSTR_GPIODRST)))e=CLOCK;
 if(!e) {
  d=snapshot(GPIOD,12);record(D0,d);P[D_SAFE]=1;
  field(&GPIOD->MODER,3U<<24,0);put(GPIOD,12,0);
  field(&GPIOD->OTYPER,1U<<12,0);field(&GPIOD->PUPDR,3U<<24,0);
  field(&GPIOD->OSPEEDR,3U<<24,1U<<24);field(&GPIOD->MODER,3U<<24,1U<<24);
  e=open_bus(&bus);if(!e)e=pad_checks();
  if(!e)e=identify(A_ID1);
  if(!e)e=stable_bmcr(0x3000,A_BMCR0);
  if(!e) {P[STATE]=2;e=window(11,A_START,A_LOOPS);}
  if(!e) {
   P[STATE]=3;P[A_REQUEST]=0x3800;P[A_WRITES]++;
   e=write_bmcr(0x3800);if(!e)e=stable_bmcr(0x3800,A_AFTER0);
   if(!e)e=window(13,B_START,B_LOOPS);
  }
  if(e)P[A_FAILURE_STAGE]=P[STATE];
  if(P[A_WRITES]) {
   P[A_RESTORE_ERROR]=restore_bmcr();
   if(!P[A_RESTORE_ERROR]&&!e){P[STATE]=4;e=window(15,C_START,C_LOOPS);}
  }
  P[CLEANUP]=close_bus(&bus);
  if((RCC->AHB4ENR&RCC_AHB4ENR_GPIODEN)&&!(RCC->AHB4RSTR&RCC_AHB4RSTR_GPIODRST)) {
   put(GPIOD,12,0);restore_pin(GPIOD,12,d);pin_state after=snapshot(GPIOD,12);
   record(D1,after);if(!equal(d,after))P[CLEANUP]=RESTORE;
  } else P[CLEANUP]=CLOCK;
 }
 if(P[CLOCK_LOW_FAIL]||P[CLOCK_HIGH_FAIL]){if(!e)e=PAD;}
 P[DIAG_ERROR]=e;P[END]=DWT->CYCCNT;
 P[STATE]=(e||P[CLEANUP]||P[A_RESTORE_ERROR])?15U:8U;__DSB();
 __asm volatile(".global power_aba_park\npower_aba_park:\nb.n .\n");__builtin_unreachable();
}
__attribute__((naked,used,noreturn)) void power_aba_entry(void)
{
 __asm volatile("mrs r0,msp\n mrs r1,msplim\n mov.w r2,#0\n msr msplim,r2\n"
                "ldr r2,=0x343B0000\n msr msp,r2\n ldr r2,=0x343AF000\n"
                "msr msplim,r2\n isb\n b.w power_aba_main\n");
}
