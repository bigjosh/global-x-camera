/* Terminal-only peripheral teardown for the qualified v50 capture/save path.
 *
 * RM0486: 14.6.9 forbids access to unclocked peripherals; 40.9.2 PCR bit0 is
 * NPWRDOWN (zero powers down, despite the CMSIS PWRDOWN spelling); 40.10.1
 * PRCR.PEN=0 resets the digital PHY. The pinned HAL_DCMIPP_DeInit also clears
 * PCR and CSIEN. ES0620 2.2.2 requires BSECEN to remain set.
 *
 * There is deliberately no NOR deep-power-down command: ROM needs to read
 * NOR before our UART recovery guard executes on the next reset.
 */
#include "stm32n6xx.h"
#include "peripherals.h"
#include "save_protocol.h"
#include "save_module_config.h"
#include "photo_fs.h"

#define SAVE_REPORT ((volatile const uint32_t *)SAVE_REPORT_ADDRESS)
#define LOADER_REPORT ((volatile const uint32_t *)0x343F9E00U)
#define CARD_REPORT ((volatile const sd_card_t *)SAVE_CARD_ADDRESS)
#define FS_REPORT ((volatile const photo_fs_report_t *)SAVE_FS_ADDRESS)
#define DATA_OFF_REPORT ((volatile const uint32_t *)0x343F8900U)

#define CAMERA_BUS (RCC_APB5ENR_CSIEN | RCC_APB5ENR_DCMIPPEN)
#define CAMERA_RESET (RCC_APB5RSTR_CSIRST | RCC_APB5RSTR_DCMIPPRST)
#define CAMERA_KERNEL (RCC_DIVENR_IC17EN | RCC_DIVENR_IC18EN)
#define NOR_BUS (RCC_AHB5ENR_XSPI1EN | RCC_AHB5ENR_XSPIMEN)
#define GPIO_BUS (RCC_AHB4ENR_GPIOBEN | RCC_AHB4ENR_GPIOCEN | \
                  RCC_AHB4ENR_GPIONEN | RCC_AHB4ENR_GPIOOEN)
#define GPIO_RESET (RCC_AHB4RSTR_GPIOBRST | RCC_AHB4RSTR_GPIOCRST | \
                    RCC_AHB4RSTR_GPIONRST | RCC_AHB4RSTR_GPIOORST)
#define NOR_PINS ((1U << 1) | (1U << 2) | (1U << 3) | (1U << 6))
#define NOR_MODE_MASK ((3U << 2) | (3U << 4) | (3U << 6) | (3U << 12))
#define NOR_MODE_AF ((2U << 2) | (2U << 4) | (2U << 6) | (2U << 12))
#define NOR_MODE_OFF ((1U << 2) | (1U << 4) | (3U << 6) | (1U << 12))
#define NOR_AF_MASK ((15U << 4) | (15U << 8) | (15U << 12) | (15U << 24))
#define NOR_AF9 ((9U << 4) | (9U << 8) | (9U << 12) | (9U << 24))
#define I2C_MODE_MASK ((3U << 20) | (3U << 22))
#define I2C_MODE_AF ((2U << 20) | (2U << 22))
#define CACHE_MASK (SCB_CCR_IC_Msk | SCB_CCR_DC_Msk)

_Static_assert(sizeof(camera_peripheral_proof_t) == 256U, "Peripheral proof ABI");
_Static_assert(LP_TERMINAL == 63, "Peripheral proof word count");
_Static_assert(sizeof(sd_card_t) == 200U, "Frozen card snapshot ABI");
_Static_assert(sizeof(photo_fs_report_t) == 80U, "Frozen filesystem snapshot ABI");

static int storage_complete(void)
{
    volatile const uint32_t *r = SAVE_REPORT;
    volatile const uint32_t *l = LOADER_REPORT;
    volatile const sd_card_t *c = CARD_REPORT;
    volatile const photo_fs_report_t *f = FS_REPORT;
    if (r[P_MAGIC] != SAVE_REPORT_MAGIC || r[P_SCHEMA] != 1U ||
        r[P_WORDS] != 128U || r[P_TERMINAL] != 0x444F4E45U ||
        r[P_STATE] != 2U || r[P_OP] != SAVE_OP_SAVE ||
        r[P_MODE] != SAVE_DEFAULT_MODE || r[P_NONCE] != 0U ||
        r[P_RESULT] || r[P_STAGE] != 8U || r[P_MEDIA_IDLE] != 1U ||
        r[P_CARD_ERROR] || r[P_FS_RESULT] || r[P_PNG_RESULT] ||
        (r[P_FINAL_CCR] & CACHE_MASK) ||
        r[P_POSTCLEAN_VALIDATED] != 1U ||
        r[P_FNV_BEFORE] != r[P_FNV_AFTER] ||
        r[P_FNV_BEFORE] != r[P_POSTCLEAN_FNV] ||
        r[P_WIDTH] != SAVE_WIDTH || r[P_HEIGHT] != SAVE_HEIGHT ||
        r[P_FRAME_BYTES] != SAVE_FRAME_BYTES ||
        r[P_CARD_SIZE] != sizeof(*c) || r[P_FS_SIZE] != sizeof(*f))
        return CAMERA_PERIPHERAL_BAD_SAVE;
    if (l[0] != 0x534C4431U || l[7] != SAVE_CRC32 ||
        l[8] != SAVE_BYTES || l[10] || !l[11])
        return CAMERA_PERIPHERAL_BAD_LOADER;
    if (c->initialized || c->controller_owned || c->timer_owned ||
        c->media_idle != 1U || c->error || c->cleanup_error ||
        c->stage != SD_STAGE_DEINIT ||
        (c->last_ready_r1 & 0x1F00U) != 0x0900U)
        return CAMERA_PERIPHERAL_BAD_CARD;
    if (f->state != PHOTO_FS_STATE_FINISHED ||
        f->stage != PHOTO_FS_STAGE_RENAME || f->fat_result ||
        f->completed != 1U || !f->bytes_written ||
        f->bytes_written != r[P_PNG_BYTES_LO] || r[P_PNG_BYTES_HI] ||
        f->sector_count != c->sector_count)
        return CAMERA_PERIPHERAL_BAD_FS;
    return CAMERA_PERIPHERAL_OK;
}

static int finish(volatile uint32_t *p, int error)
{
    p[LP_RESULT] = (uint32_t)error;
    p[LP_END] = DWT->CYCCNT;
    p[LP_STATE] = error ? 3U : 2U;
    __DSB();
    p[LP_TERMINAL] = error ? 0U : CAMERA_PERIPHERAL_DONE;
    __DSB();
    return error;
}

/* No CSI/DCMIPP/I2C/XSPI reads here: their reset or clock may already be off.
 * GPIO accesses are guarded independently, including on idempotent calls. */
static int off_state(void)
{
    if ((RCC->AHB4ENR & GPIO_BUS) != GPIO_BUS ||
        (RCC->AHB4RSTR & GPIO_RESET) ||
        !(RCC->APB4ENR2 & RCC_APB4ENR2_BSECEN) ||
        (RCC->APB5ENR & CAMERA_BUS) ||
        (RCC->APB5RSTR & CAMERA_RESET) != CAMERA_RESET ||
        (RCC->DIVENR & CAMERA_KERNEL) ||
        (RCC->APB1ENR1 & RCC_APB1ENR1_I2C2EN) ||
        !(RCC->APB1RSTR1 & RCC_APB1RSTR1_I2C2RST) ||
        (RCC->AHB5ENR & (NOR_BUS | RCC_AHB5ENR_SDMMC2EN)) ||
        !(RCC->AHB5RSTR & RCC_AHB5RSTR_XSPI1RST))
        return 0;
    return (GPIOO->MODER & (3U << 10)) == (1U << 10) &&
           !(GPIOO->OTYPER & (1U << 5)) &&
           !(GPIOO->ODR & (1U << 5)) && !(GPIOO->IDR & (1U << 5)) &&
           (GPION->MODER & NOR_MODE_MASK) == NOR_MODE_OFF &&
           !(GPION->OTYPER & NOR_PINS) &&
           (GPION->ODR & ((1U << 1) | (1U << 2) | (1U << 6))) == (1U << 1) &&
           (GPION->IDR & (1U << 1)) &&
           (GPIOB->MODER & I2C_MODE_MASK) == I2C_MODE_MASK &&
           !(GPIOB->PUPDR & I2C_MODE_MASK) &&
           (GPIOC->IDR & (1U << 4)); /* Powered SD DAT0 remains released. */
}

int camera_peripherals_shutdown(volatile camera_peripheral_proof_t *proof)
{
    if (!proof || ((uintptr_t)proof & 3U))
        return CAMERA_PERIPHERAL_BAD_ARGUMENT;
    /* No cache maintenance is inherited/adopted, and no pending IRQ can run
     * against a clock-gated register bank. An invalid context is not mutated. */
    if ((SCB->CCR & CACHE_MASK) || (__get_CONTROL() & ~0x0CU) ||
        __get_IPSR() || __get_PRIMASK() != 1U || __get_FAULTMASK() ||
        (FPU->FPCCR & FPU_FPCCR_LSPACT_Msk))
        return CAMERA_PERIPHERAL_BAD_CONTEXT;
    volatile uint32_t *p = proof->word;
    int error = storage_complete();
    if (p[LP_MAGIC]) {
        /* Never erase evidence or resume a partially performed teardown. */
        if (p[LP_MAGIC] != CAMERA_PERIPHERAL_MAGIC || p[LP_SCHEMA] != 1U ||
            p[LP_STATE] != 2U || p[LP_RESULT] ||
            p[LP_TERMINAL] != CAMERA_PERIPHERAL_DONE)
            return CAMERA_PERIPHERAL_BAD_PROOF;
        if (error) return error;
        if (p[LP_LOADER_RETURN] != LOADER_REPORT[11] || !off_state())
            return CAMERA_PERIPHERAL_READBACK_FAILED;
        p[LP_REPEAT_COUNT]++;
        __DSB();
        return CAMERA_PERIPHERAL_OK;
    }
    for (unsigned i = 0; i < CAMERA_PERIPHERAL_WORDS; ++i) p[i] = 0;
    p[LP_MAGIC] = CAMERA_PERIPHERAL_MAGIC;
    p[LP_SCHEMA] = 1U; p[LP_STATE] = 1U; p[LP_STAGE] = 1U;
    p[LP_BEGIN] = DWT->CYCCNT;
    p[LP_CCR] = SCB->CCR; p[LP_CONTROL] = __get_CONTROL();
    p[LP_IPSR] = __get_IPSR(); p[LP_PRIMASK] = __get_PRIMASK();
    p[LP_FPCCR] = FPU->FPCCR;
    p[LP_SAVE_DONE] = SAVE_REPORT[P_TERMINAL];
    p[LP_LOADER_RETURN] = LOADER_REPORT[11];
    p[LP_CARD_IDLE] = CARD_REPORT->media_idle;
    p[LP_FS_COMPLETED] = FS_REPORT->completed;
    if (error) return finish(p, error);
    /* This prior capture guard proves HAL pipe-stop and data-lane shutdown
     * completed before sensor STOP, not just that a save report is present. */
    if (DATA_OFF_REPORT[0] != 0x46534431U || DATA_OFF_REPORT[1] != 1U ||
        DATA_OFF_REPORT[2] != 4U || DATA_OFF_REPORT[12] != 3U ||
        DATA_OFF_REPORT[15])
        return finish(p, CAMERA_PERIPHERAL_CAPTURE_BUSY);

    p[LP_STAGE] = 2U;
    p[LP_APB4ENR2] = RCC->APB4ENR2;
    p[LP_APB5ENR] = RCC->APB5ENR; p[LP_APB5RSTR] = RCC->APB5RSTR;
    p[LP_DIVENR] = RCC->DIVENR;
    p[LP_APB1ENR1] = RCC->APB1ENR1; p[LP_APB1RSTR1] = RCC->APB1RSTR1;
    p[LP_AHB5ENR] = RCC->AHB5ENR; p[LP_AHB5RSTR] = RCC->AHB5RSTR;
    p[LP_AHB4ENR] = RCC->AHB4ENR; p[LP_AHB4RSTR] = RCC->AHB4RSTR;
    if (!(p[LP_APB4ENR2] & RCC_APB4ENR2_BSECEN) ||
        (p[LP_APB5ENR] & CAMERA_BUS) != CAMERA_BUS ||
        (p[LP_APB5RSTR] & CAMERA_RESET) ||
        (p[LP_DIVENR] & CAMERA_KERNEL) != CAMERA_KERNEL ||
        !(p[LP_APB1ENR1] & RCC_APB1ENR1_I2C2EN) ||
        (p[LP_APB1RSTR1] & RCC_APB1RSTR1_I2C2RST) ||
        (p[LP_AHB5ENR] & NOR_BUS) != NOR_BUS ||
        (p[LP_AHB5ENR] & (RCC_AHB5ENR_SDMMC2EN |
                          RCC_AHB5ENR_XSPI2EN | RCC_AHB5ENR_XSPI3EN)) ||
        (p[LP_AHB5RSTR] & (RCC_AHB5RSTR_XSPI1RST | RCC_AHB5RSTR_XSPIMRST)) ||
        (p[LP_AHB4ENR] & GPIO_BUS) != GPIO_BUS ||
        (p[LP_AHB4RSTR] & GPIO_RESET))
        return finish(p, CAMERA_PERIPHERAL_BAD_CLOCKS);

    /* These are the only live peripheral snapshots; all clocks/resets have
     * been qualified above, and none of the gates below has yet been changed. */
    p[LP_STAGE] = 3U;
    p[LP_CSI_SR0] = CSI->SR0; p[LP_CSI_SR1] = CSI->SR1;
    p[LP_CSI_CR] = CSI->CR; p[LP_CSI_PCR] = CSI->PCR;
    p[LP_CSI_PRCR] = CSI->PRCR;
    p[LP_DCMIPP_CMSR1] = DCMIPP->CMSR1;
    p[LP_DCMIPP_P0FCTCR] = DCMIPP->P0FCTCR;
    p[LP_DCMIPP_P0FSCR] = DCMIPP->P0FSCR;
    p[LP_I2C_ISR] = I2C2->ISR; p[LP_I2C_CR1] = I2C2->CR1;
    XSPI_TypeDef *x = (XSPI_TypeDef *)XSPI1_BASE_S;
    p[LP_XSPI_SR] = x->SR; p[LP_XSPI_CR] = x->CR;
    p[LP_SENSOR_IDR] = GPIOO->IDR; p[LP_SENSOR_ODR] = GPIOO->ODR;
    p[LP_NOR_IDR] = GPION->IDR; p[LP_NOR_MODER] = GPION->MODER;
    p[LP_SD_IDR] = GPIOC->IDR;
    if ((p[LP_CSI_SR0] & (CSI_SR0_VC0STATEF | CSI_SR0_VC1STATEF |
                         CSI_SR0_VC2STATEF | CSI_SR0_VC3STATEF)) ||
        (p[LP_DCMIPP_CMSR1] & (DCMIPP_CMSR1_P0CPTACT |
                              DCMIPP_CMSR1_P1CPTACT | DCMIPP_CMSR1_P2CPTACT)) ||
        (p[LP_DCMIPP_P0FCTCR] & DCMIPP_P0FCTCR_CPTREQ) ||
        (p[LP_DCMIPP_P0FSCR] & DCMIPP_P0FSCR_PIPEN) ||
        (DCMIPP->P1FCTCR & DCMIPP_P1FCTCR_CPTREQ) ||
        (DCMIPP->P2FCTCR & DCMIPP_P2FCTCR_CPTREQ) ||
        (DCMIPP->P1FSCR & DCMIPP_P1FSCR_PIPEN) ||
        (DCMIPP->P2FSCR & DCMIPP_P2FSCR_PIPEN) ||
        p[LP_CSI_PCR] != 3U || !(p[LP_CSI_PRCR] & CSI_PRCR_PEN))
        return finish(p, CAMERA_PERIPHERAL_CAPTURE_BUSY);
    if (p[LP_I2C_ISR] & I2C_ISR_BUSY)
        return finish(p, CAMERA_PERIPHERAL_I2C_BUSY);
    if ((p[LP_XSPI_SR] & (XSPI_SR_BUSY | XSPI_SR_FLEVEL)) ||
        p[LP_XSPI_CR] != 0x10000001U || x->DCR1 != 0x001F0000U ||
        x->DCR2 != 1U || x->CCR != 0x01002101U || x->TCR != 8U ||
        x->IR != 0x0BU || *(volatile uint32_t *)XSPIM_BASE_S != 2U)
        return finish(p, CAMERA_PERIPHERAL_NOR_BUSY);
    if ((GPIOO->MODER & (3U << 10)) != (1U << 10) ||
        (GPIOO->OTYPER & (1U << 5)) ||
        (p[LP_NOR_MODER] & NOR_MODE_MASK) != NOR_MODE_AF ||
        (GPION->OTYPER & NOR_PINS) ||
        (GPION->AFR[0] & NOR_AF_MASK) != NOR_AF9 ||
        (GPIOB->MODER & I2C_MODE_MASK) != I2C_MODE_AF ||
        !(p[LP_SD_IDR] & (1U << 4)))
        return finish(p, CAMERA_PERIPHERAL_BAD_PINS);

    /* No active storage/capture transaction remains. First remove receiver
     * interrupt sources while the register banks are live; global IRQ remains
     * masked by the caller. Preserve the raw error history in the proof. */
    p[LP_STAGE] = 4U; p[LP_MUTATION_STARTED] = 1U; __DSB();
    CSI->IER0 = 0; CSI->IER1 = 0;
    DCMIPP->CMIER = 0;
    DCMIPP->P0IER = 0; DCMIPP->P1IER = 0; DCMIPP->P2IER = 0;
    CSI->CR &= ~CSI_CR_CSIEN;
    CSI->PRCR &= ~CSI_PRCR_PEN;
    CSI->PCR = 0; /* NPWRDOWN=0, clock/data lanes disabled. */
    __DSB();
    p[LP_CSI_CR_OFF] = CSI->CR;
    p[LP_CSI_PRCR_OFF] = CSI->PRCR;
    p[LP_CSI_PCR_OFF] = CSI->PCR;
    if ((p[LP_CSI_CR_OFF] & CSI_CR_CSIEN) ||
        (p[LP_CSI_PRCR_OFF] & CSI_PRCR_PEN) || p[LP_CSI_PCR_OFF])
        return finish(p, CAMERA_PERIPHERAL_READBACK_FAILED);
    /* Sensor software STOP has completed. Hardware reset now holds its
     * transmitter inactive. Keep PO5 push-pull LOW in Sleep/Stop. Standby
     * resets pad state and is a separately qualified completion mode. */
    GPIOO->BSRR = 1U << 21;
    GPIOO->OSPEEDR &= ~(3U << 10);
    __DSB();
    p[LP_SENSOR_IDR_OFF] = GPIOO->IDR;
    if (p[LP_SENSOR_IDR_OFF] & (1U << 5))
        return finish(p, CAMERA_PERIPHERAL_READBACK_FAILED);
    RCC->APB5RSTSR = RCC_APB5RSTSR_CSIRSTS | RCC_APB5RSTSR_DCMIPPRSTS;
    __DSB();
    /* From here onward NEVER read CSI/DCMIPP, including failure paths. */
    RCC->APB5ENCR = RCC_APB5ENCR_CSIENC | RCC_APB5ENCR_DCMIPPENC;
    RCC->APB5LPENCR = RCC_APB5LPENCR_CSILPENC | RCC_APB5LPENCR_DCMIPPLPENC;
    RCC->DIVENCR = RCC_DIVENCR_IC17ENC | RCC_DIVENCR_IC18ENC;
    __DSB();

    p[LP_STAGE] = 5U;
    I2C2->CR1 &= ~I2C_CR1_PE;
    __DSB(); p[LP_I2C_CR1_OFF] = I2C2->CR1;
    if (p[LP_I2C_CR1_OFF] & I2C_CR1_PE)
        return finish(p, CAMERA_PERIPHERAL_READBACK_FAILED);
    /* Analog/no-pull releases PB10/11 without sourcing current into the
     * reset sensor. Do not pull an externally biased I2C bus LOW. */
    GPIOB->MODER |= I2C_MODE_MASK;
    GPIOB->PUPDR &= ~I2C_MODE_MASK;
    RCC->APB1RSTSR1 = RCC_APB1RSTSR1_I2C2RSTS;
    __DSB();
    /* From here onward NEVER read I2C2. */
    RCC->APB1ENCR1 = RCC_APB1ENCR1_I2C2ENC;
    RCC->APB1LPENCR1 = RCC_APB1LPENCR1_I2C2LPENC;
    __DSB();

    p[LP_STAGE] = 6U;
    /* The last NOR operation was a completed, CRC-verified finite read.
     * PN1 AF-mode IDR read LOW on v54d despite idle XSPI; the cause is not
     * established. Preload nCS HIGH before GPIO takeover and require HIGH
     * readback before disabling XSPI or touching CLK/MOSI. This only
     * deselects the flash: no clock edge or NOR command is requested. */
    GPION->BSRR = 1U << 1;
    GPION->MODER = (GPION->MODER & ~(3U << 2)) | (1U << 2);
    __DSB();
    if (!(GPION->IDR & (1U << 1)))
        return finish(p, CAMERA_PERIPHERAL_READBACK_FAILED);
    x->CR &= ~XSPI_CR_EN;
    __DSB(); p[LP_XSPI_CR_OFF] = x->CR;
    if (p[LP_XSPI_CR_OFF] & XSPI_CR_EN)
        return finish(p, CAMERA_PERIPHERAL_READBACK_FAILED);
    GPION->BSRR = ((1U << 2) | (1U << 6)) << 16;
    GPION->MODER = (GPION->MODER & ~NOR_MODE_MASK) | NOR_MODE_OFF;
    GPION->PUPDR &= ~NOR_MODE_MASK;
    GPION->OSPEEDR &= ~NOR_MODE_MASK;
    RCC->AHB5RSTSR = RCC_AHB5RSTSR_XSPI1RSTS;
    __DSB();
    /* From here onward NEVER read XSPI1 or XSPIM. Other XSPI clients were
     * required to be disabled before gating the shared XSPIM clock. */
    RCC->AHB5ENCR = RCC_AHB5ENCR_XSPI1ENC | RCC_AHB5ENCR_XSPIMENC;
    RCC->AHB5LPENCR = RCC_AHB5LPENCR_XSPI1LPENC | RCC_AHB5LPENCR_XSPIMLPENC;
    __DSB();

    p[LP_STAGE] = 7U;
    p[LP_NOR_MODER_OFF] = GPION->MODER; p[LP_NOR_IDR_OFF] = GPION->IDR;
    p[LP_SENSOR_MODER_OFF] = GPIOO->MODER;
    p[LP_I2C_MODER_OFF] = GPIOB->MODER;
    p[LP_APB5ENR_OFF] = RCC->APB5ENR; p[LP_APB5RSTR_OFF] = RCC->APB5RSTR;
    p[LP_DIVENR_OFF] = RCC->DIVENR;
    p[LP_APB1ENR1_OFF] = RCC->APB1ENR1;
    p[LP_APB1RSTR1_OFF] = RCC->APB1RSTR1;
    p[LP_AHB5ENR_OFF] = RCC->AHB5ENR; p[LP_AHB5RSTR_OFF] = RCC->AHB5RSTR;
    p[LP_APB4ENR2_OFF] = RCC->APB4ENR2;
    return finish(p, off_state() ? CAMERA_PERIPHERAL_OK :
                  CAMERA_PERIPHERAL_READBACK_FAILED);
}
