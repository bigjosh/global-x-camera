#ifndef CAMERA_LOW_POWER_PERIPHERALS_H
#define CAMERA_LOW_POWER_PERIPHERALS_H

#include <stdint.h>

#define CAMERA_PERIPHERAL_MAGIC 0x504C5031U /* PLP1 */
#define CAMERA_PERIPHERAL_DONE  0x50444F4EU /* PDON */
#define CAMERA_PERIPHERAL_WORDS 64U

typedef struct {
    uint32_t word[CAMERA_PERIPHERAL_WORDS];
} camera_peripheral_proof_t;

enum camera_peripheral_word {
    LP_MAGIC, LP_SCHEMA, LP_STATE, LP_STAGE, LP_RESULT, LP_BEGIN, LP_END,
    LP_CCR, LP_CONTROL, LP_IPSR, LP_PRIMASK,
    LP_APB4ENR2, LP_APB5ENR, LP_APB5RSTR, LP_DIVENR,
    LP_APB1ENR1, LP_APB1RSTR1, LP_AHB5ENR, LP_AHB5RSTR,
    LP_AHB4ENR, LP_AHB4RSTR,
    LP_CSI_SR0, LP_CSI_SR1, LP_CSI_CR, LP_CSI_PCR, LP_CSI_PRCR,
    LP_DCMIPP_CMSR1, LP_DCMIPP_P0FCTCR, LP_DCMIPP_P0FSCR,
    LP_I2C_ISR, LP_I2C_CR1, LP_XSPI_SR, LP_XSPI_CR,
    LP_SENSOR_IDR, LP_SENSOR_ODR, LP_NOR_IDR, LP_NOR_MODER,
    LP_SD_IDR, LP_SAVE_DONE, LP_LOADER_RETURN, LP_CARD_IDLE, LP_FS_COMPLETED,
    LP_CSI_PCR_OFF, LP_CSI_PRCR_OFF, LP_CSI_CR_OFF,
    LP_I2C_CR1_OFF, LP_XSPI_CR_OFF, LP_SENSOR_IDR_OFF,
    LP_NOR_MODER_OFF, LP_NOR_IDR_OFF,
    LP_APB5ENR_OFF, LP_APB5RSTR_OFF, LP_DIVENR_OFF,
    LP_APB1ENR1_OFF, LP_APB1RSTR1_OFF, LP_AHB5ENR_OFF, LP_AHB5RSTR_OFF,
    LP_APB4ENR2_OFF, LP_SENSOR_MODER_OFF, LP_I2C_MODER_OFF,
    LP_FPCCR, LP_REPEAT_COUNT, LP_MUTATION_STARTED, LP_TERMINAL
};

enum camera_peripheral_result {
    CAMERA_PERIPHERAL_OK = 0,
    CAMERA_PERIPHERAL_BAD_ARGUMENT = 1,
    CAMERA_PERIPHERAL_BAD_CONTEXT,
    CAMERA_PERIPHERAL_BAD_SAVE,
    CAMERA_PERIPHERAL_BAD_LOADER,
    CAMERA_PERIPHERAL_BAD_CARD,
    CAMERA_PERIPHERAL_BAD_FS,
    CAMERA_PERIPHERAL_BAD_PROOF,
    CAMERA_PERIPHERAL_BAD_CLOCKS,
    CAMERA_PERIPHERAL_CAPTURE_BUSY,
    CAMERA_PERIPHERAL_I2C_BUSY,
    CAMERA_PERIPHERAL_NOR_BUSY,
    CAMERA_PERIPHERAL_BAD_PINS,
    CAMERA_PERIPHERAL_READBACK_FAILED
};

/* Successful automatic SAVE only, after photo_save_load() has returned.
 * Caller owns/zeros this 256-byte proof once per boot, outside the image and
 * save workspaces; the completion integration reserves 0x343F9D00.
 *
 * Requires interrupt-masked privileged MSP Thread mode, no pending lazy FP
 * preservation and both CPU caches off. Existing FPCA/SFPA flags are preserved.
 * Before touching a peripheral it verifies SAVE DONE, exact loader CRC/length,
 * finished filesystem/card snapshots, clock/reset access, and live idle state.
 * It holds sensor PO5 LOW; powers down/reset-gates CSI/DCMIPP; releases I2C2;
 * keeps NOR NCS HIGH and reset-gates its idle controller. No storage commands,
 * core clock, SRAM, BSEC, PWR, debug, EXTI or NVIC changes are made here.
 *
 * Success is terminal: do not restart camera/NOR/SD or use old maintenance
 * helpers without a fresh boot and the normal initialization/ownership gates.
 * A second call is a read-only state check, apart from incrementing the proof
 * repeat count. It never reads the gated CSI/I2C/XSPI register banks. A partial
 * or failed attempt is not retried. On nonzero return, remain powered/awake.
 * Filesystem/card-ready evidence is not a power-loss durability guarantee.
 */
int camera_peripherals_shutdown(volatile camera_peripheral_proof_t *proof);

#endif
