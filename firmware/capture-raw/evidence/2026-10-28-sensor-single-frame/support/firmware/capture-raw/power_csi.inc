/* RAM-only receiver attribution after validated FRAME + software STOP and
 * sensor hardware reset. Retain APB/kernel clocks: registers remain accessible.
 * No interface reset or SRAM manipulation; the next experiment resets the MCU.
 */
#if RAW_POWER_PROBE != 5 || RAW_FLASH || RAW_STANDBY
#error Receiver-off power probe is RAM-only mode 5
#endif
__attribute__((used,aligned(32))) volatile uint32_t raw_power_csi_proof[32];
static int power_csi_off(void)
{
    volatile uint32_t *v=raw_power_csi_proof;
    for(unsigned i=0;i<32;i++) v[i]=0;
    v[0]=0x31595043U; v[1]=1; v[2]=1; v[4]=DWT->CYCCNT;
    const uint32_t clocks=RCC_APB5ENR_CSIEN|RCC_APB5ENR_DCMIPPEN;
    const uint32_t resets=RCC_APB5RSTR_CSIRST|RCC_APB5RSTR_DCMIPPRST;
    const uint32_t kernels=RCC_DIVENR_IC17EN|RCC_DIVENR_IC18EN;
    v[6]=RCC->APB5ENR; v[7]=RCC->APB5RSTR; v[8]=RCC->DIVENR;
    /* Never inspect the camera register banks before proving clocks/reset. */
    if((v[6]&clocks)!=clocks || (v[7]&resets) || (v[8]&kernels)!=kernels) {
        v[3]=1; v[2]=15; return 1;
    }
    v[9]=CSI->CR; v[10]=CSI->PRCR; v[11]=CSI->PCR;
    v[12]=CSI->SR0; v[13]=CSI->SR1; v[14]=DCMIPP->CMSR1;
    v[15]=DCMIPP->P0FCTCR; v[16]=DCMIPP->P0FSCR;
    v[17]=DCMIPP->P1FCTCR; v[18]=DCMIPP->P1FSCR;
    v[19]=DCMIPP->P2FCTCR; v[20]=DCMIPP->P2FSCR;
    v[27]=CSI->IER0; v[28]=CSI->IER1;
    const uint32_t vc=CSI_SR0_VC0STATEF|CSI_SR0_VC1STATEF|CSI_SR0_VC2STATEF|CSI_SR0_VC3STATEF;
    const uint32_t active=DCMIPP_CMSR1_P0CPTACT|DCMIPP_CMSR1_P1CPTACT|DCMIPP_CMSR1_P2CPTACT;
    if(!(v[9]&CSI_CR_CSIEN) || !(v[10]&CSI_PRCR_PEN) || v[11]!=3U ||
       (v[12]&vc) || (v[14]&active) ||
       (v[15]&DCMIPP_P0FCTCR_CPTREQ) || (v[16]&DCMIPP_P0FSCR_PIPEN) ||
       (v[17]&DCMIPP_P1FCTCR_CPTREQ) || (v[18]&DCMIPP_P1FSCR_PIPEN) ||
       (v[19]&DCMIPP_P2FCTCR_CPTREQ) || (v[20]&DCMIPP_P2FSCR_PIPEN)) {
        v[3]=2; v[2]=15; return 2;
    }
    /* All raw status remains in the proof. Mask ended receiver observations
     * before disabling its PHY, preserving IRQ state outside the camera. */
    uint32_t primask=__get_PRIMASK(); __disable_irq();
    NVIC_DisableIRQ(CSI_IRQn); NVIC_DisableIRQ(DCMIPP_IRQn);
    CSI->IER0=0; CSI->IER1=0;
    CSI->CR&=~CSI_CR_CSIEN; CSI->PRCR&=~CSI_PRCR_PEN;
    CSI->PCR=0;
    __DSB();
    v[21]=CSI->CR; v[22]=CSI->PRCR; v[23]=CSI->PCR;
    v[24]=RCC->APB5ENR; v[25]=RCC->APB5RSTR; v[26]=RCC->DIVENR;
    v[29]=CSI->IER0; v[30]=CSI->IER1;
    __set_PRIMASK(primask);
    v[5]=DWT->CYCCNT;
    if((v[21]&CSI_CR_CSIEN) || (v[22]&CSI_PRCR_PEN) || v[23] ||
       v[24]!=v[6] || v[25]!=v[7] || v[26]!=v[8] || v[29] || v[30]) {
        v[3]=4; v[2]=15; return 4;
    }
    v[2]=2; __DSB(); return 0;
}
