/* Diagnostic sensor frame2, with the original DCMIPP snapshot still armed.
 * Never resets the PHY/receiver, clears errors, or silently discards a frame. */
static void qualify_second_trigger(uint32_t scan)
{
  uint32_t began=HAL_GetTick(),start_cycles=DWT->CYCCNT,stable=0;
  unsigned rises=0,falls=0;
  event(329); late_snapshot(329);
  for(unsigned attempts=0;attempts<10000000U;++attempts) {
    uint32_t count=TRACE[2];
    if(count>=200U || LATE[3]) fail(0x94,-2);
    while(scan<count) {
      uint32_t id=EVENTS[scan*4U]; ++scan;
      if(id==50U) ++rises;
      if(id==51U) {
        if(rises!=1U || falls) fail(0x96,-3);
        falls=1; event(330); late_snapshot(330);
      }
    }
    if(frames || vsyncs || rises>1U) fail(0x96,-4);
    uint32_t sr=CSI->SR1;
    if(falls && (sr&(STOP_DATA|CSI_SR1_STOPCLF))==(STOP_DATA|CSI_SR1_STOPCLF)) {
      if(!stable) stable=DWT->CYCCNT;
      if((uint32_t)(DWT->CYCCNT-stable)>=40000U) {
        event(331); late_snapshot(331); return;
      }
    } else stable=0;
    if(HAL_GetTick()-began>500U || (uint32_t)(DWT->CYCCNT-start_cycles)>200000000U) break;
  }
  fail(0x98,falls ? -204 : -203);
}
