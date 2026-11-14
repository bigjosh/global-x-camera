/* Called only after the CRC-checked late receiver load. */
#define KNOB_LATE __attribute__((section(".raw_late_text"),noinline,noclone))
static uint32_t knob_metadata_frozen;

KNOB_LATE static int knob_record_valid(void)
{
  const volatile capture_controls_t *p=CAPTURE_CONTROLS;
  if(!capture_controls_valid(p) ||
     (p->state!=CC_SENSOR_CONFIGURED && p->state!=CC_APPLIED_VERIFIED) ||
     p->flags!=(CC_REQUIRED_FLAGS|CC_F_SENSOR_CONFIGURED|
       (p->state==CC_APPLIED_VERIFIED?CC_F_APPLIED_VALID:0U)) || p->vt_hz!=160800000U ||
     p->requested_us<1000U || p->requested_us>500000U ||
     p->line_length!=1280U ||
     p->manual[0]!=2U || p->margin>1993U || p->reserved0 || p->reserved1)
    return 0;
  const uint32_t coarse=(uint32_t)p->manual[2]|((uint32_t)p->manual[3]<<8);
  const uint32_t expected=(uint32_t)(((uint64_t)p->requested_us*160800000U+
      (uint64_t)p->line_length*1000000U-1U)/((uint64_t)p->line_length*1000000U));
  const uint32_t frame=coarse+2000U<4336U?4336U:coarse+2000U;
  if(coarse!=expected || coarse<21U || frame>65535U || p->frame_length!=frame ||
     coarse>frame-p->margin-7U) return 0;
  uint32_t gain=p->manual[1];
  if(!((p->asa==100U&&gain==0U)||(p->asa==200U&&gain==16U)||
       (p->asa==400U&&gain==24U)||(p->asa==800U&&gain==28U))) return 0;
  for(unsigned i=4;i<12;i+=2) if(p->manual[i] || p->manual[i+1]!=1U) return 0;
  if(p->state==CC_APPLIED_VERIFIED &&
     (!(p->flags&CC_F_APPLIED_VALID)||p->applied_coarse!=coarse||
      p->applied_gain!=gain||p->applied_digital!=256U)) return 0;
  return 1;
}

KNOB_LATE static int knob_verify_applied(uint32_t line,uint32_t coarse)
{
  volatile capture_controls_t *p=CAPTURE_CONTROLS;
  if(!knob_record_valid() || line!=p->line_length ||
     coarse!=((uint32_t)p->manual[2]|((uint32_t)p->manual[3]<<8))) return -1;
  uint16_t frame=0,margin=0,digital=0; uint8_t gain=0;
  int result=rd16(&sensor,0x0458,&frame);
  if(!result) result=rd16(&sensor,0x0946,&margin);
  /* ST's applied exposure cluster: coarse0064, analog0068, digital006A. */
  if(!result) result=rd8(&sensor,0x0068,&gain);
  if(!result) result=rd16(&sensor,0x006A,&digital);
  if(result) return result;
  if(frame!=p->frame_length || margin!=p->margin || frame<margin+7U ||
     coarse>frame-margin-7U || gain!=p->manual[1] || digital!=256U) return -2;
  volatile uint32_t *early_sensor=(volatile uint32_t *)0x343F4000U;
  early_sensor[18]=frame;early_sensor[19]=margin;
  p->applied_coarse=coarse;p->applied_gain=gain;p->applied_digital=digital;
  p->flags|=CC_F_APPLIED_VALID;p->state=CC_APPLIED_VERIFIED;
  p->crc32=capture_controls_crc(p);__DSB();
  return 0;
}

KNOB_LATE int raw_controls_metadata_freeze(void *destination)
{
  if(knob_metadata_frozen) return 0;
  if(!knob_record_valid()) return -1;
  volatile uint32_t *out=(volatile uint32_t *)destination;
  const volatile uint32_t *in=(const volatile uint32_t *)CAPTURE_CONTROLS;
  for(unsigned i=0;i<sizeof(capture_controls_t)/4U;i++) out[i]=in[i];
  for(unsigned i=sizeof(capture_controls_t)/4U;i<MAGIC_SLOTS_METADATA_BYTES/4U;i++) out[i]=0;
  /* Once the first sector is offered, its snapshot is immutable even if the
   * post-FRAME RAM record gains applied verification during later writes. */
  __DSB();knob_metadata_frozen=1U;return 0;
}
#undef KNOB_LATE
