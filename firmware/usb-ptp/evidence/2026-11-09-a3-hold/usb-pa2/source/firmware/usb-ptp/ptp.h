#ifndef GX_PTP_H
#define GX_PTP_H
#include <stdint.h>
#include "storage/photo_store.h"
extern volatile uint32_t ptp_stats[32];
extern volatile uint32_t ptp_log[128][8];
int ptp_init(photo_store_t *store, void *photo_buffer);
void ptp_poll(void);
int ptp_service(void *unused);
void ptp_stop(void);
#endif
