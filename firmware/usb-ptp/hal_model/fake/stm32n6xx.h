/* Route every HAL/LL register write through the bus model. */
#ifndef FAKE_STM32N6XX_H
#define FAKE_STM32N6XX_H
#include_next "stm32n6xx.h"
#include <stdint.h>
uint32_t sim_write(volatile uint32_t *reg, uint32_t value);
#undef SET_BIT
#undef CLEAR_BIT
#undef WRITE_REG
#undef MODIFY_REG
#undef CLEAR_REG
#define SET_BIT(REG, BIT)     sim_write((volatile uint32_t *)&(REG), (REG) | (BIT))
#define CLEAR_BIT(REG, BIT)   sim_write((volatile uint32_t *)&(REG), (REG) & ~(BIT))
#define WRITE_REG(REG, VAL)   sim_write((volatile uint32_t *)&(REG), (VAL))
#define CLEAR_REG(REG)        sim_write((volatile uint32_t *)&(REG), 0)
#define MODIFY_REG(REG, CLEARMASK, SETMASK) sim_write((volatile uint32_t *)&(REG), (((REG) & (~(CLEARMASK))) | (SETMASK)))
#endif
