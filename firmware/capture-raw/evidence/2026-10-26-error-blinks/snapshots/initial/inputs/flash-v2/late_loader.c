/* Finite, CRC-checked NOR read after receiver arm. Camera IRQs stay enabled.
 * This does not reinitialize XSPI or write NOR, and it never calls late code. */
#include "stm32n6xx.h"
#include "raw_late_crc.h"

extern uint8_t _raw_late_start[],_raw_late_end[];
static const uint32_t expected_crc=RAW_LATE_CRC32;
#define LATE_PROOF ((volatile uint32_t *)0x343F9E00U)

static uint32_t crc_word(uint32_t crc,uint32_t word)
{
    for(unsigned j=0;j<4;++j) {
        crc^=word&255U; word>>=8;
        for(unsigned b=0;b<8;++b) crc=(crc>>1)^((0U-(crc&1U))&0xEDB88320U);
    }
    return crc;
}

__attribute__((noinline,noclone,used)) int raw_late_load(void)
{
    uint32_t address=(uint32_t)_raw_late_start;
    uint32_t bytes=(uint32_t)(_raw_late_end-_raw_late_start);
    uint32_t wanted=*(volatile const uint32_t *)&expected_crc;
    volatile uint32_t *p=LATE_PROOF;
    for(unsigned i=0;i<16;++i) p[i]=0;
    p[0]=0x524C4431U; p[1]=DWT->CYCCNT; p[2]=address; p[3]=bytes;
    if(__get_PRIMASK() || (SCB->CCR&SCB_CCR_DC_Msk)) return -101;
    if(!bytes || (bytes&3U) || address<0x34300000U ||
       address+bytes>0x3430E000U) return -102;
    if((RCC->AHB5ENR&0x2020U)!=0x2020U || (RCC->AHB5RSTR&0x2020U)) return -103;
    XSPI_TypeDef *x=(XSPI_TypeDef *)XSPI1_BASE_S;
    if(x->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL)) return -104;
    if(x->CR!=0x10000001U || x->DCR1!=0x001F0000U || x->DCR2!=1U ||
       x->CCR!=0x01002101U || x->TCR!=8U || x->IR!=0x0BU ||
       *(volatile uint32_t *)XSPIM_BASE_S!=2U) return -105;
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    x->DLR=bytes-1U;
    x->AR=0x2000U+address-0x34300000U;
    __DSB();
    uint32_t began=DWT->CYCCNT,count=0,crc=0xFFFFFFFFU,polls=0;
    volatile uint32_t *output=(volatile uint32_t *)address;
    while(count<bytes) {
        uint32_t sr=x->SR;
        if(sr&XSPI_SR_TEF) return -106;
        if(((sr&XSPI_SR_FLEVEL)>>XSPI_SR_FLEVEL_Pos)>=4U) {
            uint32_t word=x->DR; *output++=word;
            crc=crc_word(crc,word); count+=4U;
        } else if((sr&XSPI_SR_TCF) && !(sr&XSPI_SR_BUSY)) return -107;
        if(++polls>10000000U || (uint32_t)(DWT->CYCCNT-began)>40000000U) return -108;
    }
    while((x->SR&XSPI_SR_BUSY) || !(x->SR&XSPI_SR_TCF)) {
        if(x->SR&XSPI_SR_TEF) return -109;
        if(++polls>10000000U || (uint32_t)(DWT->CYCCNT-began)>40000000U) return -110;
    }
    p[4]=x->SR; p[5]=count; p[6]=~crc; p[7]=wanted; p[8]=DWT->CYCCNT;
    if(x->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL|XSPI_SR_TEF)) return -111;
    x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;
    if(~crc!=wanted) return -112;
    __DSB(); SCB_InvalidateICache(); __DSB(); __ISB();
    p[9]=DWT->CYCCNT; p[15]=0x524C4F4BU; __DSB();
    return 0;
}
