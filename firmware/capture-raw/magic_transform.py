"""Opt-in four-byte slot prefix and returning validation for active SD writes."""
import re

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Magic capture anchor differs: '+old[:100])
    return text.replace(old,new,1)

def transform(text):
    text=once(text,
        'uint8_t g_frame[RAW_WHOLE_IMAGE_PREERASE?RAW_SLOTS_PADDED_BYTES+32U:BYTES];',
        'uint8_t raw_frame_allocation[12U+MAGIC_SLOTS_PADDED_BYTES+32U];\n'
        '#define g_frame (raw_frame_allocation+16U)')
    text=text.replace('0x34000000U+BYTES','RAW_FRAME_ADDRESS+BYTES')
    text=text.replace('0x34000000U+offset','RAW_FRAME_ADDRESS+offset')
    text=once(text,'#if RAW_WHOLE_IMAGE_PREERASE\n  volatile uint32_t *pad_guard=(volatile uint32_t *)(0x34000000U+RAW_SLOTS_PADDED_BYTES);',
        '#if RAW_MAGIC_FORMAT\n  *(volatile uint32_t *)RAW_SLOT_BUFFER_ADDRESS=MAGIC_SLOTS_START_MAGIC;\n'
        '  volatile uint32_t *pad_guard=(volatile uint32_t *)(RAW_SLOT_BUFFER_ADDRESS+MAGIC_SLOTS_PADDED_BYTES);')
    # This helper has four guarded failure exits. It must return to the SD
    # owner rather than park with a live CMD25 if validation fails.
    start=text.index('static void fast_shutdown_data_off(void)')
    end=text.index('\n#endif',start)
    body=text[start:end].replace('static void fast_shutdown_data_off(void)','static int fast_shutdown_data_off(void)')
    body,n=re.subn(r'fail\(0xA5,(-[1-4])\);',r'return \1;',body)
    if n!=4: raise ValueError('Unexpected shutdown failure exits')
    body=once(body,'  SHUTDOWN[2]=4U; __DMB();','  SHUTDOWN[2]=4U; __DMB(); return 0;')
    text=text[:start]+body+text[end:]
    text=once(text,'  if(raw_storage_transfer_active() && !capture_finalizing) return;',
        '  /* Magic streaming uses returning errors below; the SD owner aborts\n'
        '   * and proves media idle before failure cleanup. Never park here. */')
    start=text.index('void raw_capture_poll(void)\n{')
    body=text[start:]
    body=body.replace('check(', 'MAGIC_CHECK(').replace('fail(', 'MAGIC_FAIL(')
    body=once(body,'  fast_shutdown_data_off();','  MAGIC_CHECK(0xA5,fast_shutdown_data_off());')
    body=once(body,'  CPROF[CP_FLAGS]|=CP_F_RAW10;', '''  TRACE[46]=exposure_coarse;
  early_sensor[20]=exposure_coarse;early_sensor[21]=capture_exposure_us;
  if(exposure_coarse!=RAW_EXPOSURE_COARSE) MAGIC_FAIL(0x90,-1);
#if RAW_EXPOSURE_COARSE != 1428
  uint16_t frame_length=0,margin=0;
  MAGIC_CHECK(0x91,rd16(&sensor,0x0458,&frame_length));
  MAGIC_CHECK(0x92,rd16(&sensor,0x0946,&margin));
  early_sensor[18]=frame_length;early_sensor[19]=margin;
  if(frame_length<margin+7U || exposure_coarse>frame_length-margin-7U)
    MAGIC_FAIL(0x93,-1);
#endif
  CPROF[CP_FLAGS]|=CP_F_RAW10;''')
    prefix='''#define MAGIC_FAIL(where,result) do { capture_async_error=(where); \\
  raw_producer_fault(&raw_producer,RAW_PRODUCER_ERR_CAPTURE); return; } while(0)
#define MAGIC_CHECK(where,call) do { int magic_result=(call); \\
  if(magic_result) MAGIC_FAIL(where,magic_result); } while(0)
'''
    return text[:start]+prefix+body

def sensor_exposure(text, coarse):
    """RAM-only long-exposure test; flash prefix identity is not changed."""
    if not 1<=coarse<=63000: raise ValueError('Exposure coarse range')
    old='static const uint8_t manual[12]={2,0,0x94,5,0,1,0,1,0,1,0,1}; /* 1428 */'
    text=once(text,old,
        f'static const uint8_t manual[12]={{2,0,{coarse&255},{coarse>>8},0,1,0,1,0,1,0,1}}; /* {coarse} */')
    # Leave sufficient frame period for the requested integration plus readout.
    return text.replace('write_value(0x0458,4336,2)',f'write_value(0x0458,{max(4336,coarse+2000)},2)')
