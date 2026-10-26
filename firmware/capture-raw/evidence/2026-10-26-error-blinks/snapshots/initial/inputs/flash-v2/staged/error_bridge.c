#include "error_signal.h"
__attribute__((section(".error_bridge"),noreturn,noinline,used))
void error_stage1_bridge(void) {
    unsigned result=*(volatile unsigned *)0x343F3004U;
    error_signal_shutdown(result==17U?2U:8U);
}
