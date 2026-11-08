#include "stm32n657xx.h"
/* ROM-established single-line NOR, same finite reads as the capture loader. */
static int boot_read(uint32_t offset,uint8_t *to,uint32_t n,uint32_t expected)
{
 XSPI_TypeDef *x=XSPI1;uint32_t start=DWT->CYCCNT,count=0,crc=~0U;
 if(SCB->CCR&(SCB_CCR_IC_Msk|SCB_CCR_DC_Msk))return 0;
 if(x->CR!=0x10000001U||x->CCR!=0x01002101U||x->IR!=0xBU||x->SR&(XSPI_SR_BUSY|XSPI_SR_FLEVEL))return 0;
 x->FCR=XSPI_FCR_CTCF|XSPI_FCR_CTEF;x->DLR=n-1;x->AR=offset;
 while(count<n){
  uint32_t sr=x->SR;
  if(sr&XSPI_SR_TEF)return 0;
  if(sr&XSPI_SR_FLEVEL){uint8_t b=*(volatile uint8_t *)&x->DR;to[count++]=b;crc^=b;for(unsigned i=0;i<8;i++)crc=(crc>>1)^(0xEDB88320U&(0U-(crc&1U)));}
  if((uint32_t)(DWT->CYCCNT-start)>40000000U)return 0;
 }
 while(!(x->SR&XSPI_SR_TCF)||(x->SR&XSPI_SR_BUSY)){if((uint32_t)(DWT->CYCCNT-start)>40000000U)return 0;}
 return !(x->SR&(XSPI_SR_TEF|XSPI_SR_FLEVEL))&&(crc^~0U)==expected;
}
