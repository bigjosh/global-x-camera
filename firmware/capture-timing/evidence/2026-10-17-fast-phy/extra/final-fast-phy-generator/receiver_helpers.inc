/* Freerun clock/data separation: bounded observational records, no flag clears.
 * Header32 +32 records of16 words at0x343F8000; prior contents beyond count
 * are deliberately not cleared and must never be decoded as current records. */
#define FAST ((volatile uint32_t *)0x343F8000U)
#define FAST_HEADER_WORDS 32U
#define FAST_MAX_RECORDS 32U
#define FAST_RECORD_WORDS 16U
static volatile uint32_t fast_strobes;
__attribute__((noreturn)) static void fail(uint32_t where,int32_t result);

static void fast_snapshot(uint32_t id)
{
  uint32_t mask=__get_PRIMASK(); __disable_irq();
  uint32_t n=FAST[2];
  if(n<FAST_MAX_RECORDS) {
    volatile uint32_t *r=FAST+FAST_HEADER_WORDS+n*FAST_RECORD_WORDS;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick();
    r[11]=RCC->APB5RSTR;
    if(!(r[11]&RCC_APB5RSTR_CSIRST) &&
       (RCC->APB5ENR&RCC_APB5ENR_CSIEN) && (RCC->DIVENR&RCC_DIVENR_IC18EN)) {
      r[3]=CSI->SR0; r[4]=CSI->SR1; r[5]=CSI->IER0; r[6]=CSI->IER1;
      r[7]=CSI->PRCR; r[8]=CSI->PCR; r[9]=CSI->CR; r[10]=CSI->LMCFGR;
      FAST[4]|=r[3]; FAST[5]|=r[4];
    } else {
      for(unsigned i=3;i<=10;++i) r[i]=0;
      r[7]=0xFFFFFFFFU; FAST[7]++;
    }
    r[12]=(RCC->AHB4ENR&RCC_AHB4ENR_GPIOAEN)?(GPIOA->IDR&1U):0xFFFFFFFFU;
    r[13]=frames; r[14]=vsyncs; r[15]=fast_strobes;
    FAST[2]=n+1U;
  } else FAST[3]++;
  FAST[1]=id; __DMB(); __set_PRIMASK(mask);
}

static void fast_init(void)
{
  for(unsigned i=0;i<FAST_HEADER_WORDS;++i) FAST[i]=0;
  FAST[0]=0x46505931U; /* FPY1 */
  FAST[6]=FAST_DATA_STREAMING; FAST[8]=1U;
  fast_snapshot(399);
}

/* Called with physical reset asserted, then immediately before/after release. */
void fast_phy_hook(unsigned int id)
{
  if(id==405U) {
    if((CSI->PRCR&CSI_PRCR_PEN) || CSI->PCR!=0x0FU) fail(0xA1,-1);
    if(FAST_DATA_STREAMING) {
      CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
      if(CSI->PCR!=0x03U) fail(0xA1,-2);
    }
  }
  event(id); fast_snapshot(id);
}

static void fast_streaming_data_enable(void)
{
  event(437); fast_snapshot(437);
  FAST[11]=DWT->CYCCNT; FAST[13]=GPIOA->IDR&1U;
  FAST[14]=frames; FAST[15]=vsyncs;
  if(!(CSI->PRCR&CSI_PRCR_PEN)) fail(0xA1,-3);
  if(FAST_DATA_STREAMING) {
    if(CSI->PCR!=0x03U) fail(0xA1,-4);
    SET_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
  }
  if(CSI->PCR!=0x0FU) fail(0xA1,-5);
  FAST[12]=DWT->CYCCNT;
  event(438); fast_snapshot(438);
  /* Freerun exposure may already be high. Do not reject it.
   * The bench must associate the captured frame with the first STROBE. */
}

static void fast_qualify_stop(void)
{
  const uint32_t stop_data=CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F;
  uint32_t begun=HAL_GetTick(),stable=0;
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    uint32_t sr=CSI->SR1;
    if((sr&stop_data)==stop_data) {
      if(!stable) stable=DWT->CYCCNT;
      /* Empirical observation gate inherited from v33, not specified T_INIT. */
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        FAST[20]=sr; FAST[21]=DWT->CYCCNT;
        event(409); fast_snapshot(409); return;
      }
    } else stable=0;
    if(HAL_GetTick()-begun>50U) break;
  }
  fail(0xA3,-100);
}

#if FAST_SHUTDOWN_DATA_OFF
/* Separate64-byte proof buffer; FAST544words ends at0x343F8880. No startup
 * work is added: initialize only after the successful HAL pipe-stop. */
#define SHUTDOWN ((volatile uint32_t *)0x343F8900U)
static void fast_shutdown_data_off(void)
{
  for(unsigned i=0;i<16U;++i) SHUTDOWN[i]=0;
  SHUTDOWN[0]=0x46534431U; /* FSD1 */
  SHUTDOWN[1]=1U; SHUTDOWN[2]=1U;
  SHUTDOWN[3]=RCC->APB5ENR; SHUTDOWN[4]=RCC->DIVENR; SHUTDOWN[5]=RCC->APB5RSTR;
  const uint32_t clocks=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
  const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
  const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
  if((SHUTDOWN[3]&clocks)!=clocks || (SHUTDOWN[4]&kernels)!=kernels || (SHUTDOWN[5]&resets)) {
    SHUTDOWN[15]=(uint32_t)-1; fail(0xA5,-1);
  }
  SHUTDOWN[2]=2U;
  /* All peripheral reads follow the RCC clock/reset guards above. */
  SHUTDOWN[6]=CSI->SR0; SHUTDOWN[7]=DCMIPP->P0FCTCR;
  SHUTDOWN[8]=DCMIPP->CMSR1; SHUTDOWN[9]=DCMIPP->P0FSCR;
  SHUTDOWN[10]=CSI->PRCR; SHUTDOWN[11]=CSI->PCR;
  /* RM0486: VC0STATEF bit17, CPTREQ bit3, P0CPTACT bit15, PIPEN bit31. */
  if((SHUTDOWN[6]&CSI_SR0_VC0STATEF) || (SHUTDOWN[7]&DCMIPP_P0FCTCR_CPTREQ) ||
     (SHUTDOWN[8]&DCMIPP_CMSR1_P0CPTACT) || (SHUTDOWN[9]&DCMIPP_P0FSCR_PIPEN)) {
    SHUTDOWN[15]=(uint32_t)-2; fail(0xA5,-2);
  }
  if(!(SHUTDOWN[10]&CSI_PRCR_PEN) || SHUTDOWN[11]!=0x0FU) {
    SHUTDOWN[15]=(uint32_t)-3; fail(0xA5,-3);
  }
  SHUTDOWN[2]=3U;
  event(442); fast_snapshot(442);
  SHUTDOWN[13]=DWT->CYCCNT;
  /* Preserve clock module, PHY power, PEN, interrupt enables and error flags. */
  CLEAR_BIT(CSI->PCR,CSI_PCR_DL0EN|CSI_PCR_DL1EN); __DSB();
  SHUTDOWN[12]=CSI->PCR; SHUTDOWN[14]=DWT->CYCCNT;
  event(443); fast_snapshot(443);
  if(SHUTDOWN[12]!=0x03U) { SHUTDOWN[15]=(uint32_t)-4; fail(0xA5,-4); }
  SHUTDOWN[2]=4U; __DMB();
}
#endif

__attribute__((noreturn,noinline,used)) void fast_failure_park(void)
{
  __disable_irq(); __DSB(); __ISB();
  __asm volatile(".global fast_failure_idle\n"
                 "fast_failure_idle:\n"
                 "b.n .\n");
  __builtin_unreachable();
}

__attribute__((noreturn)) static void fast_failure_quiesce(uint32_t where,int32_t result)
{
  __disable_irq(); FAST[16]=where; FAST[17]=(uint32_t)result;
  fast_snapshot(0xF0000000U|where);
  FAST[25]=RCC->APB5ENR;
  if((FAST[25]&RCC_APB5ENR_DCMIPPEN) &&
     !(RCC->APB5RSTR&RCC_APB5RSTR_DCMIPPRST) && (RCC->DIVENR&RCC_DIVENR_IC17EN)) {
    FAST[26]=DCMIPP->P0FCTCR; FAST[27]=DCMIPP->CMSR2;
  }
  FAST[28]=RCC->APB5RSTR;
  RCC->APB5RSTSR=RCC_APB5RSTSR_DCMIPPRSTS; __DSB();
  FAST[29]=RCC->APB5RSTR; FAST[18]=__get_PRIMASK();
  FAST[19]=((FAST[29]&RCC_APB5RSTR_DCMIPPRST) && FAST[18]==1U)?0x51554945U:0U;
  __DSB(); __ISB(); fast_failure_park();
}
