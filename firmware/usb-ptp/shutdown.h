#ifndef USB_PTP_SHUTDOWN_H
#define USB_PTP_SHUTDOWN_H
#include <stdint.h>

/* Call only from privileged secure Thread mode, after the physical VBUS
 * monitor has confirmed absence and the PTP operation has unwound. These are
 * caller attestations, not conclusions inferred from a USB reset/suspend or
 * the RCC clock bits. SD_DEINITIALIZED means sd_deinit returned SD_OK with
 * media_idle=1, initialized/controller_owned/timer_owned=0 and no cleanup
 * error. USB_STOPPED means ptp_stop completed, with no further callbacks.
 * This routine does not wait for, abort, reset, or retry an active SD command.
 */
#define USB_SHUTDOWN_VBUS_ABSENT       (1U << 0)
#define USB_SHUTDOWN_PTP_QUIESCENT     (1U << 1)
#define USB_SHUTDOWN_SD_DEINITIALIZED (1U << 2)
#define USB_SHUTDOWN_USB_STOPPED       (1U << 3)
#define USB_SHUTDOWN_REQUIRED         15U
#define USB_SHUTDOWN_MAGIC            0x31534455U /* UDS1 */
#define USB_SHUTDOWN_SEAL             0x44455355U /* USED: snapshot published */
#define USB_SHUTDOWN_SCHEMA           2U /* schema 1: PD7; schema 2: PA2/A3 */

enum usb_shutdown_state {
    USB_SHUTDOWN_BEGIN=1, USB_SHUTDOWN_PERIPHERALS_OFF=2,
    USB_SHUTDOWN_ARMED=3, USB_SHUTDOWN_REFUSED=4, USB_SHUTDOWN_RETURNED=5
};
enum usb_shutdown_error {
    USB_SHUTDOWN_OK=0, USB_SHUTDOWN_BAD_PREREQUISITES=1,
    USB_SHUTDOWN_BAD_CONTEXT=2, USB_SHUTDOWN_BAD_CLOCKS=3,
    USB_SHUTDOWN_HOLD_UNAVAILABLE=4, USB_SHUTDOWN_STORAGE_ACTIVE=5,
    USB_SHUTDOWN_OTHER_CLIENT_ACTIVE=6, USB_SHUTDOWN_PIN_READBACK=7,
    USB_SHUTDOWN_PERIPHERAL_READBACK=8, USB_SHUTDOWN_DEBUG_UNAVAILABLE=9,
    USB_SHUTDOWN_DEBUG_EMULATION=10, USB_SHUTDOWN_OTP_UNKNOWN=11,
    USB_SHUTDOWN_RESET_OPTION=12, USB_SHUTDOWN_HARDWARE_WATCHDOG=13,
    USB_SHUTDOWN_PENDING_SOURCE=14, USB_SHUTDOWN_MODE_READBACK=15,
    USB_SHUTDOWN_UNEXPECTED_RETURN=16
};

typedef struct {
    uint32_t magic, schema, words, state, error, prerequisites;
    uint32_t trial_entry_proven; /* Always zero: pre-WFI data is NOT entry proof. */
    uint32_t hold_verified, ccr, control, ipsr, faultmask, fpccr;
    uint32_t ahb4enr, ahb4rstr, ahb5enr_before, ahb5enr_after;
    uint32_t apb4enr2, dbg_cr_before, dbg_cr_after;
    uint32_t otp_shadowed, otp_valid, otp_value;
    uint32_t cpucr_before, cpucr_after, cr4_after, scr_after;
    uint32_t exti_pending, nvic_enabled, nvic_pending, systick_ctrl;
    uint32_t wkup_enable, wkup_status, stopcr, svmcr3_after;
    uint32_t hold_moder, hold_pupdr, hold_odr, hold_idr;
    uint32_t checksum, seal;
} usb_shutdown_proof_t;
extern volatile usb_shutdown_proof_t usb_shutdown_proof;

/* Never returns: guarded Standby, or an awake diagnostic park with HOLD high
 * on refusal/unexpected WFI return. Normal UART recovery requires NRST/cold
 * restart; neither UART wake nor USB reattach wake is configured. No reset,
 * NOR deep-power-down, OTP operation, or RTC/backup-domain write is issued.
 * USB-specific entry, power/current and AUX rail sequencing remain unqualified
 * until separately measured. SRAM records may disappear upon real Standby.
 */
void usb_shutdown_enter(uint32_t prerequisites) __attribute__((noreturn));
#endif
