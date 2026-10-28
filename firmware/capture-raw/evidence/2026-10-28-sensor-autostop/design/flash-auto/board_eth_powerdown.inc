/* NUCLEO-N657X0-Q C02: leave the unused LAN8742 in BMCR power-down.
 * PF4=MDIO (external 1.5k pullup), PG11=MDC, PHY address 0. The qualified
 * late-load caller owns these pins and runs at 400 MHz. No MAC/reset/rail,
 * camera or storage access. Warnings are retained; capture always continues.
 * Clearing BMCR power-down resets the PHY: this helper deliberately never
 * restores BMCR, including after an uncertain write/readback outcome.
 */
#if !RAW_BOARD_ETH_POWERDOWN
#error Include board_eth_powerdown.inc only for the board feature
#endif
#if RAW_FLASH
#define BOARD_ETH_LATE __attribute__((section(".raw_late_text"),noinline,noclone))
#else
#define BOARD_ETH_LATE
#endif

enum {
    BETH_OK=0, BETH_CONTEXT=1, BETH_CLOCK=2, BETH_DWT=3, BETH_PULLUP=4,
    BETH_TURNAROUND=5, BETH_ID=6, BETH_BMCR=7, BETH_VERIFY=8,
    BETH_GPIO_RESTORE=9
};
enum {
    BE_MAGIC, BE_VERSION, BE_STAGE, BE_ERROR, BE_CLEANUP_ERROR, BE_FLAGS,
    BE_START_TICK, BE_END_TICK, BE_ID1, BE_ID2, BE_BMCR0, BE_BMCR1,
    BE_REQUESTED, BE_AFTER0, BE_AFTER1, BE_WRITE_ATTEMPTS, BE_READ_ATTEMPTS,
    BE_RCC0, BE_RCC1, BE_RSTR, BE_ADDED_CLOCKS, BE_PULLUP,
    BE_CFGR1, BE_CFGR2, BE_IC1, BE_PLL1A, BE_PLL1B, BE_PLL1C,
    BE_DWT_HZ, BE_HALF_CYCLES, BE_PRIMASK, BE_RESERVED0,
    BE_F0=32, BE_G0=38, BE_F1=44, BE_G1=50,
    BE_IPSR=56, BE_CONTROL, BE_DWT_CTRL, BE_DEMCR, BE_CCR,
    BE_RESERVED1, BE_RESERVED2, BE_RESERVED3
};
enum {
    BF_ID=1U, BF_CONFIG=2U, BF_ALREADY_PD=4U, BF_WRITE_ATTEMPT=8U,
    BF_PD_VERIFIED=16U, BF_GPIO_RESTORED=32U, BF_RCC_RESTORED=64U,
    BF_OUTCOME_UNKNOWN=128U
};
__attribute__((used,aligned(32))) volatile uint32_t raw_board_eth_proof[64];
static uint32_t board_eth_attempted;
#define BEP raw_board_eth_proof
#define BETH_PD 0x0800U
#define BETH_CLOCKS (RCC_AHB4ENR_GPIOFEN | RCC_AHB4ENR_GPIOGEN)
#define BETH_RESETS (RCC_AHB4RSTR_GPIOFRST | RCC_AHB4RSTR_GPIOGRST)
#define BETH_HALF 2000U /* 5 us at qualified 400 MHz */
typedef struct { uint32_t mode,type,speed,pull,af,odr; } beth_pin;
typedef struct { beth_pin f,g; uint32_t added,configured,clock_snapshot; } beth_bus;

BOARD_ETH_LATE static int beth_delay(uint32_t cycles)
{
    uint32_t start=DWT->CYCCNT;
    for(uint32_t n=0;n<500000U;n++)
        if((uint32_t)(DWT->CYCCNT-start)>=cycles) return BETH_OK;
    return BETH_DWT; /* Bounded even with a stalled counter. */
}
BOARD_ETH_LATE static beth_pin beth_snapshot(GPIO_TypeDef *p,uint32_t pin)
{
    beth_pin s={ (p->MODER>>(pin*2U))&3U, (p->OTYPER>>pin)&1U,
        (p->OSPEEDR>>(pin*2U))&3U, (p->PUPDR>>(pin*2U))&3U,
        (p->AFR[pin/8U]>>((pin%8U)*4U))&15U, (p->ODR>>pin)&1U };
    return s;
}
BOARD_ETH_LATE static void beth_record(uint32_t i,beth_pin s)
{ BEP[i]=s.mode; BEP[i+1]=s.type; BEP[i+2]=s.speed;
  BEP[i+3]=s.pull; BEP[i+4]=s.af; BEP[i+5]=s.odr; }
BOARD_ETH_LATE static int beth_equal(beth_pin a,beth_pin b)
{ return a.mode==b.mode && a.type==b.type && a.speed==b.speed &&
         a.pull==b.pull && a.af==b.af && a.odr==b.odr; }
BOARD_ETH_LATE static void beth_field(volatile uint32_t *r,uint32_t mask,uint32_t value)
{ *r=(*r&~mask)|(value&mask); }
BOARD_ETH_LATE static void beth_put(GPIO_TypeDef *p,uint32_t pin,uint32_t value)
{ p->BSRR=1U<<(pin+(value?0U:16U)); }
BOARD_ETH_LATE static void beth_restore_pin(GPIO_TypeDef *p,uint32_t pin,beth_pin s)
{
    uint32_t shift=pin*2U,a=(pin%8U)*4U;
    beth_field(&p->MODER,3U<<shift,0);
    beth_field(&p->OTYPER,1U<<pin,s.type<<pin);
    beth_field(&p->OSPEEDR,3U<<shift,s.speed<<shift);
    beth_field(&p->PUPDR,3U<<shift,s.pull<<shift);
    beth_field(&p->AFR[pin/8U],15U<<a,s.af<<a);
    beth_put(p,pin,s.odr);
    beth_field(&p->MODER,3U<<shift,s.mode<<shift);
}
BOARD_ETH_LATE static int beth_clock_guard(void)
{
    BEP[BE_IPSR]=__get_IPSR(); BEP[BE_CONTROL]=__get_CONTROL();
    BEP[BE_PRIMASK]=__get_PRIMASK(); BEP[BE_CCR]=SCB->CCR;
    if(BEP[BE_IPSR] || (BEP[BE_CONTROL]&1U) || (BEP[BE_CCR]&SCB_CCR_DC_Msk))
        return BETH_CONTEXT;
    BEP[BE_CFGR1]=RCC->CFGR1; BEP[BE_CFGR2]=RCC->CFGR2;
    BEP[BE_IC1]=RCC->IC1CFGR; BEP[BE_PLL1A]=RCC->PLL1CFGR1;
    BEP[BE_PLL1B]=RCC->PLL1CFGR2; BEP[BE_PLL1C]=RCC->PLL1CFGR3;
    if(BEP[BE_CFGR1]!=0x33330000U || BEP[BE_CFGR2]!=0x00100000U ||
       BEP[BE_IC1]!=0x00020000U || BEP[BE_PLL1A]!=0x00404B00U ||
       BEP[BE_PLL1B]!=0U || BEP[BE_PLL1C]!=0x49000005U) return BETH_CLOCK;
    BEP[BE_DWT_CTRL]=DWT->CTRL; BEP[BE_DEMCR]=CoreDebug->DEMCR;
    if(!(BEP[BE_DEMCR]&CoreDebug_DEMCR_TRCENA_Msk) ||
       !(BEP[BE_DWT_CTRL]&DWT_CTRL_CYCCNTENA_Msk)) return BETH_DWT;
    return beth_delay(BETH_HALF);
}
BOARD_ETH_LATE static int beth_bus_open(beth_bus *b)
{
    b->added=0; b->configured=0; b->clock_snapshot=0;
    int e=beth_clock_guard(); if(e) return e;
    BEP[BE_RCC0]=RCC->AHB4ENR; BEP[BE_RSTR]=RCC->AHB4RSTR;
    b->clock_snapshot=1;
    if(BEP[BE_RSTR]&BETH_RESETS) return BETH_CLOCK;
    b->added=BETH_CLOCKS&~BEP[BE_RCC0]; BEP[BE_ADDED_CLOCKS]=b->added;
    if(b->added) RCC->AHB4ENSR=b->added;
    __DSB(); __ISB();
    if((RCC->AHB4ENR&BETH_CLOCKS)!=BETH_CLOCKS) return BETH_CLOCK;
    /* Never access a GPIO before its clock/reset guard. */
    b->f=beth_snapshot(GPIOF,4); b->g=beth_snapshot(GPIOG,11);
    beth_record(BE_F0,b->f); beth_record(BE_G0,b->g);
    uint32_t p=__get_PRIMASK(); __disable_irq();
    beth_field(&GPIOF->MODER,3U<<8,0); beth_field(&GPIOG->MODER,3U<<22,0);
    beth_put(GPIOF,4,1); beth_put(GPIOG,11,0);
    beth_field(&GPIOF->OTYPER,1U<<4,1U<<4);
    beth_field(&GPIOG->OTYPER,1U<<11,0);
    beth_field(&GPIOF->PUPDR,3U<<8,0); beth_field(&GPIOG->PUPDR,3U<<22,0);
    beth_field(&GPIOF->OSPEEDR,3U<<8,0); beth_field(&GPIOG->OSPEEDR,3U<<22,0);
    beth_field(&GPIOF->MODER,3U<<8,1U<<8);
    beth_field(&GPIOG->MODER,3U<<22,1U<<22);
    b->configured=1;
    __DSB(); __set_PRIMASK(p);
    e=beth_delay(BETH_HALF); if(e) return e;
    BEP[BE_PULLUP]=(GPIOF->IDR>>4)&1U;
    if(!BEP[BE_PULLUP]) return BETH_PULLUP;
    beth_pin f=beth_snapshot(GPIOF,4),g=beth_snapshot(GPIOG,11);
    if(f.mode!=1U || f.type!=1U || f.pull || f.speed || f.odr!=1U ||
       g.mode!=1U || g.type || g.pull || g.speed || g.odr) return BETH_CLOCK;
    return BETH_OK;
}
BOARD_ETH_LATE static int beth_bus_close(beth_bus *b)
{
    int e=BETH_OK;
    if(b->configured) {
        if((RCC->AHB4ENR&BETH_CLOCKS)!=BETH_CLOCKS || (RCC->AHB4RSTR&BETH_RESETS))
            e=BETH_CLOCK;
        else {
            uint32_t p=__get_PRIMASK(); __disable_irq();
            beth_put(GPIOF,4,1); beth_put(GPIOG,11,0);
            beth_restore_pin(GPIOF,4,b->f); beth_restore_pin(GPIOG,11,b->g);
            __DSB(); __set_PRIMASK(p);
            beth_pin f=beth_snapshot(GPIOF,4),g=beth_snapshot(GPIOG,11);
            beth_record(BE_F1,f); beth_record(BE_G1,g);
            if(beth_equal(f,b->f)&&beth_equal(g,b->g)) BEP[BE_FLAGS]|=BF_GPIO_RESTORED;
            else e=BETH_GPIO_RESTORE;
        }
    }
    if(b->added) RCC->AHB4ENCR=b->added;
    __DSB(); __ISB(); /* No GPIO accesses after removing owned clock bits. */
    if(b->clock_snapshot) {
        BEP[BE_RCC1]=RCC->AHB4ENR;
        if((BEP[BE_RCC1]&BETH_CLOCKS)==(BEP[BE_RCC0]&BETH_CLOCKS))
            BEP[BE_FLAGS]|=BF_RCC_RESTORED;
        else e=BETH_GPIO_RESTORE;
    }
    return e;
}
BOARD_ETH_LATE static int beth_clock_bit(uint32_t out,uint32_t *in)
{
    beth_put(GPIOF,4,out);
    int e=beth_delay(BETH_HALF); if(e) return e;
    /* LAN8742 table 5-15 permits immediate output advance AFTER rising MDC.
     * Sample the stable current bit before that edge; late sampling shifts it. */
    if(in) *in=(GPIOF->IDR>>4)&1U;
    beth_put(GPIOG,11,1);
    e=beth_delay(BETH_HALF);
    beth_put(GPIOG,11,0);
    return e;
}
BOARD_ETH_LATE static int beth_send(uint32_t value,uint32_t count)
{
    while(count) { --count; int e=beth_clock_bit((value>>count)&1U,0); if(e) return e; }
    return BETH_OK;
}
BOARD_ETH_LATE static int beth_header(uint32_t read,uint32_t reg)
{
    int e=beth_send(0xFFFFFFFFU,32); if(e) return e;
    e=beth_send(1U,2); if(e) return e;
    e=beth_send(read?2U:1U,2); if(e) return e;
    e=beth_send(0U,5); if(e) return e;
    return beth_send(reg,5);
}
BOARD_ETH_LATE static int beth_read(uint32_t reg,uint32_t *value)
{
    uint32_t bit=1U,ta=1U,result=0U;
    BEP[BE_READ_ATTEMPTS]++;
    int e=beth_header(1,reg); if(e) return e;
    e=beth_clock_bit(1,0); if(e) return e;
    e=beth_clock_bit(1,&ta); if(e) return e;
    /* Finish the frame even if no PHY acknowledges, leaving a clean boundary. */
    for(uint32_t n=0;n<16;n++) {
        e=beth_clock_bit(1,&bit); if(e) return e; result=(result<<1)|bit;
    }
    e=beth_clock_bit(1,0); if(e) return e;
    if(ta) return BETH_TURNAROUND;
    *value=result;
    return BETH_OK;
}
BOARD_ETH_LATE static int beth_write_bmcr(uint32_t value)
{
    BEP[BE_WRITE_ATTEMPTS]++;
    BEP[BE_FLAGS]|=BF_WRITE_ATTEMPT|BF_OUTCOME_UNKNOWN;
    int e=beth_header(0,0); if(e) return e;
    e=beth_send(2U,2); if(e) return e;
    e=beth_send(value,16); if(e) return e;
    return beth_clock_bit(1,0);
}
BOARD_ETH_LATE static void board_eth_powerdown_once(void)
{
    if(board_eth_attempted) return; /* Preserve the first attempt and its warning. */
    board_eth_attempted=1;
    for(uint32_t n=0;n<64;n++) BEP[n]=0;
    BEP[BE_MAGIC]=0x31485445U; BEP[BE_VERSION]=1; BEP[BE_STAGE]=1;
    BEP[BE_START_TICK]=DWT->CYCCNT; BEP[BE_DWT_HZ]=400000000U;
    BEP[BE_HALF_CYCLES]=BETH_HALF;
    beth_bus bus; uint32_t a=0,b=0; int e=beth_bus_open(&bus);
    if(!e) { BEP[BE_STAGE]=2; e=beth_read(2,&a); BEP[BE_ID1]=a; }
    if(!e) { e=beth_read(3,&b); BEP[BE_ID2]=b; }
    if(!e && (a!=0x0007U || (b&0xFFF0U)!=0xC130U)) e=BETH_ID;
    if(!e) { BEP[BE_FLAGS]|=BF_ID; BEP[BE_STAGE]=3;
        e=beth_read(0,&a); BEP[BE_BMCR0]=a; }
    if(!e) { e=beth_read(0,&b); BEP[BE_BMCR1]=b; }
    /* AN enabled; only speed/duplex strap bits and optional stable PD accepted.
     * Reject reset/restart, loopback/isolation and all reserved configurations. */
    if(!e && (a!=b || (a&~(0x2100U|BETH_PD))!=0x1000U)) e=BETH_BMCR;
    if(!e) {
        BEP[BE_FLAGS]|=BF_CONFIG; BEP[BE_STAGE]=4;
        BEP[BE_REQUESTED]=a|BETH_PD;
        if(a&BETH_PD) BEP[BE_FLAGS]|=BF_ALREADY_PD|BF_PD_VERIFIED;
        else {
            BEP[BE_STAGE]=5; e=beth_write_bmcr(BEP[BE_REQUESTED]);
            if(!e) { e=beth_read(0,&a); BEP[BE_AFTER0]=a; }
            if(!e) { e=beth_read(0,&b); BEP[BE_AFTER1]=b; }
            if(!e && (a!=BEP[BE_REQUESTED] || b!=a)) e=BETH_VERIFY;
            if(!e) { BEP[BE_FLAGS]|=BF_PD_VERIFIED;
                BEP[BE_FLAGS]&=~BF_OUTCOME_UNKNOWN; }
        }
    }
    BEP[BE_CLEANUP_ERROR]=(uint32_t)beth_bus_close(&bus);
    BEP[BE_ERROR]=(uint32_t)e;
    BEP[BE_END_TICK]=DWT->CYCCNT;
    BEP[BE_STAGE]=(e||BEP[BE_CLEANUP_ERROR])?0xE1U:6U;
    __DSB(); /* No failure routes to camera/storage error signaling. */
}
#undef BEP
#undef BETH_PD
#undef BETH_CLOCKS
#undef BETH_RESETS
#undef BETH_HALF
#undef BOARD_ETH_LATE
