#ifndef GLOBAL_X_USBD_CONF_H
#define GLOBAL_X_USBD_CONF_H
#include "stm32n6xx.h"
#include "stm32n6xx_hal.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define USBD_MAX_NUM_INTERFACES 1U
#define USBD_MAX_NUM_CONFIGURATION 1U
#define USBD_MAX_SUPPORTED_CLASS 1U
#define USBD_MAX_STR_DESC_SIZ 128U
#define USBD_SELF_POWERED 1U
#define USBD_DEBUG_LEVEL 0U
#define USBD_LPM_ENABLED 0U
#define USBD_CLASS_BOS_ENABLED 0U
#define USBD_SUPPORT_USER_STRING_DESC 0U
#define USBD_CLASS_USER_STRING_DESC 0U
#define USBD_USER_REGISTER_CALLBACK 0U
#define USBD_memset memset
#define USBD_memcpy memcpy
#endif
