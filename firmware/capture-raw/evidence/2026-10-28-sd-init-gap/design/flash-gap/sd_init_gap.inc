/* Opt-in attribution experiment, included only in the magic capture path.
 * Card power is unchanged: this postpones protocol initialization, not its
 * supply. FRAME/STOP validation remains owned by raw_capture_poll(). The CPU
 * stays awake during the gap, so this is not a sensor-only idle measurement.
 * All flash instructions live after the independently checked late load.
 *
 * GAP1 words: magic,version,state,error,entry,frame_done,stop_done,gap_begin,
 * gap_end,target_cycles,commands_before,commands_after,frame_valid,stopped,
 * clock_hz,reserved. States 1=wait,2=gap,3=complete,15=failed. Errors:
 * 1=context/clock/ownership,2=capture fault,3=FRAME/STOP timeout,
 * 4=unexpected SD command/ownership,5=gap counter/timing failure,6=marker failure.
 */
MAGIC_LATE static int magic_sd_init_gap(void)
{
    volatile uint32_t *const v=raw_sd_init_gap_proof;
    for(uint32_t i=0;i<16U;i++) v[i]=0U;
    v[0]=0x31504147U; v[1]=1U; v[2]=1U;
    v[4]=DWT->CYCCNT; v[9]=80000000U;
    v[10]=raw_card.command_count; v[14]=SystemCoreClock;
    uint32_t error=0U;
    if(operation!=RAW_OP_CAPTURE || storage_call_depth || __get_IPSR() ||
       raw_card.initialized || raw_card.controller_owned || raw_card.timer_owned ||
       raw_card.read_sectors || raw_card.written_sectors || raw_card.command_count ||
       SystemCoreClock!=400000000U || !(DWT->CTRL&DWT_CTRL_CYCCNTENA_Msk)) {
        error=1U; goto failed;
    }
    uint32_t budget=100000000U;
    while(!raw_capture_frame_validated() || !raw_capture_sensor_stopped()) {
        raw_capture_poll();
        if(raw_capture_fault()) { error=2U; goto failed; }
        if((uint32_t)(DWT->CYCCNT-v[4])>1200000000U || !--budget) {
            error=3U; goto failed;
        }
    }
    if(raw_capture_fault()) { error=2U; goto failed; }
    v[5]=P[RP_FRAME_DONE]; v[6]=P[RP_CAMERA_STOP];
    v[12]=raw_capture_frame_validated(); v[13]=raw_capture_sensor_stopped();
    if(raw_card.command_count || raw_card.initialized || raw_card.controller_owned ||
       raw_card.timer_owned || storage_call_depth) { error=4U; goto failed; }
    v[2]=2U;
    if(!phase_gpio_emit(11U)) { error=6U; goto failed; }
    __DSB(); v[7]=DWT->CYCCNT;
    budget=100000000U;
    while((uint32_t)(DWT->CYCCNT-v[7])<v[9] && --budget) __NOP();
    v[8]=DWT->CYCCNT; v[11]=raw_card.command_count;
    if(!budget || (uint32_t)(v[8]-v[7])>=100000000U) {
        error=5U; goto failed;
    }
    if(raw_card.command_count || raw_card.initialized || raw_card.controller_owned ||
       raw_card.timer_owned || storage_call_depth) { error=4U; goto failed; }
    if(!phase_gpio_emit(12U)) { error=6U; goto failed; }
    v[2]=3U; __DSB(); return 0;
failed:
    v[11]=raw_card.command_count; v[3]=error; v[2]=15U; __DSB();
    return (int)error;
}
