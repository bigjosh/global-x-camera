#ifndef CAMERA_PHASE_GPIO_H
#define CAMERA_PHASE_GPIO_H
#include <stdint.h>
/* Diagnostic only. PD12 = Arduino D8/CN14.1 = CN15.21. */
int phase_gpio_init(void);
int phase_gpio_emit(uint32_t event);
#endif
