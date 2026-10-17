"""Checked transformations of the frozen native-v25 source; no hardware."""
from build_raw10 import replace
from pathlib import Path

HERE=Path(__file__).resolve().parent

def transform_sensor(text):
    text=replace(text,'    SENSOR[S_MAGIC]=0x53454E31U; /* SEN1 */','''    SENSOR[S_MAGIC]=0x53454E31U; /* SEN1 */
    /* Cold-only: hold the complete CSI peripheral in reset before START.
     * PRCR.PEN=0 resets the physical receiver digital section, not just CSIEN. */
    /* Do not access CSI registers before kernel-clock setup or during reset.
     * These sentinels explicitly replace the unsafe initial CSI reads. */
    SENSOR[24]=0xFFFFFFFFU; SENSOR[25]=0xFFFFFFFFU;
    SENSOR[26]=RCC->APB5RSTR;
    RCC->APB5RSTSR=RCC_APB5RSTSR_CSIRSTS; __DSB();
    SENSOR[27]=RCC->APB5RSTR;
    if(!(SENSOR[27]&RCC_APB5RSTR_CSIRST) ||
       ((SENSOR[27]^SENSOR[26])&~RCC_APB5RSTR_CSIRST)) return failure(48,-11);
    event(300);''')
    text=replace(text,'    event(109); event(24); SENSOR[S_START_BEGIN]=DWT->CYCCNT;','''    /* UM2602 I2C follower, normal 10-bit ADC: VT_CTRL[1:0]=2, bit2=0. */
    TRY(49,write_value(0x0309,2,1)); TRY(50,write_value(0x033A,0,2));
    TRY(51,read_reg(0x0309,1,&value)); SENSOR[28]=value;
    if(value!=2U) return failure(51,-12);
    TRY(52,read_reg(0x033A,2,&value)); SENSOR[29]=value;
    if(value) return failure(52,-13);
    TRY(53,read_reg(0x0956,1,&value)); SENSOR[30]=value;
    if(value!=0x1CU) return failure(53,-14); /* Keep default continuous clock. */
    SENSOR[31]=RCC->APB5RSTR;
    if(!(SENSOR[31]&RCC_APB5RSTR_CSIRST)) return failure(54,-15);
    event(109); event(24); SENSOR[S_START_BEGIN]=DWT->CYCCNT;''')
    return text

def transform_capture(text):
    text=replace(text,'__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)',
        (HERE/'receiver_helpers.inc').read_text()+'\n__attribute__((noreturn)) static void fail(uint32_t where, int32_t result)')
    text=replace(text,'  event(0x80000000U | where);\n  for (;;) __NOP();',
        '  event(0x80000000U | where);\n  late_failure_quiesce(where,result);')
    text=replace(text,'  TRACE[3] = (uint32_t)result;',
        '  __disable_irq(); /* Keep terminal TRACE proof immutable before quiescence. */\n  TRACE[3] = (uint32_t)result;')
    text=replace(text,'void CSI_IRQHandler(void) { irq_sr0=CSI->SR0;',
        'void CSI_IRQHandler(void) { late_snapshot(320); irq_sr0=CSI->SR0;')
    text=replace(text,'  __HAL_RCC_CSI_FORCE_RESET(); __HAL_RCC_CSI_RELEASE_RESET();',
        '''  late_snapshot(301);
  if(!(RCC->APB5RSTR & RCC_APB5RSTR_CSIRST)) fail(0x91,-1);
  __HAL_RCC_CSI_RELEASE_RESET(); __DSB();
  late_snapshot(302);
  if((RCC->APB5RSTR & RCC_APB5RSTR_CSIRST) || (CSI->PRCR & CSI_PRCR_PEN)) fail(0x92,-1);''')
    text=replace(text,'  event(21);\n  check(22, HAL_DCMIPP_CSI_PIPE_Start',
        '  event(21);\n}\n\nstatic void arm_receiver(void)\n{\n  check(22, HAL_DCMIPP_CSI_PIPE_Start')
    text=replace(text,'int main(void)\n{\n  event(2);',
        'int main(void)\n{\n  late_init();\n  event(2);')
    start=text.index('  /* Receiver-only handoff.')
    end=text.index('  uint32_t start=HAL_GetTick();',start)
    text=text[:start]+(HERE/'main_sequence.inc').read_text()+text[end:]
    text=replace(text,'  event(31);\n  TRACE[44]=CSI->SR0;',
        '''  event(31); late_snapshot(313);
  /* I2C FSYNC acknowledgement follows transmission, never wait before frame. */
  ack_started=HAL_GetTick();
  do { check(0x98,rd8(&sensor,0x0202,&state));
       if(HAL_GetTick()-ack_started>500U) fail(0x98,-100); } while(state);
  late_snapshot(314);
  TRACE[44]=CSI->SR0;''')
    text=replace(text,'  check(32, HAL_DCMIPP_CSI_PIPE_Stop',
        '  late_snapshot(315);\n  check(32, HAL_DCMIPP_CSI_PIPE_Stop')
    text=replace(text,'  check(33, VD6G_Stop(&sensor));',
        '  check(33, VD6G_Stop(&sensor));\n  late_snapshot(316);')
    text=replace(text,'  event(40);','  late_snapshot(317); if(LATE[3]) fail(0x94,-2); LATE[1]=40;\n  event(40);')
    return text
