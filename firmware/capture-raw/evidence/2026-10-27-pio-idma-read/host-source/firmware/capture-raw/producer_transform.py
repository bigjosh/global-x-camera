"""Add the opt-in LINE producer to an already transformed capture source."""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("LINE transform anchor count differs: " + old[:100])
    return text.replace(old, new, 1)


def transform(text):
    text = once(text, '#include "runtime.h"', '#include "runtime.h"\n#include "producer.h"')
    # Keep the historical failure symbol for provenance; actual failures use the
    # storage owner after its SD call returns, rather than parking in a callback.
    text = once(text, '''  __disable_irq();
  status_led_proof_phase(STATUS_LED_ERROR,LED_P_ERROR_CYCLE);''', '''  status_led_proof_phase(STATUS_LED_ERROR,LED_P_ERROR_CYCLE);''')
    text = once(text, '  fast_failure_quiesce(where,result);',
                '  raw_capture_fail(where,result);')
    text = once(text, '    frames++; raw_capture_frame_event(); event(30);', '''    frames++;
#if RAW_LINE_STREAM
    raw_producer_frame(&raw_producer,DWT->CYCCNT);
#endif
    raw_capture_frame_event(); event(30);''')
    text = once(text, '  arm_receiver();\n  raw_capture_armed();', '''#if RAW_LINE_STREAM
  /* HAL enable does not clear stale LINE status. Before arming, discard only
   * this flag so event1 cannot consume the holdback without64 captured lines. */
  DCMIPP->CMFCR=DCMIPP_CMFCR_CP0LINEF; __DSB();
  check(0x8E,HAL_DCMIPP_PIPE_EnableLineEvent(&hcam,DCMIPP_PIPE0,DCMIPP_MULTILINE_64_LINES));
#endif
  arm_receiver();
  raw_capture_armed();''')
    text = once(text, '  errors++; TRACE[4] |= h->ErrorCode; event(id);', '''#if RAW_LINE_STREAM
  raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE);
#endif
  errors++; TRACE[4] |= h->ErrorCode; event(id);''')
    callback = '''#if RAW_LINE_SNAPSHOTS
static void raw_line_snapshot(uint32_t index,uint32_t offset,uint32_t bytes)
{
  /* Copy the newest published tail immediately, before publication. A later
   * slow SD read can hide an early-memory-visibility error; this snapshot cannot.
   * Diagnostic RAM mode only. The source has no dirty CPU cache alias. */
  volatile const uint32_t *src=(volatile const uint32_t *)(0x34000000U+offset);
  volatile uint32_t *dst=(volatile uint32_t *)(RAW_PRODUCER_SNAPSHOT_ADDRESS+index*512U);
  for(uint32_t i=0;i<bytes/4U;i++) dst[i]=src[i];
  __DMB();
}
#endif
void HAL_DCMIPP_PIPE_LineEventCallback(DCMIPP_HandleTypeDef *h,uint32_t pipe)
{
  (void)h;
#if RAW_LINE_STREAM
  if(pipe==0U) {
    if(errors || hcam.ErrorCode) raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE);
    raw_producer_line(&raw_producer,DWT->CYCCNT,
#if RAW_LINE_SNAPSHOTS
      raw_line_snapshot
#else
      0
#endif
    );
  }
#else
  (void)pipe;
#endif
}
'''
    text = once(text, 'void HAL_DCMIPP_PIPE_FrameEventCallback(', callback + '\nvoid HAL_DCMIPP_PIPE_FrameEventCallback(')
    text = once(text, 'uint32_t raw_capture_available(void) { return capture_ready?BYTES:0U; }', '''uint32_t raw_capture_available(void)
{
#if RAW_LINE_STREAM
  return raw_producer_available(&raw_producer);
#else
  return capture_ready?BYTES:0U;
#endif
}
uint32_t raw_capture_frame_validated(void) { return capture_ready; }''')
    text = once(text, 'return errors|hcam.ErrorCode|capture_async_error;',
                'return errors|hcam.ErrorCode|capture_async_error|raw_producer.error;')
    text = once(text, 'void raw_capture_poll(void)\n{', '''void raw_capture_poll(void)
{
  /* The full post-frame checks can terminate on failure. They must never run
   * while SD owns an active command/DMA buffer. The already-started async STOP
   * poll below has deferred errors and is safe after capture_finalizing. */
  if(raw_storage_transfer_active() && !capture_finalizing) return;
  if(capture_async_error || raw_producer.error) return;''')
    text = once(text, '  capture_ready=1U; __DSB();', '''#if RAW_LINE_STREAM
  if(raw_producer_complete(&raw_producer,raw10[1],frames,
      errors|hcam.ErrorCode,raw10[7],DWT->CYCCNT)) { capture_async_error=0x8FU;return; }
#endif
  capture_ready=1U; __DSB();''')
    return text
