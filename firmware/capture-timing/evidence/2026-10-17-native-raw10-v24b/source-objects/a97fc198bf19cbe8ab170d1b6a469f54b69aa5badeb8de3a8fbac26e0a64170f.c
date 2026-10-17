/* Bench-only fixed-profile sensor startup before second-stage NOR loading.
 * The register order follows the frozen v16 HAL/VD6G benchmark. This file uses
 * only bounded polling and integer operations; it does not alter ROM clocks,
 * NOR settings, OTP, lifecycle state, the sensor's calibration, or XSHUTDOWN.
 */
#include <stdint.h>
#include "stm32n657xx.h"

#define TRACE ((volatile uint32_t *)0x343F0000U)
#define EVENTS ((volatile uint32_t *)0x343F0100U)
#define SENSOR ((volatile uint32_t *)0x343F4000U)
#define TIMEOUT (400000000U / 2U)
#define ERRORS (I2C_ISR_NACKF | I2C_ISR_BERR | I2C_ISR_ARLO | I2C_ISR_OVR | I2C_ISR_TIMEOUT)
#define CLEAR_ERRORS (I2C_ICR_NACKCF | I2C_ICR_STOPCF | I2C_ICR_BERRCF | I2C_ICR_ARLOCF | I2C_ICR_OVRCF | I2C_ICR_TIMOUTCF)

enum { S_MAGIC, S_PHASE, S_RESULT, S_ISR, S_START_BEGIN, S_START_END,
       S_READY_CYCLES, S_BOOT_CYCLES, S_MODEL, S_REVISION, S_ROM, S_LINE,
       S_WRITE_TX, S_WRITE_BYTES, S_READ_TX, S_READ_BYTES, S_RECEIVER_READY };

static void event(uint32_t id)
{
    uint32_t n=TRACE[2];
    if(n<200U) {
        EVENTS[n*4]=id; EVENTS[n*4+1]=DWT->CYCCNT;
        EVENTS[n*4+2]=0; EVENTS[n*4+3]=400000000U; TRACE[2]=n+1;
    }
    TRACE[1]=id; GPIOE->ODR^=1U; __DMB();
}

static int wait_flag(uint32_t flag, uint32_t began)
{
    uint32_t attempts=0;
    do {
        uint32_t status=I2C2->ISR;
        SENSOR[S_ISR]=status;
        if(status & ERRORS) return -(int)(status & ERRORS);
        if(status & flag) return 0;
    } while((uint32_t)(DWT->CYCCNT-began)<TIMEOUT && ++attempts<10000000U);
    return -1;
}

static int finish(int result)
{
    /* Clear a completed/NACKed transfer before the next bounded READY probe.
     * Never retry arbitration/bus faults as if they were ordinary startup. */
    if(result && (I2C2->ISR & I2C_ISR_BUSY)) {
        I2C2->CR2 |= I2C_CR2_STOP;
        uint32_t start=DWT->CYCCNT, attempts=0;
        while((I2C2->ISR & I2C_ISR_BUSY) &&
              (uint32_t)(DWT->CYCCNT-start)<400000U && ++attempts<100000U) __NOP();
    }
    I2C2->ICR=CLEAR_ERRORS;
    I2C2->CR2=0;
    return result;
}

static int write_reg(uint16_t address, const uint8_t *data, uint32_t bytes)
{
    uint32_t began=DWT->CYCCNT;
    if(I2C2->ISR & I2C_ISR_BUSY) return -2;
    SENSOR[S_WRITE_TX]++; SENSOR[S_WRITE_BYTES]+=bytes;
    I2C2->ICR=CLEAR_ERRORS;
    I2C2->CR2=0x20U | ((bytes+2U)<<I2C_CR2_NBYTES_Pos) | I2C_CR2_AUTOEND | I2C_CR2_START;
    for(uint32_t i=0;i<bytes+2U;++i) {
        int ret=wait_flag(I2C_ISR_TXIS,began);
        if(ret) return finish(ret);
        I2C2->TXDR=i==0 ? address>>8 : i==1 ? address&255U : data[i-2U];
    }
    return finish(wait_flag(I2C_ISR_STOPF,began));
}

static int read_reg(uint16_t address, uint32_t bytes, uint32_t *value)
{
    uint32_t began=DWT->CYCCNT, result=0;
    if(I2C2->ISR & I2C_ISR_BUSY) return -2;
    SENSOR[S_READ_TX]++; SENSOR[S_READ_BYTES]+=bytes;
    I2C2->ICR=CLEAR_ERRORS;
    I2C2->CR2=0x20U | (2U<<I2C_CR2_NBYTES_Pos) | I2C_CR2_START;
    for(uint32_t i=0;i<2U;++i) {
        int ret=wait_flag(I2C_ISR_TXIS,began);
        if(ret) return finish(ret);
        I2C2->TXDR=i ? address&255U : address>>8;
    }
    int ret=wait_flag(I2C_ISR_TC,began);
    if(ret) return finish(ret);
    I2C2->CR2=0x20U | (bytes<<I2C_CR2_NBYTES_Pos) | I2C_CR2_RD_WRN | I2C_CR2_AUTOEND | I2C_CR2_START;
    for(uint32_t i=0;i<bytes;++i) {
        ret=wait_flag(I2C_ISR_RXNE,began);
        if(ret) return finish(ret);
        result |= (I2C2->RXDR & 255U) << (i*8U);
    }
    ret=finish(wait_flag(I2C_ISR_STOPF,began));
    if(!ret) *value=result;
    return ret;
}

static int write_value(uint16_t address, uint32_t value, uint32_t bytes)
{
    uint8_t data[4]={(uint8_t)value,(uint8_t)(value>>8),(uint8_t)(value>>16),(uint8_t)(value>>24)};
    return write_reg(address,data,bytes);
}

static int poll(uint16_t address, uint32_t expected, int allow_nack)
{
    uint32_t began=DWT->CYCCNT, attempts=0, value;
    do {
        int ret=read_reg(address,1,&value);
        if(!ret && value==expected) return 0;
        if(ret && !(allow_nack && ret==-(int)I2C_ISR_NACKF)) return ret;
        uint32_t delay=DWT->CYCCNT;
        while((uint32_t)(DWT->CYCCNT-delay)<20000U) __NOP();
    } while((uint32_t)(DWT->CYCCNT-began)<TIMEOUT && ++attempts<1000000U);
    return -3;
}

static int failure(uint32_t phase, int result)
{
    SENSOR[S_PHASE]=phase; SENSOR[S_RESULT]=(uint32_t)result;
    return result ? result : -4;
}
#define TRY(phase,call) do { int result=(call); if(result) return failure(phase,result); } while(0)

int stage1_sensor_start(void)
{
    uint32_t value;
    for(unsigned i=0;i<32U;++i) SENSOR[i]=0;
    SENSOR[S_MAGIC]=0x53454E31U; /* SEN1 */
    if((RCC->CCIPR4 & RCC_CCIPR4_I2C2SEL)!=0) return failure(1,-5);
    RCC->AHB4ENSR=RCC_AHB4ENSR_GPIOBENS | RCC_AHB4ENSR_GPIOAENS;
    (void)RCC->AHB4ENR;
    /* PA0 stays input before the module's level translator can drive it. */
    GPIOA->MODER &= ~3U; GPIOA->PUPDR &= ~3U;
    /* PB10/11 AF4 open-drain, no pulls, HIGH speed: same as Nucleo BSP. */
    GPIOB->OTYPER |= (1U<<10)|(1U<<11);
    GPIOB->PUPDR &= ~(15U<<20);
    GPIOB->OSPEEDR=(GPIOB->OSPEEDR & ~(15U<<20)) | (10U<<20);
    GPIOB->AFR[1]=(GPIOB->AFR[1] & ~(255U<<8)) | (0x44U<<8);
    GPIOB->MODER=(GPIOB->MODER & ~(15U<<20)) | (10U<<20);
    RCC->APB1ENSR1=RCC_APB1ENSR1_I2C2ENS; (void)RCC->APB1ENR1;
    RCC->APB1RSTSR1=RCC_APB1RSTSR1_I2C2RSTS;
    RCC->APB1RSTCR1=RCC_APB1RSTCR1_I2C2RSTC;
    I2C2->CR1=0; I2C2->TIMINGR=0x10831A27U; I2C2->TIMEOUTR=0;
    I2C2->OAR1=I2C_OAR1_OA1EN; I2C2->OAR2=0; I2C2->ICR=CLEAR_ERRORS;
    I2C2->CR1=I2C_CR1_FMP | I2C_CR1_PE;
    TRACE[32]=150000000U; TRACE[33]=I2C2->TIMINGR; TRACE[34]=I2C2->CR1;
    event(220); event(100);
    TRY(2,poll(0x0028,1,1)); SENSOR[S_READY_CYCLES]=DWT->CYCCNT;
    event(101);
    TRY(3,read_reg(0x0000,2,&value)); SENSOR[S_MODEL]=value;
    if(value!=0x5603U) return failure(3,-6);
    TRY(4,read_reg(0x0002,2,&value)); SENSOR[S_REVISION]=value;
    if((value>>8)!=0x31U) return failure(4,-7);
    TRY(5,read_reg(0x0014,2,&value)); SENSOR[S_ROM]=value;
    event(102); TRY(6,read_reg(0x0002,2,&value));
    if((value>>8)!=0x31U) return failure(6,-7);
    event(103);
    TRY(7,write_value(0x0200,1,1));
    TRY(8,poll(0x0200,0,0)); TRY(9,poll(0x0028,2,0));
    SENSOR[S_BOOT_CYCLES]=DWT->CYCCNT;
    event(104); TRY(10,read_reg(0x0002,2,&value));
    if((value>>8)!=0x31U) return failure(10,-7);
    event(105); TRY(11,read_reg(0x001A,1,&value));
    event(106);
    static const uint8_t gpios[8]={2,0x15,1,1,1,1,1,1};
    TRY(12,write_reg(0x0467,gpios,8));
    event(107);
    TRY(13,write_value(0x0220,12000000U,4));
    TRY(14,write_value(0x0224,2,1)); TRY(15,write_value(0x0226,134,1));
    TRY(16,read_reg(0x0300,2,&value)); SENSOR[S_LINE]=value;
    if(value!=1236U) return failure(16,-8);
    TRY(17,write_value(0x0458,4336,2));
    event(12);
    TRY(18,write_value(0x0458,4336,2)); /* v16 explicit frame override */
    TRY(19,write_value(0x0471,0,2)); TRY(20,write_value(0x0201,6,1));
    TRY(21,poll(0x0201,0,0));
    static const uint8_t manual[12]={2,0,0x94,5,0,1,0,1,0,1,0,1}; /* 1428 */
    TRY(22,write_reg(0x044C,manual,12));
    event(15); event(108);
    TRY(23,write_value(0x030A,10,1)); TRY(24,write_value(0x030C,0x02CA,2));
    TRY(25,write_value(0x0312,804,2)); TRY(26,write_value(0x030F,0x2B,1));
    TRY(27,write_value(0x047E,0,1));
    TRY(28,write_value(0x045E,2,2)); TRY(29,write_value(0x0460,1121,2));
    TRY(30,write_value(0x0462,0,2)); TRY(31,write_value(0x0464,1363,2));
    TRY(32,write_value(0x044C,2,1)); TRY(33,write_value(0x0302,0,1));
    TRY(34,write_value(0x0400,0,2)); TRY(35,write_value(0x0430,0,2));
    event(109); event(24); SENSOR[S_START_BEGIN]=DWT->CYCCNT;
    TRY(36,write_value(0x0201,1,1));
    SENSOR[S_START_END]=DWT->CYCCNT; event(25);
    TRACE[40]=SENSOR[S_WRITE_TX]; TRACE[41]=SENSOR[S_WRITE_BYTES];
    TRACE[42]=SENSOR[S_READ_TX]; TRACE[43]=SENSOR[S_READ_BYTES];
    SENSOR[S_PHASE]=37; SENSOR[S_RESULT]=0; __DSB();
    /* Do not wait for START ACK/STREAMING here: load the receiver concurrently. */
    return 0;
}
