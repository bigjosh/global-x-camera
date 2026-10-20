/* Native-only test bridge: exercises exactly the target's pure C detector. */
#include "pulse_detector.h"
#include <stddef.h>
#ifdef _WIN32
#define EXPORTED __declspec(dllexport)
#else
#define EXPORTED
#endif
EXPORTED void vcp_test_run(const uint32_t *times, const uint32_t *levels,
                          uint32_t count, uint32_t start,
                          recovery_vcp_detector *result)
{
    recovery_vcp_init(result,times[0],levels[0]);
    for (uint32_t i=1U; i<count; ++i) {
        if ((uint32_t)(times[i]-start)>=VCP_WINDOW_CYCLES) break;
        recovery_vcp_sample(result,times[i],levels[i]);
    }
}
