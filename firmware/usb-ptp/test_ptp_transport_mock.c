/* Native test adapter only. No USB device or hardware access. */
#include "transport/usb_ptp_transport.h"
#include "ptp.h"
#include <string.h>

static usb_ptp_callbacks callbacks;
static uint8_t captured[PHOTO_STORE_PNG_BYTES+65536U], events[4096];
static uint32_t captured_size,event_size,transmits,last_size,ticks,cancel_at,cancel_id;
static int configured,aborts,armed;
static uint32_t abort_failures,block_at,reset_at,busy;
static const uint8_t *owned;static uint32_t owned_size;
static uint8_t owned_copy[16384];
usb_ptp_stats usb_ptp_debug;
uint32_t HAL_GetTick(void){return ticks++;}
int usb_ptp_transport_init(const usb_ptp_callbacks *cb){callbacks=*cb;configured=1;abort_failures=block_at=reset_at=busy=owned_size=0;owned=0;return 0;}
void usb_ptp_transport_stop(void){configured=0;busy=owned_size=0;owned=0;}
void usb_ptp_transport_poll(void){}
int usb_ptp_configured(void){return configured;}
uint16_t usb_ptp_bulk_max_packet(void){return 512;}
int usb_ptp_receive_enable(void){armed++;return 0;}
int usb_ptp_tx_busy(void){return busy;}
int usb_ptp_transmit(const void *data,uint32_t len,int end){
 (void)end;
 if(busy||len>sizeof captured-captured_size)return 1;
 memcpy(captured+captured_size,data,len);captured_size+=len;last_size=len;transmits++;
 if(block_at&&transmits==block_at){if(len>sizeof owned_copy)return 1;busy=1;owned=data;owned_size=len;memcpy(owned_copy,data,len);}
 if(cancel_at&&transmits==cancel_at&&callbacks.cancel)callbacks.cancel(cancel_id);
 if(reset_at&&transmits==reset_at&&callbacks.reset)callbacks.reset();
 return 0;
}
int usb_ptp_send_event(const void *data,uint32_t len){
 if(len>sizeof events-event_size)return 1;
 memcpy(events+event_size,data,len);event_size+=len;return 0;
}
void usb_ptp_abort_bulk(void){if(!usb_ptp_cancel_transfer())usb_ptp_receive_enable();}
int usb_ptp_cancel_transfer(void){aborts++;if(abort_failures){abort_failures--;return 1;}busy=owned_size=0;owned=0;return 0;}
void USB1_OTG_HS_IRQHandler(void){}
void mock_clear(void){captured_size=event_size=transmits=last_size=cancel_at=0;abort_failures=block_at=reset_at=busy=owned_size=0;owned=0;aborts=armed=0;}
void mock_feed(const uint8_t *p,uint32_t n){callbacks.rx(p,n);ptp_poll();}
void mock_queue(const uint8_t *p,uint32_t n){callbacks.rx(p,n);}
void mock_cancel(uint32_t tid){callbacks.cancel(tid);}
void mock_cancel_on_tx(uint32_t nth,uint32_t tid){cancel_at=nth;cancel_id=tid;}
void mock_usb_reset(void){callbacks.reset();ptp_poll();}
const uint8_t *mock_data(void){return captured;}
uint32_t mock_size(void){return captured_size;}
uint32_t mock_last_size(void){return last_size;}
const uint8_t *mock_events(void){return events;}
uint32_t mock_event_size(void){return event_size;}
int mock_aborts(void){return aborts;}

uint16_t mock_status(void){return callbacks.get_status();}
void mock_abort_failures(uint32_t n){abort_failures=n;}
void mock_block_on_tx(uint32_t n){block_at=n;}
void mock_reset_on_tx(uint32_t n){reset_at=n;}
int mock_owned_unchanged(void){return owned&&owned_size&&!memcmp(owned,owned_copy,owned_size);}
void mock_physical_disconnect(void){configured=0;busy=owned_size=0;owned=0;callbacks.reset();ptp_poll();}
void mock_reconnect(void){configured=1;}
