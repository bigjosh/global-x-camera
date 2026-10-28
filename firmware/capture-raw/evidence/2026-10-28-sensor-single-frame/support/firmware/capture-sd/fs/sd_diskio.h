#ifndef CAMERA_SD_DISKIO_H
#define CAMERA_SD_DISKIO_H
#include <stdint.h>
#include "sd_card.h"
/* Caller must initialize the card first. Binding never initializes, formats,
 * resets or switches power. Single owner, one physical drive, non-reentrant. */
int sd_disk_bind(sd_card_t *card);
sd_card_t *sd_disk_card(void);
#endif
