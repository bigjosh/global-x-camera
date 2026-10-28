/* RAM-only LAN8742 power attribution; never include in flash/Standby builds.
 * Caller owns Ethernet pins, runs at qualified 400 MHz, and invokes restore
 * after SD cleanup on every terminal path. No camera, storage or reset access.
 * C02: PF4=MDIO (external 1.5k pullup), PG11=MDC, PHY address=0.
 * Protocol and qualification limits: README.md, RAM-only power attribution.
 */
#if RAW_POWER_PROBE < 3 || RAW_POWER_PROBE > 4 || RAW_FLASH || RAW_STANDBY
#error Ethernet power probe is RAM-only modes 3 and 4
#endif

enum {
    PHY_OK=0, PHY_CONTEXT=1, PHY_CLOCK=2, PHY_DWT=3, PHY_PULLUP=4,
    PHY_TURNAROUND=5, PHY_ID=6, PHY_BMCR=7, PHY_VERIFY=8,
    PHY_GPIO_RESTORE=9, PHY_RESTORE_TIMEOUT=10, PHY_STATE=11
};
enum {
    E_MAGIC, E_VERSION, E_MODE, E_STAGE, E_BEGIN_ERROR, E_RESTORE_ERROR,
    E_BEGIN_TICK, E_READY_TICK, E_RESTORE_TICK, E_DONE_TICK,
    E_ID1, E_ID2, E_BMCR0, E_BMCR1, E_REQUESTED, E_AFTER0, E_AFTER1,
    E_BEFORE_RESTORE, E_RESTORED0, E_RESTORED1, E_RESTORE_POLLS,
    E_BEGIN_GPIO_ERROR, E_RESTORE_GPIO_ERROR, E_WRITE_ATTEMPTS,
    E_BEGIN_RCC0, E_BEGIN_RCC1, E_BEGIN_RSTR,
    E_RESTORE_RCC0, E_RESTORE_RCC1, E_RESTORE_RSTR,
    E_PULLUP_BEGIN, E_PULLUP_RESTORE,
    E_BEGIN_F0=32, E_BEGIN_G0=38, E_BEGIN_F1=44, E_BEGIN_G1=50,
    E_RESTORE_CONFIG_MATCH=56, E_RESTORE_ID1, E_RESTORE_ID2,
    E_FLAGS, E_DWT_HZ, E_HALF_CYCLES, E_RESERVED0, E_RESERVED1
};
__attribute__((used,aligned(32))) volatile uint32_t raw_power_phy_proof[64];
static uint32_t phy_original_bmcr, phy_active;
#define EP raw_power_phy_proof
#define PHY_PD 0x0800U
#define PHY_CLOCKS (RCC_AHB4ENR_GPIOFEN | RCC_AHB4ENR_GPIOGEN)
#define PHY_RESETS (RCC_AHB4RSTR_GPIOFRST | RCC_AHB4RSTR_GPIOGRST)
#define PHY_HALF 2000U /* 5 us at the caller's qualified 400 MHz */
typedef struct { uint32_t mode,type,speed,pull,af,odr; } phy_pin;
typedef struct { phy_pin f,g; uint32_t added,configured; } phy_bus;

static int phy_delay(uint32_t cycles)
{
    const uint32_t start=DWT->CYCCNT;
    /* A disabled/stalled counter cannot leave recovery trapped here. */
    for(uint32_t n=0;n<500000U;n++) {
        if((uint32_t)(DWT->CYCCNT-start)>=cycles) return PHY_OK;
    }
    return PHY_DWT;
}
static phy_pin phy_snapshot(GPIO_TypeDef *p,uint32_t pin)
{
    phy_pin s={ (p->MODER>>(pin*2U))&3U, (p->OTYPER>>pin)&1U,
        (p->OSPEEDR>>(pin*2U))&3U, (p->PUPDR>>(pin*2U))&3U,
        (p->AFR[pin/8U]>>((pin%8U)*4U))&15U, (p->ODR>>pin)&1U };
    return s;
}
static void phy_record(uint32_t i,phy_pin s)
{ EP[i]=s.mode; EP[i+1]=s.type; EP[i+2]=s.speed;
  EP[i+3]=s.pull; EP[i+4]=s.af; EP[i+5]=s.odr; }
static int phy_equal(phy_pin a,phy_pin b)
{ return a.mode==b.mode && a.type==b.type && a.speed==b.speed &&
         a.pull==b.pull && a.af==b.af && a.odr==b.odr; }
static void phy_field(volatile uint32_t *reg,uint32_t mask,uint32_t value)
{ *reg=(*reg&~mask)|(value&mask); }
static void phy_put(GPIO_TypeDef *p,uint32_t pin,uint32_t value)
{ p->BSRR=1U<<(pin+(value?0U:16U)); }
static void phy_restore_pin(GPIO_TypeDef *p,uint32_t pin,phy_pin s)
{
    const uint32_t shift=pin*2U, a=(pin%8U)*4U;
    /* Disconnect the temporary output before restoring its latch/type/AF. */
    phy_field(&p->MODER,3U<<shift,0);
    phy_field(&p->OTYPER,1U<<pin,s.type<<pin);
    phy_field(&p->OSPEEDR,3U<<shift,s.speed<<shift);
    phy_field(&p->PUPDR,3U<<shift,s.pull<<shift);
    phy_field(&p->AFR[pin/8U],15U<<a,s.af<<a);
    phy_put(p,pin,s.odr);
    phy_field(&p->MODER,3U<<shift,s.mode<<shift);
}
static int phy_bus_open(phy_bus *b,uint32_t restoring)
{
    uint32_t idx=restoring?E_RESTORE_RCC0:E_BEGIN_RCC0;
    b->added=0; b->configured=0;
    if(__get_IPSR()!=0U || (__get_CONTROL()&1U)!=0U) return PHY_CONTEXT;
    if(!(CoreDebug->DEMCR&CoreDebug_DEMCR_TRCENA_Msk) ||
       !(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk)) return PHY_DWT;
    int e=phy_delay(PHY_HALF); if(e) return e;
    EP[idx]=RCC->AHB4ENR; EP[idx+2]=RCC->AHB4RSTR;
    if(EP[idx+2]&PHY_RESETS) return PHY_CLOCK;
    b->added=PHY_CLOCKS&~EP[idx];
    if(b->added) RCC->AHB4ENSR=b->added;
    __DSB(); __ISB();
    if((RCC->AHB4ENR&PHY_CLOCKS)!=PHY_CLOCKS) return PHY_CLOCK;
    /* GPIO reads only after clock confirmation; no GPIO reset is changed. */
    b->f=phy_snapshot(GPIOF,4); b->g=phy_snapshot(GPIOG,11);
    if(!restoring) { phy_record(E_BEGIN_F0,b->f); phy_record(E_BEGIN_G0,b->g); }
    uint32_t primask=__get_PRIMASK(); __disable_irq();
    phy_field(&GPIOF->MODER,3U<<8,0); phy_field(&GPIOG->MODER,3U<<22,0);
    phy_put(GPIOF,4,1); /* Release, never drive MDIO push-pull high. */
    phy_put(GPIOG,11,0);
    phy_field(&GPIOF->OTYPER,1U<<4,1U<<4);
    phy_field(&GPIOG->OTYPER,1U<<11,0);
    phy_field(&GPIOF->PUPDR,3U<<8,0); phy_field(&GPIOG->PUPDR,3U<<22,0);
    phy_field(&GPIOF->OSPEEDR,3U<<8,0); phy_field(&GPIOG->OSPEEDR,3U<<22,0);
    phy_field(&GPIOF->MODER,3U<<8,1U<<8);
    phy_field(&GPIOG->MODER,3U<<22,1U<<22);
    b->configured=1;
    __DSB(); __set_PRIMASK(primask);
    e=phy_delay(PHY_HALF); if(e) return e;
    EP[restoring?E_PULLUP_RESTORE:E_PULLUP_BEGIN]=(GPIOF->IDR>>4)&1U;
    if(!EP[restoring?E_PULLUP_RESTORE:E_PULLUP_BEGIN]) return PHY_PULLUP;
    /* Check the GPIO configuration was accepted before issuing MDC edges. */
    phy_pin f=phy_snapshot(GPIOF,4),g=phy_snapshot(GPIOG,11);
    if(f.mode!=1U || f.type!=1U || f.pull || f.speed || f.odr!=1U ||
       g.mode!=1U || g.type || g.pull || g.speed || g.odr) return PHY_CLOCK;
    return PHY_OK;
}
static int phy_bus_close(phy_bus *b,uint32_t restoring)
{
    int e=PHY_OK;
    /* The caller owns these clock bits for the duration; check before GPIO. */
    if(b->configured) {
        if((RCC->AHB4ENR&PHY_CLOCKS)!=PHY_CLOCKS || (RCC->AHB4RSTR&PHY_RESETS))
            e=PHY_CLOCK;
        else {
            uint32_t p=__get_PRIMASK(); __disable_irq();
            phy_put(GPIOF,4,1); phy_put(GPIOG,11,0);
            phy_restore_pin(GPIOF,4,b->f); phy_restore_pin(GPIOG,11,b->g);
            __DSB(); __set_PRIMASK(p);
            phy_pin f=phy_snapshot(GPIOF,4),g=phy_snapshot(GPIOG,11);
            uint32_t matched=phy_equal(f,b->f)&&phy_equal(g,b->g);
            if(!restoring) { phy_record(E_BEGIN_F1,f); phy_record(E_BEGIN_G1,g); }
            else EP[E_RESTORE_CONFIG_MATCH]=matched;
            if(!matched) e=PHY_GPIO_RESTORE;
        }
    }
    /* No GPIO register accesses after removing clocks we added. */
    if(b->added) RCC->AHB4ENCR=b->added;
    __DSB(); __ISB();
    uint32_t idx=restoring?E_RESTORE_RCC1:E_BEGIN_RCC1;
    EP[idx]=RCC->AHB4ENR;
    if((EP[idx]&PHY_CLOCKS)!=(EP[idx-1]&PHY_CLOCKS)) e=PHY_GPIO_RESTORE;
    return e;
}
static int phy_clock_bit(uint32_t out,uint32_t *in)
{
    /* Starts/ends MDC low. MDIO changes only while MDC is low. */
    phy_put(GPIOF,4,out);
    int e=phy_delay(PHY_HALF); if(e) return e;
    /* LAN8742 table 5-15: PHY output may change immediately AFTER rising MDC.
     * Sample the current stable bit before that edge, not after the high wait.
     * The latter skips the first bit and can mistake ID bit15 for turnaround. */
    if(in) *in=(GPIOF->IDR>>4)&1U;
    phy_put(GPIOG,11,1);
    e=phy_delay(PHY_HALF);
    phy_put(GPIOG,11,0);
    return e;
}
static int phy_send(uint32_t value,uint32_t count)
{
    while(count) { --count; int e=phy_clock_bit((value>>count)&1U,0); if(e) return e; }
    return PHY_OK;
}
static int phy_header(uint32_t read,uint32_t reg)
{
    int e=phy_send(0xFFFFFFFFU,32); if(e) return e;
    e=phy_send(1U,2); if(e) return e; /* ST=01 */
    e=phy_send(read?2U:1U,2); if(e) return e;
    e=phy_send(0U,5); if(e) return e; /* PHYAD0 strapped low */
    return phy_send(reg,5);
}
static int phy_read(uint32_t reg,uint32_t *value)
{
    uint32_t bit=1U,result=0U;
    int e=phy_header(1,reg); if(e) return e;
    e=phy_clock_bit(1,0); if(e) return e; /* turnaround Z */
    e=phy_clock_bit(1,&bit); if(e) return e; /* PHY drives turnaround 0 */
    if(bit) return PHY_TURNAROUND;
    for(uint32_t n=0;n<16;n++) {
        e=phy_clock_bit(1,&bit); if(e) return e; result=(result<<1)|bit;
    }
    e=phy_clock_bit(1,0); /* idle cycle releases PHY's final data bit */
    if(!e) *value=result;
    return e;
}
static int phy_write(uint32_t reg,uint32_t value)
{
    EP[E_WRITE_ATTEMPTS]++;
    int e=phy_header(0,reg); if(e) return e;
    e=phy_send(2U,2); if(e) return e; /* turnaround=10 */
    e=phy_send(value,16); if(e) return e;
    return phy_clock_bit(1,0);
}
static int phy_identity(uint32_t restoring)
{
    uint32_t a=0,b=0; int e=phy_read(2,&a); if(e) return e;
    e=phy_read(3,&b); if(e) return e;
    EP[restoring?E_RESTORE_ID1:E_ID1]=a;
    EP[restoring?E_RESTORE_ID2:E_ID2]=b;
    return a==0x0007U && (b&0xFFF0U)==0xC130U ? PHY_OK:PHY_ID;
}
static int power_phy_begin(uint32_t mode)
{
    if(phy_active) return PHY_STATE;
    for(uint32_t n=0;n<64;n++) EP[n]=0;
    EP[E_MAGIC]=0x31594850U; EP[E_VERSION]=1; EP[E_MODE]=mode;
    EP[E_DWT_HZ]=400000000U; EP[E_HALF_CYCLES]=PHY_HALF;
    EP[E_BEGIN_TICK]=DWT->CYCCNT; EP[E_STAGE]=1;
    if(mode!=3U && mode!=4U) return (int)(EP[E_BEGIN_ERROR]=PHY_STATE);
    phy_bus bus; uint32_t a=0,b=0; int e=phy_bus_open(&bus,0);
    if(!e) { EP[E_STAGE]=2; e=phy_identity(0); }
    if(!e) e=phy_read(0,&a);
    if(!e) e=phy_read(0,&b);
    EP[E_BMCR0]=a; EP[E_BMCR1]=b;
    /* AN enabled; speed/duplex strap defaults may vary but are ignored by AN.
     * Refuse reset/restart, loopback/isolation, preexisting PD or reserved bits. */
    if(!e && (a!=b || (a&~0x2100U)!=0x1000U)) e=PHY_BMCR;
    if(!e) {
        phy_original_bmcr=a; phy_active=1; EP[E_FLAGS]|=1U;
        EP[E_REQUESTED]=a|(mode==4U?PHY_PD:0U); EP[E_STAGE]=3;
        /* Control writes the unchanged value: same transaction count. */
        e=phy_write(0,EP[E_REQUESTED]);
    }
    if(!e) e=phy_read(0,&a);
    if(!e) e=phy_read(0,&b);
    EP[E_AFTER0]=a; EP[E_AFTER1]=b;
    if(!e && (a!=EP[E_REQUESTED] || b!=a)) e=PHY_VERIFY;
    EP[E_BEGIN_GPIO_ERROR]=phy_bus_close(&bus,0);
    if(!e && EP[E_BEGIN_GPIO_ERROR]) e=(int)EP[E_BEGIN_GPIO_ERROR];
    EP[E_BEGIN_ERROR]=(uint32_t)e; EP[E_READY_TICK]=DWT->CYCCNT;
    EP[E_STAGE]=e?0xE1U:4U;
    return e;
}
static int power_phy_restore(void)
{
    /* Safe on paths before begin. Once any BMCR write was attempted, retain
     * active until explicit readback+GPIO proof succeeds, including failures. */
    if(!phy_active) return PHY_OK;
    EP[E_RESTORE_TICK]=DWT->CYCCNT; EP[E_STAGE]=5;
    phy_bus bus; uint32_t a=0,b=0; int e=phy_bus_open(&bus,1);
    if(!e) e=phy_identity(1);
    if(!e) e=phy_read(0,&a);
    EP[E_BEFORE_RESTORE]=a;
    if(!e && a!=EP[E_REQUESTED] && a!=phy_original_bmcr) e=PHY_BMCR;
    /* Clearing PD automatically resets PHY; never claim all PHY registers
     * retained. Only original BMCR plus identities are qualified below. */
    if(!e) e=phy_write(0,phy_original_bmcr);
    if(!e) {
        for(uint32_t n=0;n<100U;n++) {
            EP[E_RESTORE_POLLS]=n+1U;
            e=phy_read(0,&a); if(e) break;
            EP[E_RESTORED0]=a;
            if(a==phy_original_bmcr) break;
            e=phy_delay(400000U); if(e) break; /* bounded 1 ms */
        }
        if(!e && a!=phy_original_bmcr) e=PHY_RESTORE_TIMEOUT;
    }
    if(!e) e=phy_read(0,&b);
    EP[E_RESTORED1]=b;
    if(!e && b!=phy_original_bmcr) e=PHY_VERIFY;
    EP[E_RESTORE_GPIO_ERROR]=phy_bus_close(&bus,1);
    if(!e && EP[E_RESTORE_GPIO_ERROR]) e=(int)EP[E_RESTORE_GPIO_ERROR];
    EP[E_RESTORE_ERROR]=(uint32_t)e; EP[E_DONE_TICK]=DWT->CYCCNT;
    if(!e) { phy_active=0; EP[E_FLAGS]|=2U; EP[E_STAGE]=6; }
    else EP[E_STAGE]=0xE2U;
    return e;
}
#undef EP
#undef PHY_PD
#undef PHY_CLOCKS
#undef PHY_RESETS
#undef PHY_HALF
