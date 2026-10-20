/* Called only after complete-frame validation and sensor STOP. No NOR writes. */
#include "stm32n6xx.h"
#include "status_leds.h"
#include "save_module_config.h"
_Static_assert(SAVE_BYTES && (SAVE_BYTES%4U)==0, "Aligned module length");
_Static_assert(SAVE_LOAD_ADDRESS==0x34320000U, "Reserved save RAM");

static uint32_t update_crc(uint32_t crc, uint32_t value)
{
    for(unsigned byte=0; byte<4; ++byte) {
        crc ^= value & 255U; value >>= 8;
        for(unsigned bit=0; bit<8; ++bit)
            crc=(crc>>1)^((0U-(crc&1U))&0xEDB88320U);
    }
    return crc;
}

int photo_save_load(void)
{
    volatile uint32_t *proof=(volatile uint32_t *)0x343F9E00U;
    /* Keep ACTIVE magic visible from the pre-event40 announcement onward. */
    for(unsigned i=1;i<16;++i) proof[i]=0;
    proof[0]=0x534C4431U; proof[1]=DWT->CYCCNT;
    __disable_irq();
    if(SCB->CCR & SCB_CCR_DC_Msk) return -101;
    if((RCC->AHB5ENR&0x2020U)!=0x2020U ||
       (RCC->AHB5RSTR&0x2020U)) return -102;
    XSPI_TypeDef *x=(XSPI_TypeDef *)XSPI1_BASE_S;
    proof[2]=x->SR; proof[3]=x->CR; proof[4]=x->CCR; proof[5]=x->IR;
    if(x->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) return -103;
    /* Prefix leaves the finite NOR read profile intact. Reject another owner. */
    if(x->CR!=0x10000001U || x->DCR1!=0x001F0000U ||
       x->DCR2!=1U || x->CCR!=0x01002101U || x->TCR!=8U ||
       x->IR!=0x0BU || *(volatile uint32_t *)XSPIM_BASE_S!=2U) return -104;
    status_led_set(STATUS_LED_NAND_WRITE); /* Existing green phase now saves to SD. */
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    x->DLR=SAVE_BYTES-1U;
    x->AR=SAVE_FLASH_OFFSET;
    __DSB();
    uint32_t started=DWT->CYCCNT, count=0, crc=0xFFFFFFFFU;
    uint32_t polls=0;
    volatile uint32_t *output=(volatile uint32_t *)SAVE_LOAD_ADDRESS;
    while(count<SAVE_BYTES) {
        uint32_t sr=x->SR;
        if(sr&XSPI_SR_TEF) return -105;
        if(((sr&XSPI_SR_FLEVEL)>>XSPI_SR_FLEVEL_Pos)>=4U) {
            uint32_t value=x->DR;
            *output++=value; crc=update_crc(crc,value); count+=4;
        } else if((sr&XSPI_SR_TCF) && !(sr&XSPI_SR_BUSY)) return -111;
        if(++polls>10000000U) return -106;
        if((uint32_t)(DWT->CYCCNT-started)>40000000U) return -106;
    }
    while((x->SR&XSPI_SR_BUSY) || !(x->SR&XSPI_SR_TCF)) {
        if(x->SR&XSPI_SR_TEF) return -107;
        if(++polls>10000000U) return -108;
        if((uint32_t)(DWT->CYCCNT-started)>40000000U) return -108;
    }
    uint32_t terminal=x->SR;
    proof[6]=terminal;
    if((terminal&(XSPI_SR_BUSY|XSPI_SR_FLEVEL|XSPI_SR_TEF)) ||
       !(terminal&XSPI_SR_TCF)) return -109;
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    proof[7]=crc^0xFFFFFFFFU; proof[8]=count; proof[9]=DWT->CYCCNT;
    if(proof[7]!=SAVE_CRC32) return -110;
    __DSB();
    SCB_DisableICache(); /* Fresh save code; also makes RAM bench reuse explicit. */
    __DSB(); __ISB();
    typedef int (*entry_fn)(uint32_t,uint32_t);
    int result=((entry_fn)(SAVE_LOAD_ADDRESS|1U))(1U,SAVE_DEFAULT_MODE);
    proof[10]=(uint32_t)result; proof[11]=DWT->CYCCNT;
    return result;
}
