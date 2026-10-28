"""Reviewed-source transformations for the independent early/ForceRx pair."""

from build_raw10 import replace

FORCE_HELPERS = r'''
/* Dedicated current-run ForceRx proof:32 words at0x343F8940, immediately after
 * the separate shutdown proof. Sensor START is already complete in stage1;
 * initialization here precedes every PHY/ForceRx observation, not sensor START.
 * Each observation is {DWT cycle, PMCR, raw SR1}. No flags are cleared/masked. */
#define FORCE ((volatile uint32_t *)0x343F8940U)
static void ready_force_init(void)
{
  for(unsigned i=0;i<32U;++i) FORCE[i]=0;
  FORCE[0]=0x52465231U; /* RFR1 */
  FORCE[1]=1U; FORCE[2]=READY_GATE; FORCE[3]=1U;
  FORCE[4]=((volatile uint32_t *)0x343F4000U)[5];
  FORCE[5]=DWT->CYCCNT; FORCE[28]=40000U;
  __DMB();
}

static void ready_force_guard(void)
{
  uint32_t bus=RCC->APB5ENR, kernel=RCC->DIVENR, reset=RCC->APB5RSTR;
  const uint32_t buses=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
  const uint32_t kernels=RCC_DIVENR_IC18EN|RCC_DIVENR_IC17EN;
  const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
  /* Compact exact relevant RCC bits: bus[6,2], kernel[17:16] shifted to[9:8],
   * reset[6,2] shifted to[22,18]. A safe read has this word equal to0x344. */
  FORCE[31]=(bus&buses)|(((kernel&kernels)>>16)<<8)|((reset&resets)<<16);
  if((bus&buses)!=buses || (kernel&kernels)!=kernels || (reset&resets)) {
    FORCE[29]=(uint32_t)-1; fail(0xA6,-1);
  }
}

static void ready_force_stop_seen(uint32_t sr,uint32_t cycle);
static void ready_force_observe(unsigned at)
{
  ready_force_guard();
  FORCE[at]=DWT->CYCCNT; FORCE[at+1U]=CSI->PMCR; FORCE[at+2U]=CSI->SR1;
  /* The pre-PEN read is historical only: it cannot prove receive readiness. */
  if(at!=6U) ready_force_stop_seen(FORCE[at+2U],FORCE[at]); __DMB();
}

static void ready_force_before_stop(void)
{
  ready_force_observe(12U); FORCE[3]=4U;
  if(FORCE[13]!=(READY_GATE==5U?3U:0U)) {
    FORCE[29]=(uint32_t)-2; fail(0xA6,-2);
  }
}

static void ready_force_stop_seen(uint32_t sr,uint32_t cycle)
{
  if((sr&CSI_SR1_STOPDL0F) && !FORCE[24]) FORCE[24]=cycle;
  if((sr&CSI_SR1_STOPDL1F) && !FORCE[25]) FORCE[25]=cycle;
  if((sr&(CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F))==
        (CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F) && !FORCE[26]) FORCE[26]=cycle;
}

static void ready_force_release(void)
{
  ready_force_observe(15U); FORCE[3]=5U;
  ready_force_observe(18U);
  const uint32_t force=CSI_PMCR_FRXMDL0|CSI_PMCR_FRXMDL1;
  const uint32_t stop=CSI_SR1_STOPDL0F|CSI_SR1_STOPDL1F;
  if((FORCE[17]&stop)!=stop || (FORCE[20]&stop)!=stop) {
    FORCE[29]=(uint32_t)-7; fail(0xA6,-7);
  }
  if(FORCE[19]!=(READY_GATE==5U?force:0U)) {
    FORCE[29]=(uint32_t)-3; fail(0xA6,-3);
  }
  ready_force_guard();
  CLEAR_BIT(CSI->PMCR,force); __DSB();
  ready_force_observe(21U);
  if(FORCE[22]!=(FORCE[19]&~force)) {
    FORCE[29]=(uint32_t)-4; fail(0xA6,-4);
  }
  FORCE[3]=6U; __DMB();
}
'''


def capture(text):
    """Keep early physical lane enable; move only sensor polls after VC arming."""
    text=replace(text,'static void fast_init(void)',FORCE_HELPERS+'\nstatic void fast_init(void)')
    text=replace(text,'  FAST[6]=FAST_DATA_STREAMING; FAST[8]=1U;',
                 '  FAST[6]=READY_GATE; FAST[8]=1U;\n  ready_force_init();')
    text=replace(text,'  if(id==405U) {',
                 '  if(id==405U || id==406U) {\n'
                 '    ready_force_observe(id==405U?6U:9U);\n'
                 '    FORCE[3]=id==405U?2U:3U;\n'
                 '    if(id==405U) {\n'
                 '      ready_force_guard();\n'
                 '      WRITE_REG(CSI->PMCR,CSI_PMCR_FRXMDL0|CSI_PMCR_FRXMDL1); __DSB();\n'
                 '      FORCE[30]=CSI->PMCR;\n'
                 '      if(FORCE[30]!=3U) { FORCE[29]=(uint32_t)-5; fail(0xA6,-5); }\n'
                 '    } else if(FORCE[10]!=3U) { FORCE[29]=(uint32_t)-6; fail(0xA6,-6); }\n'
                 '  }\n  if(id==405U) {')
    text=replace(text,'    uint32_t sr=CSI->SR1;\n    if((sr&stop_data)==stop_data)',
                 '    ready_force_guard();\n'
                 '    uint32_t sr=CSI->SR1, observed=DWT->CYCCNT;\n'
                 '    ready_force_stop_seen(sr,observed);\n'
                 '    if((sr&stop_data)==stop_data)')
    text=replace(text,'        FAST[20]=sr; FAST[21]=DWT->CYCCNT;',
                 '        FORCE[27]=stable;\n        FAST[20]=sr; FAST[21]=DWT->CYCCNT;')
    first=text.index('  uint8_t state=0xFF; uint32_t ack_started=HAL_GetTick();')
    last=text.index('  fast_streaming_data_enable();',first)
    verify=text[first:last]
    text=text[:first]+text[last:]
    text=replace(text,'  fast_streaming_data_enable();\n  fast_qualify_stop();',
                 '  fast_streaming_data_enable();\n  ready_force_before_stop();\n'
                 '  fast_qualify_stop();\n  ready_force_release();')
    text=replace(text,'  arm_receiver();\n  uint32_t start=HAL_GetTick();',
                 '  arm_receiver();\n'+verify+'  uint32_t start=HAL_GetTick();')
    return text


def hal(text,treatment):
    """Only treatment retains the reset ForceRx bits across PHY enable."""
    if not treatment:return text
    return replace(text,'  /* Remove the force */\n  CLEAR_REG(csi_instance->PMCR);',
                   '  /* ForceRx treatment: retain FRXMDL0/1 until the guarded\n'
                   '   * both-lane STOP observation has remained stable100us. */\n'
                   '  /* PMCR is unchanged here; the matched control clears it. */')
