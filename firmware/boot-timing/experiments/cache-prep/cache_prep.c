/* Offline-built, RAM-only diagnostic for the observed I-cache-on/D-cache-off
 * state. This does not initialize clocks, security, peripherals or storage. */
#include "stm32n657xx.h"

__attribute__((noreturn)) void cache_prep_body(uint32_t original_msplim)
{
    volatile uint32_t *const status = (volatile uint32_t *)0x34190400UL;
    const uint32_t before = SCB->CCR;

    /* Refuse to alter caches if the precondition changed. With D-cache enabled,
     * these RAM status writes are not guaranteed visible to the debugger. */
    status[0] = 0x50524550UL; /* PREP: started */
    status[1] = before;
    status[2] = original_msplim;
    status[3] = __get_MSPLIM();
    status[4] = before;
    if ((before & SCB_CCR_DC_Msk) == 0U) {
        SCB_DisableICache(); /* Pinned CMSIS: barriers, disable, invalidate. */
        status[4] = SCB->CCR;
        status[0] = ((SCB->CCR & SCB_CCR_IC_Msk) == 0U)
            ? 0x43414348UL /* CACH: completed */
            : 0x4641494CUL; /* FAIL: did not clear */
    } else {
        status[0] = 0x44434143UL; /* DCAC: refused; D-cache was enabled */
    }
    __DSB();
    __ISB();
    /* Stay awake and attachable even when CubeProgrammer disconnects.
     * BKPT would risk a HardFault after the debugger releases the core. */
    __asm volatile (
        ".global cache_prep_ready\n"
        "cache_prep_ready:\n"
        "nop\n"
        "b cache_prep_ready\n"
        ::: "memory");
    __builtin_unreachable();
}
