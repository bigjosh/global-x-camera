#ifndef GLOBAL_X_USB_PTP_TRANSPORT_H
#define GLOBAL_X_USB_PTP_TRANSPORT_H

#include <stdint.h>

/* All callbacks can execute in USB interrupt context. They must only move
 * bounded data / update flags; do not read SD, encode PNG, or wait in them.
 * RX memory is stable until receive_enable(), including after callback return.
 * reset also reports disconnect/deconfiguration and invalidates pending TX/RX.
 */
typedef struct {
    void (*rx)(const uint8_t *data, uint32_t length);
    void (*tx_done)(void);
    void (*reset)(void);
    void (*cancel)(uint32_t transaction_id);
    void (*device_reset)(void);
    uint16_t (*get_status)(void); /* PTP response code; NULL => 0x2001 (OK). */
} usb_ptp_callbacks;

typedef struct {
    volatile uint32_t init_stage, init_error;
    volatile uint32_t polls, interrupts, setups, resets, suspends, resumes;
    volatile uint32_t configurations, rx_packets, rx_bytes, tx_completions;
    volatile uint32_t cancels, device_resets, status_requests, stalls;
    volatile uint32_t speed, configured, last_setup, last_setup_value;
    volatile uint32_t last_setup_index_length;
    volatile uint32_t gintsts, gintmsk, gusbcfg, gccfg, dctl, dsts;
    volatile uint32_t pwr_svmcr3, rcc_ccipr6, phy_cr;
} usb_ptp_stats;

extern usb_ptp_stats usb_ptp_debug;

/* Requires existing HAL tick, enabled interrupts if tick depends on SysTick,
 * HCLK >= 30MHz, intact 48MHz board HSE and powered USB1 rails. No PLL/system
 * clock, GPIO, SD, camera, NOR or HOLD configuration is changed.
 * Returns 0 on success; nonzero init_error/init_stage explains a failure.
 */
int usb_ptp_transport_init(const usb_ptp_callbacks *callbacks);
void usb_ptp_transport_stop(void);
void usb_ptp_transport_poll(void);
int usb_ptp_configured(void);
uint16_t usb_ptp_bulk_max_packet(void);
/* Arms exactly one packet. Returns 0 on success, 1 if already armed/not ready. */
int usb_ptp_receive_enable(void);
/* Buffer remains owned by USB until tx_busy()==0 / tx_done(). Max 65535 bytes.
 * Every intermediate chunk must be a multiple of bulk_max_packet(). Set end
 * only for the final chunk of one PTP USB transfer/container. It adds a ZLP
 * when needed so a following PTP response cannot be mistaken for image data.
 * TX data is read using 32-bit FIFO loads: allocate/pad through the next word.
 */
int usb_ptp_transmit(const void *data, uint32_t length, int end_transfer);
int usb_ptp_tx_busy(void);
/* Event is copied internally (max24bytes), then sent on interrupt IN. */
int usb_ptp_send_event(const void *data, uint32_t length);
/* Main-loop host-cancel cleanup. Stops/flushes bulk IN, preserving DATA PID
 * toggles, endpoint activation and any pending OUT packet. Returns 0 only
 * after success; then the caller may return to idle/rearm OUT. No callbacks.
 * Host cancel completes through GetDeviceStatus, not a bulk response. */
int usb_ptp_cancel_transfer(void);
/* Convenience wrapper for reset/error cleanup; rearms OUT only on success. */
void usb_ptp_abort_bulk(void);
void USB1_OTG_HS_IRQHandler(void);

#endif
