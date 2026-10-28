/* v30 diagnostic region: header32, 128 bounded raw snapshots of12 words. */
#define LATE ((volatile uint32_t *)0x343F8000U)
#define LATE_WORDS (32U+128U*12U)
#define STOP_DATA (CSI_SR1_STOPDL0F | CSI_SR1_STOPDL1F)
__attribute__((noreturn)) static void fail(uint32_t where,int32_t result);

static void late_snapshot(uint32_t id)
{
  uint32_t mask=__get_PRIMASK(); __disable_irq();
  uint32_t n=LATE[2];
  if(n<128U) {
    volatile uint32_t *r=LATE+32U+n*12U;
    r[0]=id; r[1]=DWT->CYCCNT; r[2]=HAL_GetTick();
    r[11]=RCC->APB5RSTR;
    if(!(r[11]&RCC_APB5RSTR_CSIRST) &&
       (RCC->APB5ENR&RCC_APB5ENR_CSIEN) && (RCC->DIVENR&RCC_DIVENR_IC18EN)) {
      r[3]=CSI->SR0; r[4]=CSI->SR1; r[5]=CSI->IER0; r[6]=CSI->IER1;
      r[7]=CSI->PRCR; r[8]=CSI->PCR; r[9]=CSI->CR; r[10]=CSI->LMCFGR;
      LATE[4]|=r[3]; LATE[5]|=r[4];
    } else {
      /* Reading an APB peripheral while its RCC reset is held can stall the
       * bus. Do not fabricate a measured reset state: PRCR=FFFFFFFF means
       * all CSI fields in this record were deliberately not read. */
      for(unsigned i=3;i<=10;++i) r[i]=0;
      r[7]=0xFFFFFFFFU; LATE[7]++;
    }
    LATE[2]=n+1U;
  } else LATE[3]++;
  LATE[1]=id; __DMB(); __set_PRIMASK(mask);
}

static void late_init(void)
{
  for(unsigned i=0;i<LATE_WORDS;++i) LATE[i]=0;
  LATE[0]=0x4C505231U; LATE[6]=LATE_PHY_MODE;
  volatile uint32_t *s=(volatile uint32_t *)0x343F4000U;
  for(unsigned i=0;i<8;++i) LATE[8+i]=s[24+i];
  late_snapshot(299);
}

/* Called around merger writes and the actual physical PHY reset release. */
void late_phy_hook(unsigned int id)
{
  event(id); late_snapshot(id);
  if(id==303U && ((CSI->PRCR & CSI_PRCR_PEN) ||
                 (CSI->CR & CSI_CR_CSIEN) || (CSI->SR1 & CSI_SR1_ACTCLF))) fail(0x93,-1);
}

/* All failure paths stay debug-accessible. No flash operation is performed by
 * this image. The owner must inspect this terminal state before maintenance. */
__attribute__((noreturn,noinline,used)) void late_failure_park(void)
{
  __disable_irq(); __DSB(); __ISB();
  __asm volatile(".global late_failure_idle\n"
                 "late_failure_idle:\n"
                 "b.n .\n");
  __builtin_unreachable();
}

__attribute__((noreturn)) static void late_failure_quiesce(uint32_t where,int32_t result)
{
  __disable_irq();
  LATE[16]=where; LATE[17]=(uint32_t)result;
  late_snapshot(0xF0000000U | where);
  LATE[25]=RCC->APB5ENR;
  if((LATE[25]&RCC_APB5ENR_DCMIPPEN) &&
     !(RCC->APB5RSTR&RCC_APB5RSTR_DCMIPPRST) && (RCC->DIVENR&RCC_DIVENR_IC17EN)) {
    LATE[26]=DCMIPP->P0FCTCR; LATE[27]=DCMIPP->CMSR2;
  }
  LATE[28]=RCC->APB5RSTR;
  /* Only DCMIPP: stop capture/DMA without clearing the CSI error history. */
  RCC->APB5RSTSR=RCC_APB5RSTSR_DCMIPPRSTS; __DSB();
  LATE[29]=RCC->APB5RSTR; LATE[18]=__get_PRIMASK();
  LATE[19]=((LATE[29]&RCC_APB5RSTR_DCMIPPRST) && LATE[18]==1U)?0x51554945U:0U;
  __DSB(); __ISB(); late_failure_park();
}

static void qualify_stop(void)
{
  uint32_t begun=HAL_GetTick(),stable=0,previous=~CSI->SR1;
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    uint32_t sr=CSI->SR1;
    if(sr!=previous) { late_snapshot(308); previous=sr; }
    if((sr&STOP_DATA)==STOP_DATA) {
      if(!stable) stable=DWT->CYCCNT;
      /* Observe the two data STOP flags continuously for100 nominalus.
       * This is a conservative observation guard, not a claimed PHY T_INIT. */
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        LATE[20]=sr; LATE[21]=DWT->CYCCNT;
        event(309); late_snapshot(309); return;
      }
    } else stable=0;
    if(LATE[3]) fail(0x94,-2);
    if(HAL_GetTick()-begun>50U) break;
  }
  late_snapshot(0xF0000094U); fail(0x94,-100);
}
