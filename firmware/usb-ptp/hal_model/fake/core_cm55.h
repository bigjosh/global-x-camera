/* Host stand-in for the Cortex-M55 core header: types and barriers only. */
#ifndef FAKE_CORE_CM55_H
#define FAKE_CORE_CM55_H
#include <stdint.h>
#define __I volatile const
#define __O volatile
#define __IO volatile
#define __IM volatile const
#define __OM volatile
#define __IOM volatile
#define __STATIC_INLINE static inline
#define __STATIC_FORCEINLINE static inline
#define __INLINE inline
#define __ASM __asm
#define __WEAK __attribute__((weak))
#define __PACKED __attribute__((packed))
#define __PACKED_STRUCT struct __attribute__((packed))
#define __NO_RETURN __attribute__((noreturn))
#define __USED __attribute__((used))
#define __ALIGNED(x) __attribute__((aligned(x)))
#define __RESTRICT __restrict
typedef struct { volatile uint32_t CTRL, CYCCNT; } DWT_Type;
#define DWT ((DWT_Type *)0xE0001000UL)
typedef struct { volatile uint32_t r[64]; volatile uint32_t CCR; } SCB_Type;
/* Memory protection is off after the boot ROM; the model keeps it off. */
typedef struct { volatile uint32_t TYPE, CTRL; } MPU_Type;
extern MPU_Type model_mpu;
#define MPU (&model_mpu)
#define MPU_CTRL_ENABLE_Msk 1UL
void sim_sync(void);
void sim_nop(void);
#define __DSB() sim_sync()
#define __ISB() ((void)0)
#define __NOP() sim_nop()
#define __CLZ __builtin_clz
#define __RBIT(x) 0
static inline uint32_t __get_PRIMASK(void){return 0;}
static inline void __set_PRIMASK(uint32_t x){(void)x;}
static inline void __disable_irq(void){}
static inline void __enable_irq(void){}
#endif
