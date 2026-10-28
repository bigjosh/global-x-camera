/* AST1 is a bounded diagnostic, not a production single-shot guarantee.
 * State2 waits for autonomous FSM2; state3 has observed it; state4 proves the
 * counter/strobes are unchanged at the later completed-storage boundary.
 * Timestamps describe host observations, not exact physical transition times. */
#if RAW_FLASH
#error Sensor auto-stop is currently qualified only as a RAM-awake experiment
#endif
#define AST_LATE

AST_LATE static void ast_failed(uint32_t error)
{
  AST[4]=error; AST[3]=15U; capture_async_error=error;
  capture_stop_pending=0U; __DSB();
}

AST_LATE static void ast_poll(void)
{
  uint32_t now=DWT->CYCCNT;
  if((uint32_t)(now-capture_stop_started)>AST[31]) { ast_failed(0x91U); return; }
  if((uint32_t)(now-capture_stop_poll)<400000U) return;
  capture_stop_poll=now; AST[19]++;
  uint8_t ack=0xFFU,state=0xFFU;
  if(rd8(&sensor,0x0202,&ack)) { ast_failed(0x92U); return; }
  AST[21]=ack;
  if(rd8(&sensor,0x0028,&state)) { ast_failed(0x93U); return; }
  AST[20]=state;
  if(state!=2U) return;
  AST[14]=DWT->CYCCNT;
  if(!phase_gpio_emit(11U)) { ast_failed(0x98U); return; }
  uint16_t count=0xFFFFU;
  if(rd16(&sensor,0x0050,&count)) { ast_failed(0x94U); return; }
  AST[15]=count; AST[17]=fast_strobes; AST[29]=count-AST[9];
  if(ack || AST[18] || AST[9] || (count!=1U && count!=2U) ||
     (AST[17]!=1U && AST[17]!=2U) || (GPIOA->IDR&1U)) { ast_failed(0x95U); return; }
  sensor.ctx.is_streaming=0; capture_stop_pending=0; capture_sensor_stopped=1;
  CPROF[CP_SENSOR_STOP_DONE]=AST[14]; CPROF[CP_FLAGS]|=CP_F_SAFE_STOP;
  AST[3]=3U; AST[30]|=4U; __DSB(); raw_capture_stopped();
}

AST_LATE int raw_sensor_autostop_finish(void)
{
  AST[22]=DWT->CYCCNT;
  uint8_t state=0xFFU; uint16_t count=0xFFFFU;
  if(rd8(&sensor,0x0028,&state) || rd16(&sensor,0x0050,&count)) {
    ast_failed(0x96U); return -1;
  }
  AST[24]=state; AST[25]=count; AST[26]=fast_strobes;
  AST[27]=GPIOA->IDR&1U; AST[23]=DWT->CYCCNT;
  if(AST[3]!=3U || AST[30]!=7U || state!=2U || count!=AST[15] ||
     AST[26]!=AST[17] || AST[27] || AST[18] || frames!=1U || raw_capture_fault()) {
    ast_failed(0x97U); return -1;
  }
  AST[3]=4U; AST[30]|=8U; __DSB(); return 0;
}
#undef AST_LATE
