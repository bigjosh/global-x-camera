"""Exercise the actual endpoint/control class and pinned USB core on the host.

Only the hardware-specific tail beginning at hardware_prepare is omitted.
Cancellation register cleanup itself is exercised against a recording HAL stub.
The LL endpoints are replaced with recording stubs; no instrument is opened.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
MOCK_HAL=r'''
#ifndef MOCK_STM32_H
#define MOCK_STM32_H
#include <stdint.h>
#include <stddef.h>
#define __IO volatile
#define __STATIC_INLINE static inline
#define __PACKED __attribute__((packed))
#define UNUSED(x) (void)(x)
typedef enum {HAL_OK=0,HAL_ERROR=1,HAL_BUSY=2} HAL_StatusTypeDef;
typedef struct {uint8_t *xfer_buff;uint32_t xfer_len,xfer_count;} MockEndpoint;
typedef struct {void *Instance;MockEndpoint IN_ep[3];} PCD_HandleTypeDef;
typedef struct {uint32_t DIEPEMPMSK;} USB_OTG_DeviceTypeDef;
typedef struct {uint32_t DIEPINT;} USB_OTG_INEndpointTypeDef;
#define USB_OTG_DEVICE_BASE 0x800U
#define USB_OTG_IN_ENDPOINT_BASE 0x900U
#define USB_OTG_EP_REG_SIZE 0x20U
#define USB_OTG_DIEPINT_XFRC 1U
#define USB_OTG_DIEPINT_EPDISD 2U
#define USB_OTG_DIEPINT_TOC 8U
#define USB_OTG_DIEPINT_INEPNE 64U
HAL_StatusTypeDef HAL_PCD_EP_Abort(PCD_HandleTypeDef*,uint8_t);
HAL_StatusTypeDef USB_FlushTxFifo(void*,uint32_t);
static inline void __DSB(void){}
static inline uint32_t __get_PRIMASK(void){return 0;}
static inline void __disable_irq(void){}
static inline void __set_PRIMASK(uint32_t x){(void)x;}
#endif
'''
HARNESS=r'''
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include "class_actual.c"
static unsigned tx_count, stall_count, open_count, reset_count, done_count;
static unsigned received_count, cancel_count, reset_req_count, abort_count, close_count;
static int abort_result,flush_result;
static unsigned in_pid=1,out_pid=1,flush_count;
static uint32_t mock_mmio[1024];
HAL_StatusTypeDef HAL_PCD_EP_Abort(PCD_HandleTypeDef*h,uint8_t ep){assert(h==&pcd && ep==0x81);abort_count++;return abort_result?HAL_ERROR:HAL_OK;}
HAL_StatusTypeDef USB_FlushTxFifo(void*instance,uint32_t fifo){assert(instance==mock_mmio && fifo==1);flush_count++;return flush_result?HAL_ERROR:HAL_OK;}
static uint32_t cancel_tid, rx_count[16], recv_size[16];
static uint8_t *recv_ptr[16];
static struct {uint8_t ep;uint32_t len;uint8_t data[64];} transactions[128];
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef*d){(void)d;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef*d){(void)d;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef*d){(void)d;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef*d){(void)d;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef*d,uint8_t a,uint8_t t,uint16_t m){(void)d;(void)t;(void)m;open_count++;if(a==0x81)in_pid=0;if(a==1)out_pid=0;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;close_count++;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;stall_count++;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;return USBD_OK;}
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;return 0;}
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef*d,uint8_t a){(void)d;(void)a;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef*d,uint8_t a,uint8_t*b,uint32_t n){
 (void)d;assert(tx_count<128);transactions[tx_count].ep=a;transactions[tx_count].len=n;
 if(n)memcpy(transactions[tx_count].data,b,n<64?n:64);tx_count++;return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef*d,uint8_t a,uint8_t*b,uint32_t n){
 (void)d;recv_ptr[a&15]=b;recv_size[a&15]=n;return USBD_OK;
}
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef*d,uint8_t a){(void)d;return rx_count[a&15];}
void USBD_LL_Delay(uint32_t n){(void)n;}
static void on_reset(void){reset_count++;}
static void on_done(void){done_count++;}
static void on_rx(const uint8_t*b,uint32_t n){assert(b==rx_buffer);assert(n==17);received_count++;}
static void on_cancel(uint32_t n){cancel_count++;cancel_tid=n;}
static void on_device_reset(void){reset_req_count++;}
static uint16_t status(void){return 0x2019;}
static void setup(uint8_t type,uint8_t request,uint16_t value,uint16_t index,uint16_t len){
 uint8_t s[8]={type,request,value,value>>8,index,index>>8,len,len>>8};
 (void)USBD_LL_SetupStage(&dev,s);
}
static void init(int hs){
 memset(&dev,0,sizeof dev);memset(&cb,0,sizeof cb);memset(mock_mmio,0,sizeof mock_mmio);pcd.Instance=mock_mmio;running=1;
 cb.reset=on_reset;cb.tx_done=on_done;cb.rx=on_rx;cb.cancel=on_cancel;
 cb.device_reset=on_device_reset;cb.get_status=status;
 assert(USBD_Init(&dev,&descriptors,0)==USBD_OK);
 assert(USBD_RegisterClass(&dev,&ptp_class)==USBD_OK);
 USBD_LL_SetSpeed(&dev,hs?USBD_SPEED_HIGH:USBD_SPEED_FULL);USBD_LL_Reset(&dev);
 setup(0,5,7,0,0);assert(dev.dev_state==USBD_STATE_ADDRESSED);
 setup(0,9,1,0,0);assert(dev.dev_state==USBD_STATE_CONFIGURED);
 assert(rx_armed);assert(recv_size[1]==(hs?512:64));assert(usb_ptp_configured());
 tx_count=0;stall_count=0;
}
static void descriptors_test(void){
 init(1);uint16_t n;uint8_t*b=get_hs(&n);assert(n==39 && b[2]==39);
 assert(b[14]==6 && b[15]==1 && b[16]==1);
 assert(b[20]==0x81 && b[27]==1 && b[34]==0x82);
 assert(b[22]==0 && b[23]==2);assert(b[29]==0 && b[30]==2);
 b=get_fs(&n);assert(b[22]==64 && b[23]==0);
 b=get_other(&n);assert(b[1]==7 && b[22]==64 && b[23]==0);
 dev.dev_speed=USBD_SPEED_FULL;b=get_other(&n);assert(b[1]==7 && b[23]==2);
 b=get_serial(USBD_SPEED_FULL,&n);assert(n==b[0] && b[1]==3 && !(n&1));
 setup(0x80,6,0x100,0,18);assert(transactions[0].len==18 && transactions[0].data[0]==18);
}
static void zlp_test(int hs){
 init(hs);uint8_t payload[1028]={0};unsigned m=usb_ptp_bulk_max_packet();
 assert(!usb_ptp_transmit(payload,m,1));assert(tx_active && tx_zlp);
 assert(usb_ptp_transmit(payload,12,1));assert(tx_count==1 && transactions[0].len==m);
 USBD_LL_DataInStage(&dev,1,NULL);assert(tx_active && !tx_zlp && !done_count);
 assert(tx_count==2 && transactions[1].len==0);
 USBD_LL_DataInStage(&dev,1,NULL);assert(!tx_active && done_count==1);
 assert(!usb_ptp_transmit(payload,m,0));USBD_LL_DataInStage(&dev,1,NULL);
 assert(!tx_active && done_count==2 && tx_count==3);
 assert(!usb_ptp_transmit(payload,m+1,1));USBD_LL_DataInStage(&dev,1,NULL);
 assert(!tx_active && done_count==3 && tx_count==4);
 assert(usb_ptp_transmit(payload,12,0));assert(usb_ptp_transmit(payload,65536,1));
 assert(!usb_ptp_transmit(NULL,0,1));USBD_LL_DataInStage(&dev,1,NULL);
 assert(done_count==4 && tx_count==5);
}
static void cancel_test(void){
 init(1);setup(0x21,0x64,0,0,6);assert(cancel_pending && recv_size[0]==6);
 uint8_t p[6]={1,0x40,0x78,0x56,0x34,0x12};memcpy(recv_ptr[0],p,6);rx_count[0]=6;
 USBD_LL_DataOutStage(&dev,0,recv_ptr[0]);assert(cancel_count==1 && cancel_tid==0x12345678);
 assert(!cancel_pending && transactions[tx_count-1].len==0);
 setup(0x21,0x64,0,1,6);assert(stall_count==2 && cancel_count==1);
 setup(0x21,0x64,0,0,5);assert(stall_count==4);
 setup(0x21,0x64,1,0,6);assert(stall_count==6);
 setup(0x21,0x66,0,0,0);assert(reset_req_count==1);
 setup(0x21,0x66,0,0,1);assert(reset_req_count==1 && stall_count==8);
}
static void status_test(void){
 init(1);setup(0xA1,0x67,0,0,64);assert(tx_count==1 && transactions[0].len==4);
 assert(transactions[0].data[0]==4 && transactions[0].data[1]==0);
 assert(transactions[0].data[2]==0x19 && transactions[0].data[3]==0x20);
 setup(0xA1,0x67,0,0,3);assert(stall_count==2);
 setup(0x81,10,0,0,1);assert(transactions[tx_count-1].len==1 && transactions[tx_count-1].data[0]==0);
 setup(0x01,11,1,0,0);assert(stall_count==4);
 setup(0xA1,0x65,0,0,64);assert(stall_count==6);
}
static void rx_test(void){
 init(1);assert(usb_ptp_receive_enable());rx_count[1]=17;memset(rx_buffer,0xAC,17);
 USBD_LL_DataOutStage(&dev,1,rx_buffer);assert(received_count==1 && !rx_armed);
 assert(rx_buffer[16]==0xAC);assert(!usb_ptp_receive_enable() && rx_armed);
 uint8_t p[24]={0};assert(!usb_ptp_send_event(p,24));assert(event_active);
 assert(usb_ptp_send_event(p,12));USBD_LL_DataInStage(&dev,2,NULL);assert(!event_active);
 assert(usb_ptp_send_event(p,25));assert(usb_ptp_send_event(p,11));
}
static void cancel_transfer_test(void){
 init(1);uint8_t payload[512]={0};assert(!usb_ptp_transmit(payload,512,1));
 unsigned opens=open_count,closes=close_count;in_pid=out_pid=1;
 USB_OTG_DeviceTypeDef*d=(USB_OTG_DeviceTypeDef*)((uint8_t*)mock_mmio+USB_OTG_DEVICE_BASE);
 USB_OTG_INEndpointTypeDef*ep=(USB_OTG_INEndpointTypeDef*)((uint8_t*)mock_mmio+USB_OTG_IN_ENDPOINT_BASE+USB_OTG_EP_REG_SIZE);
 d->DIEPEMPMSK=7;pcd.IN_ep[1].xfer_buff=payload;pcd.IN_ep[1].xfer_len=512;
 abort_result=1;assert(usb_ptp_cancel_transfer());assert(tx_active && tx_zlp && rx_armed);
 assert(d->DIEPEMPMSK==5 && flush_count==0 && pcd.IN_ep[1].xfer_buff==payload);
 abort_result=0;flush_result=1;assert(usb_ptp_cancel_transfer());assert(tx_active && pcd.IN_ep[1].xfer_buff==payload);
 flush_result=0;assert(!usb_ptp_cancel_transfer());assert(!tx_active && !tx_zlp && rx_armed);
 assert(!pcd.IN_ep[1].xfer_buff && !pcd.IN_ep[1].xfer_len && ep->DIEPINT==75);
 assert(in_pid==1 && out_pid==1 && open_count==opens && close_count==closes);
 assert(abort_count==3 && flush_count==2 && done_count==0);
 /* A delayed old completion must not finish a future caller's transfer. */
 USBD_LL_DataInStage(&dev,1,NULL);assert(done_count==0 && !tx_active);
 assert(!usb_ptp_transmit(payload,12,1));USBD_LL_DataInStage(&dev,1,NULL);
 assert(done_count==1 && !tx_active);
}
static void reset_test(void){
 init(1);uint8_t p[512]={0};assert(!usb_ptp_transmit(p,512,1));
 usb_ptp_abort_bulk();assert(!tx_active && rx_armed && usb_ptp_configured());
 assert(!usb_ptp_transmit(p,512,1));setup(0,9,0,0,0);
 assert(!usb_ptp_configured() && !rx_armed && !tx_active && !event_active);
 assert(usb_ptp_transmit(p,512,1));assert(usb_ptp_receive_enable());
 setup(0,9,1,0,0);assert(usb_ptp_configured() && rx_armed);
 USBD_LL_Reset(&dev);assert(!usb_ptp_configured() && !tx_active && reset_count>=3);
}
int main(int argc,char**argv){
 assert(argc==2);
 if(!strcmp(argv[1],"descriptors"))descriptors_test();
 else if(!strcmp(argv[1],"hs_zlp"))zlp_test(1);
 else if(!strcmp(argv[1],"fs_zlp"))zlp_test(0);
 else if(!strcmp(argv[1],"cancel"))cancel_test();
 else if(!strcmp(argv[1],"status"))status_test();
 else if(!strcmp(argv[1],"rx"))rx_test();
 else if(!strcmp(argv[1],"reset"))reset_test();
 else if(!strcmp(argv[1],"cancel_transfer"))cancel_transfer_test();
 else return 2;
 puts("PASS");return 0;
}
'''

class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='gx-usb-transport-')
        cls.out=Path(cls.temp.name)
        source=(HERE/'usb_ptp_transport.c').read_text()
        boundary='static int hardware_prepare(void)'
        assert source.count(boundary)==1
        (cls.out/'class_actual.c').write_text(source.split(boundary)[0])
        for name in ('stm32n6xx.h','stm32n6xx_hal.h'):
            (cls.out/name).write_text(MOCK_HAL)
        for name in ('stm32n6xx_hal_rif.h','stm32n6xx_ll_rcc.h'):
            (cls.out/name).write_text('')
        (cls.out/'harness.c').write_text(HARNESS)
        compiler=shutil.which('clang') or shutil.which('gcc')
        if not compiler:raise RuntimeError('Host clang/gcc required')
        cls.exe=cls.out/'transport_test.exe'
        core=HERE/'vendor/st-usbd/Core'
        subprocess.run([compiler,'-std=c11','-Wall','-Wextra','-Werror',
                        '-Wno-unused-function','-Wno-unused-variable','-DUSE_USB_HS',
                        '-I'+str(cls.out),'-I'+str(HERE),'-I'+str(core/'Inc'),
                        str(cls.out/'harness.c'),*[str(x) for x in sorted((core/'Src').glob('*.c'))],
                        '-o',str(cls.exe)],check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def check_case(self,name):
        result=subprocess.run([str(self.exe),name],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS',result.stdout)

    def test_descriptors(self):self.check_case('descriptors')
    def test_high_speed_transfer_boundaries(self):self.check_case('hs_zlp')
    def test_full_speed_transfer_boundaries(self):self.check_case('fs_zlp')
    def test_cancel_reset_requests(self):self.check_case('cancel')
    def test_device_status_and_invalid_requests(self):self.check_case('status')
    def test_receive_backpressure_and_events(self):self.check_case('rx')
    def test_deconfigure_and_recovery(self):self.check_case('reset')
    def test_cancel_preserves_toggles_and_ignores_old_completion(self):self.check_case('cancel_transfer')
    def test_vendor_files_unchanged(self):
        import build_sources
        self.assertEqual(build_sources.verify_vendor(),'2df324bd60d4b0bb27404fd70b1c089b467f0e09')

if __name__=='__main__':unittest.main()
