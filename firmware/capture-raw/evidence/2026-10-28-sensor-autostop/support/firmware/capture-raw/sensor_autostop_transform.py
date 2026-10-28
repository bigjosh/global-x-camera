"""Opt-in context-chain auto-stop experiment; default build never calls this.

ST UM2602 Rev8 documents context repeat/next and the first-two-frame caveat.
This experiment measures one or two sensor exposures, while the receiver still
must produce exactly one complete, normally validated snapshot.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Auto-stop transform anchor changed: ' + old[:90])
    return text.replace(old, new, 1)


def sensor(text):
    anchor = '  event(109);'
    setup = '''  /* AST1: configure and independently read back the context chain before START.
   * FRAME_COUNTER is 16-bit and skips zero on rollover. A fresh sensor reset
   * must leave it zero; this experiment deliberately rejects a stale context. */
  SENSOR[24]=0x41535431U; SENSOR[25]=DWT->CYCCNT;
  TRY(40,write_value(0x048C,1U,2));
  TRY(41,write_value(0x048E,4U,2));
  uint32_t ast_repeat=0,ast_next=0,ast_count=0;
  TRY(42,read_reg(0x048C,2,&ast_repeat));
  TRY(43,read_reg(0x048E,2,&ast_next));
  TRY(44,read_reg(0x0050,2,&ast_count));
  SENSOR[26]=DWT->CYCCNT; SENSOR[27]=ast_repeat;
  SENSOR[28]=ast_next; SENSOR[29]=ast_count;
  if(ast_repeat!=1U || ast_next!=4U || ast_count!=0U) {
    SENSOR[S_PHASE]=45U; SENSOR[S_RESULT]=1U; return 1;
  }
  SENSOR[30]=1U;
'''
    return once(text, anchor, setup + anchor)


def capture(text):
    text = once(text, 'static volatile uint32_t fast_strobes;',
        'static volatile uint32_t fast_strobes;\n'
        'volatile uint32_t raw_sensor_autostop_proof[40] __attribute__((aligned(32)));\n'
        '#define AST raw_sensor_autostop_proof')
    text = once(text, '    fast_strobes++; event(50);',
        '    GPIOD->BSRR=1U; /* Diagnostic mirror of the observed STROBE edge. */\n'
        '    fast_strobes++; event(50);')
    text = once(text, '      FAST[31]=fast_strobes;',
        '      FAST[31]=fast_strobes; AST[12]=DWT->CYCCNT;')
    text = once(text, 'if(pin==GPIO_PIN_0) event(51);',
        'if(pin==GPIO_PIN_0) { GPIOD->BSRR=1U<<16; event(51); }')
    text = once(text, '  write_transactions++; write_bytes++;',
        '  if(a==0x0202U && v==1U) AST[18]++;\n'
        '  write_transactions++; write_bytes++;')
    anchor = '  uint32_t sensor_start_end=early_sensor[5];'
    text = once(text, anchor, '''  AST[0]=0x41535431U; AST[1]=1U; AST[2]=40U; AST[3]=1U;
  AST[5]=early_sensor[25]; AST[6]=early_sensor[26];
  AST[7]=early_sensor[27]; AST[8]=early_sensor[28]; AST[9]=early_sensor[29];
  AST[10]=early_sensor[4]; AST[11]=early_sensor[5]; AST[31]=400000000U;
  AST[32]=fast_strobes;
  if(early_sensor[24]!=0x41535431U || early_sensor[30]!=1U ||
     AST[7]!=1U || AST[8]!=4U || AST[9]!=0U) fail(0x90,-1);
  AST[30]=1U;
  GPIOD->BSRR=1U<<16; AST[33]=DWT->CYCCNT; /* Mirror active before PA0 IRQ. */
''' + anchor)
    anchor = 'void raw_capture_poll(void)'
    # Included here because sensor callbacks and capture state are now defined.
    text = once(text, anchor, '#include "sensor_autostop.inc"\n\n' + anchor)
    begin = text.index('  if(capture_stop_pending) {', text.index(anchor))
    end = text.index('\n#endif', begin)
    text = text[:begin] + '''  if(capture_stop_pending) { ast_poll(); return; }''' + text[end:]
    text = once(text, '  MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));',
        '  /* The context chain owns STOP. Never issue an explicit STOP here. */')
    text = once(text, '  capture_stop_started=DWT->CYCCNT; capture_stop_pending=1U;',
        '  capture_stop_started=DWT->CYCCNT; capture_stop_pending=1U;\n'
        '  AST[3]=2U; AST[13]=capture_stop_started;\n'
        '  AST[16]=FAST[31]; AST[28]=frames; AST[30]|=2U;')
    return text
