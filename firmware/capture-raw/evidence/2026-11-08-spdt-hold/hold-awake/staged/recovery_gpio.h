#ifndef RECOVERY_GPIO_H
#define RECOVERY_GPIO_H

void recovery_gpio_begin(void);
void recovery_gpio_check(void);
void recovery_gpio_publish(void);
void recovery_gpio_park(void) __attribute__((noreturn));

#endif
