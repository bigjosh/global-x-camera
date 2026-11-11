/* Global-X prototype USB Still Image transport. PTP operations live above this
 * layer. Chapter9 control handling is the pinned, unmodified ST Device core.
 * The Nucleo USB1 PHY preparation follows the original ST camera smoke demo.
 */
#include "usb_ptp_transport.h"
#include "usbd_core.h"
#include "usbd_ctlreq.h"
#include "usbd_ioreq.h"
#include "stm32n6xx_hal_rif.h"
#include "stm32n6xx_ll_rcc.h"

#ifndef USB_PTP_USE_IRQ
#define USB_PTP_USE_IRQ 1
#endif
#ifndef USB_PTP_FORCE_FS
#define USB_PTP_FORCE_FS 0
#endif
/* Development-only identifiers on the ST evaluation board. Replace with an
 * allocated product identity before distribution. Kept configurable to avoid
 * changing the protocol implementation when an identity is assigned. */
#ifndef USB_PTP_VID
#define USB_PTP_VID 0x0483
#endif
#ifndef USB_PTP_PID
#define USB_PTP_PID 0x572A
#endif

#define EP_BULK_OUT 0x01U
#define EP_BULK_IN  0x81U
#define EP_EVENT_IN 0x82U
#define EVENT_MAX 24U
#define CFG_SIZE 39U
#define HS_MPS 512U
#define FS_MPS 64U

static PCD_HandleTypeDef pcd;
static USBD_HandleTypeDef dev;
static usb_ptp_callbacks cb;
usb_ptp_stats usb_ptp_debug;
static volatile uint8_t running, rx_armed, tx_active, tx_zlp, event_active;
static uint8_t cancel_pending;
static uint8_t rx_buffer[HS_MPS] __attribute__((aligned(4)));
static uint8_t event_buffer[EVENT_MAX] __attribute__((aligned(4)));
static uint8_t control_buffer[8] __attribute__((aligned(4)));
static uint8_t string_buffer[128] __attribute__((aligned(4)));
static uint8_t other_speed[CFG_SIZE] __attribute__((aligned(4)));

static uint8_t device_descriptor[18] __attribute__((aligned(4))) = {
    18,1,0,2,0,0,0,64,
    (USB_PTP_VID & 255), (USB_PTP_VID >> 8),
    (USB_PTP_PID & 255), (USB_PTP_PID >> 8),
    0,1,1,2,3,1
};
static uint8_t qualifier[10] __attribute__((aligned(4))) = {
    10,6,0,2,0,0,0,64,1,0
};
/* Three endpoints, one standard Still Image interface (6/1/1). The separate
 * JS/battery supply makes this prototype self-powered; up to500mA is declared
 * for its supported USB-powered configuration. No remote-wakeup capability. */
static uint8_t hs_config[CFG_SIZE] __attribute__((aligned(4))) = {
    9,2,CFG_SIZE,0,1,1,4,0xC0,250,
    9,4,0,0,3,6,1,1,5,
    7,5,EP_BULK_IN,2,0,2,0,
    7,5,EP_BULK_OUT,2,0,2,0,
    7,5,EP_EVENT_IN,3,EVENT_MAX,0,6
};
static uint8_t fs_config[CFG_SIZE] __attribute__((aligned(4))) = {
    9,2,CFG_SIZE,0,1,1,4,0xC0,250,
    9,4,0,0,3,6,1,1,5,
    7,5,EP_BULK_IN,2,64,0,0,
    7,5,EP_BULK_OUT,2,64,0,0,
    7,5,EP_EVENT_IN,3,EVENT_MAX,0,16
};
static uint8_t lang_id[4] __attribute__((aligned(4))) = {4,3,9,4};

static uint32_t lock(void) { uint32_t x=__get_PRIMASK(); __disable_irq(); return x; }
static void unlock(uint32_t x) { __set_PRIMASK(x); }
static USBD_StatusTypeDef convert(HAL_StatusTypeDef x) {
    return x==HAL_OK ? USBD_OK : (x==HAL_BUSY ? USBD_BUSY : USBD_FAIL);
}
static uint8_t *str(const char *s, uint16_t *n) {
    uint16_t i=2;
    while (*s && (uint32_t)i+2U<=sizeof string_buffer) {
        string_buffer[i++]=(uint8_t)*s++; string_buffer[i++]=0;
    }
    string_buffer[0]=(uint8_t)i; string_buffer[1]=3; *n=i;
    return string_buffer;
}
static uint8_t *get_dev(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;*n=sizeof device_descriptor;return device_descriptor;}
static uint8_t *get_lang(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;*n=sizeof lang_id;return lang_id;}
static uint8_t *get_mfg(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;return str("Global-X prototype",n);}
static uint8_t *get_prod(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;return str("Global-X Camera",n);}
/* Stable for this one development board. Do not invent changing serials per
 * boot: Windows associates persistent object/cache state with this identity. */
static uint8_t *get_serial(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;return str("GX-N657-PROTOTYPE-01",n);}
static uint8_t *get_cfg(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;return str("Photo transfer",n);}
static uint8_t *get_if(USBD_SpeedTypeDef s,uint16_t*n) {(void)s;return str("PTP Still Image",n);}
static uint8_t *get_hs(uint16_t*n) {*n=CFG_SIZE;return hs_config;}
static uint8_t *get_fs(uint16_t*n) {*n=CFG_SIZE;return fs_config;}
static uint8_t *get_other(uint16_t*n) {
    memcpy(other_speed,dev.dev_speed==USBD_SPEED_HIGH?fs_config:hs_config,CFG_SIZE);
    other_speed[1]=USB_DESC_TYPE_OTHER_SPEED_CONFIGURATION;*n=CFG_SIZE;return other_speed;
}
static uint8_t *get_qual(uint16_t*n) {*n=sizeof qualifier;return qualifier;}
static USBD_DescriptorsTypeDef descriptors={
    get_dev,get_lang,get_mfg,get_prod,get_serial,get_cfg,get_if
};

int usb_ptp_configured(void) {return running && dev.dev_state==USBD_STATE_CONFIGURED;}
uint16_t usb_ptp_bulk_max_packet(void) {return dev.dev_speed==USBD_SPEED_HIGH?HS_MPS:FS_MPS;}
int usb_ptp_tx_busy(void) {return tx_active;}
int usb_ptp_receive_enable(void) {
    uint32_t irq=lock();
    if(!usb_ptp_configured() || rx_armed) {unlock(irq);return 1;}
    rx_armed=1;
    USBD_StatusTypeDef result=USBD_LL_PrepareReceive(&dev,EP_BULK_OUT,rx_buffer,usb_ptp_bulk_max_packet());
    if(result!=USBD_OK)rx_armed=0;
    unlock(irq);return result==USBD_OK?0:1;
}
int usb_ptp_transmit(const void *data,uint32_t length,int end_transfer) {
    uint32_t irq=lock();
    uint16_t mps=usb_ptp_bulk_max_packet();
    if(!usb_ptp_configured() || tx_active || length>65535U || (!data && length) ||
       (!end_transfer && (!length || length%mps))) {unlock(irq);return 1;}
    tx_active=1;tx_zlp=(end_transfer && length && !(length%mps))?1:0;
    USBD_StatusTypeDef result=USBD_LL_Transmit(&dev,EP_BULK_IN,(uint8_t *)data,length);
    if(result!=USBD_OK)tx_active=tx_zlp=0;
    unlock(irq);return result==USBD_OK?0:1;
}
int usb_ptp_send_event(const void *data,uint32_t length) {
    uint32_t irq=lock();
    if(!usb_ptp_configured() || event_active || !data || length<12 || length>EVENT_MAX) {unlock(irq);return 1;}
    memcpy(event_buffer,data,length);event_active=1;
    USBD_StatusTypeDef result=USBD_LL_Transmit(&dev,EP_EVENT_IN,event_buffer,length);
    if(result!=USBD_OK)event_active=0;
    unlock(irq);return result==USBD_OK?0:1;
}
static int cancel_in_transfer(void);
int usb_ptp_cancel_transfer(void) {
    uint32_t irq=lock();
    if(!usb_ptp_configured()){unlock(irq);return 1;}
    /* Host cancellation does not include ClearFeature(ENDPOINT_HALT).
     * Close/open would force DATA0 and desynchronize the host's pipe. Stop
     * the transfer only; preserve both endpoints and their current toggles. */
    if(cancel_in_transfer()){unlock(irq);return 1;}
    tx_active=tx_zlp=0;
    unlock(irq);return 0;
}
void usb_ptp_abort_bulk(void) {
    if(!usb_ptp_cancel_transfer())(void)usb_ptp_receive_enable();
}

static uint8_t class_init(USBD_HandleTypeDef*d,uint8_t cfg) {
    (void)cfg; uint16_t mps=usb_ptp_bulk_max_packet();
    if(USBD_LL_OpenEP(d,EP_BULK_IN,USBD_EP_TYPE_BULK,mps)!=USBD_OK ||
       USBD_LL_OpenEP(d,EP_BULK_OUT,USBD_EP_TYPE_BULK,mps)!=USBD_OK ||
       USBD_LL_OpenEP(d,EP_EVENT_IN,USBD_EP_TYPE_INTR,EVENT_MAX)!=USBD_OK)return USBD_FAIL;
    d->ep_in[1].is_used=1;d->ep_out[1].is_used=1;d->ep_in[2].is_used=1;
    tx_active=tx_zlp=event_active=rx_armed=cancel_pending=0;
    usb_ptp_debug.configurations++;usb_ptp_debug.configured=1;
    /* The core sets CONFIGURED only after Init returns, so arm directly here. */
    rx_armed=1;
    if(USBD_LL_PrepareReceive(d,EP_BULK_OUT,rx_buffer,mps)!=USBD_OK){rx_armed=0;return USBD_FAIL;}
    return USBD_OK;
}
static uint8_t class_deinit(USBD_HandleTypeDef*d,uint8_t cfg) {
    (void)cfg;
    (void)USBD_LL_CloseEP(d,EP_BULK_IN);(void)USBD_LL_CloseEP(d,EP_BULK_OUT);(void)USBD_LL_CloseEP(d,EP_EVENT_IN);
    d->ep_in[1].is_used=0;d->ep_out[1].is_used=0;d->ep_in[2].is_used=0;
    tx_active=tx_zlp=event_active=rx_armed=cancel_pending=0;usb_ptp_debug.configured=0;
    if(cb.reset)cb.reset();
    return USBD_OK;
}
static uint8_t bad_setup(USBD_HandleTypeDef*d,USBD_SetupReqTypedef*r) {
    usb_ptp_debug.stalls++;USBD_CtlError(d,r);return USBD_FAIL;
}
static uint8_t class_setup(USBD_HandleTypeDef*d,USBD_SetupReqTypedef*r) {
    cancel_pending=0;
    if(r->bmRequest==0x02 && r->bRequest==USB_REQ_CLEAR_FEATURE &&
       r->wValue==USB_FEATURE_EP_HALT && !r->wLength) {
        /* Standard core already clears STALL, resets DATA0 and ACKs EP0. */
        if(r->wIndex==EP_BULK_IN){tx_active=tx_zlp=0;}
        else if(r->wIndex==EP_BULK_OUT){rx_armed=0;(void)usb_ptp_receive_enable();}
        else if(r->wIndex==EP_EVENT_IN){event_active=0;}
        return USBD_OK;
    }
    if(r->wIndex!=0 || r->wValue!=0)return bad_setup(d,r);
    if(r->bmRequest==0xA1) {
        if(r->bRequest==0x67 && r->wLength>=4) {
            uint16_t status=cb.get_status?cb.get_status():0x2001;
            control_buffer[0]=4;control_buffer[1]=0;
            control_buffer[2]=(uint8_t)status;control_buffer[3]=(uint8_t)(status>>8);
            usb_ptp_debug.status_requests++;
            return (uint8_t)USBD_CtlSendData(d,control_buffer,4);
        }
    } else if(r->bmRequest==0x21) {
        if(r->bRequest==0x64 && r->wLength==6) {
            cancel_pending=1;return (uint8_t)USBD_CtlPrepareRx(d,control_buffer,6);
        }
        if(r->bRequest==0x66 && !r->wLength) {
            usb_ptp_debug.device_resets++;if(cb.device_reset)cb.device_reset();
            return USBD_OK; /* Standard core sends the status-stage ACK. */
        }
    } else if(r->bmRequest==0x81 && r->bRequest==USB_REQ_GET_INTERFACE && r->wLength==1) {
        control_buffer[0]=0;return (uint8_t)USBD_CtlSendData(d,control_buffer,1);
    } else if(r->bmRequest==0x01 && r->bRequest==USB_REQ_SET_INTERFACE && !r->wLength) {
        return USBD_OK; /* only alternate setting0 */
    } else if(r->bmRequest==0x81 && r->bRequest==USB_REQ_GET_STATUS && r->wLength==2) {
        control_buffer[0]=control_buffer[1]=0;return (uint8_t)USBD_CtlSendData(d,control_buffer,2);
    }
    return bad_setup(d,r);
}
static uint8_t class_ep0_rx(USBD_HandleTypeDef*d) {
    if(cancel_pending) {
        cancel_pending=0;
        if(control_buffer[0]!=1 || control_buffer[1]!=0x40 || USBD_LL_GetRxDataSize(d,0)!=6)
            return bad_setup(d,&d->request);
        uint32_t tid=(uint32_t)control_buffer[2]|((uint32_t)control_buffer[3]<<8)|
                     ((uint32_t)control_buffer[4]<<16)|((uint32_t)control_buffer[5]<<24);
        usb_ptp_debug.cancels++;if(cb.cancel)cb.cancel(tid);
    }
    return USBD_OK;
}
static uint8_t class_data_in(USBD_HandleTypeDef*d,uint8_t ep) {
    if(ep==1) {
        if(!tx_active)return USBD_OK; /* ignore a canceled completion */
        if(tx_zlp){tx_zlp=0;return (uint8_t)USBD_LL_Transmit(d,EP_BULK_IN,NULL,0);}
        tx_active=0;usb_ptp_debug.tx_completions++;if(cb.tx_done)cb.tx_done();
    } else if(ep==2)event_active=0;
    return USBD_OK;
}
static uint8_t class_data_out(USBD_HandleTypeDef*d,uint8_t ep) {
    if(ep==1) {
        uint32_t n=USBD_LL_GetRxDataSize(d,EP_BULK_OUT);rx_armed=0;
        usb_ptp_debug.rx_packets++;usb_ptp_debug.rx_bytes+=n;
        if(cb.rx)cb.rx(rx_buffer,n);
    }
    return USBD_OK;
}
static USBD_ClassTypeDef ptp_class={
    .Init=class_init,.DeInit=class_deinit,.Setup=class_setup,.EP0_RxReady=class_ep0_rx,
    .DataIn=class_data_in,.DataOut=class_data_out,
    .GetHSConfigDescriptor=get_hs,.GetFSConfigDescriptor=get_fs,
    .GetOtherSpeedConfigDescriptor=get_other,.GetDeviceQualifierDescriptor=get_qual
};

/* Stop IN without reactivating the endpoint (which resets DATA0). OUT is
 * already packet bounded: no host-to-device data operations are implemented.
 * Its pending receive and the shared RX FIFO are therefore left intact, so
 * EP0 status polling is never flushed along with an interrupted image. */
static int cancel_in_transfer(void) {
    USB_OTG_DeviceTypeDef *d=(USB_OTG_DeviceTypeDef *)((uintptr_t)pcd.Instance+USB_OTG_DEVICE_BASE);
    USB_OTG_INEndpointTypeDef *ep=(USB_OTG_INEndpointTypeDef *)((uintptr_t)pcd.Instance+USB_OTG_IN_ENDPOINT_BASE+USB_OTG_EP_REG_SIZE);
    d->DIEPEMPMSK&=~(1U<<1); /* prevent old buffer from refilling FIFO */
    if(HAL_PCD_EP_Abort(&pcd,EP_BULK_IN)!=HAL_OK)return 1;
    if(USB_FlushTxFifo(pcd.Instance,1U)!=HAL_OK)return 1;
    ep->DIEPINT=USB_OTG_DIEPINT_XFRC|USB_OTG_DIEPINT_EPDISD|
                USB_OTG_DIEPINT_TOC|USB_OTG_DIEPINT_INEPNE;
    pcd.IN_ep[1].xfer_buff=NULL;pcd.IN_ep[1].xfer_len=0;pcd.IN_ep[1].xfer_count=0;
    dev.ep_in[1].total_length=0;__DSB();return 0;
}

static int hardware_prepare(void) {
    usb_ptp_debug.init_stage=1;
    __HAL_RCC_RIFSC_CLK_ENABLE();
    RIMC_MasterConfig_t master={0};master.MasterCID=RIF_CID_1;master.SecPriv=RIF_ATTRIBUTE_SEC|RIF_ATTRIBUTE_PRIV;
    HAL_RIF_RIMC_ConfigMasterAttributes(RIF_MASTER_INDEX_OTG1,&master);
    HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_OTG1HS,RIF_ATTRIBUTE_SEC|RIF_ATTRIBUTE_PRIV);
    __HAL_RCC_PWR_CLK_ENABLE();HAL_PWREx_EnableVddUSBVMEN();
    uint32_t start=HAL_GetTick();
    while(!__HAL_PWR_GET_FLAG(PWR_FLAG_USB33RDY)) {
        if((uint32_t)(HAL_GetTick()-start)>100U){usb_ptp_debug.init_error=1;return 1;}
    }
    HAL_PWREx_EnableVddUSB();
    usb_ptp_debug.init_stage=2;
    /* Change only HSE enable and USB muxes; keep the capture PLLs untouched. */
    __HAL_RCC_HSE_CONFIG(RCC_HSE_ON);start=HAL_GetTick();
    while(!__HAL_RCC_GET_FLAG(RCC_FLAG_HSERDY)) {
        if((uint32_t)(HAL_GetTick()-start)>100U){usb_ptp_debug.init_error=2;return 2;}
    }
    /* HSE/2 path is24MHz regardless of the separate direct-oscillator divider. */
    LL_RCC_SetOTGPHYClockSource(LL_RCC_OTGPHY1_CLKSOURCE_HSE_DIV_2);
    LL_RCC_SetOTGPHYCKREFClockSource(LL_RCC_OTGPHY1CKREF_CLKSOURCE_OTGPHY1);
    __HAL_RCC_USB1_OTG_HS_CLK_ENABLE();
    __HAL_RCC_USB1_OTG_HS_PHY_CLK_ENABLE();
    __HAL_RCC_USB1_OTG_HS_FORCE_RESET();__HAL_RCC_USB1_OTG_HS_RELEASE_RESET();
    MODIFY_REG(USB1_HS_PHYC->USBPHYC_CR,0x7U<<4,0x2U<<4);
    usb_ptp_debug.init_stage=3;
    return 0;
}
int usb_ptp_transport_init(const usb_ptp_callbacks *callbacks) {
    if(running)usb_ptp_transport_stop();
    memset(&usb_ptp_debug,0,sizeof usb_ptp_debug);memset(&cb,0,sizeof cb);
    if(callbacks)cb=*callbacks;
    memset(&pcd,0,sizeof pcd);memset(&dev,0,sizeof dev);
    tx_active=tx_zlp=event_active=rx_armed=cancel_pending=0;
    if(hardware_prepare())return (int)usb_ptp_debug.init_error;
    pcd.Instance=USB1_OTG_HS;pcd.Init.dev_endpoints=3;
    pcd.Init.speed=USB_PTP_FORCE_FS?PCD_SPEED_FULL:PCD_SPEED_HIGH;
    pcd.Init.dma_enable=DISABLE;pcd.Init.phy_itface=USB_OTG_HS_EMBEDDED_PHY;
    pcd.Init.Sof_enable=DISABLE;pcd.Init.low_power_enable=DISABLE;
    pcd.Init.lpm_enable=DISABLE;pcd.Init.vbus_sensing_enable=DISABLE;
    pcd.Init.use_dedicated_ep1=DISABLE;pcd.Init.use_external_vbus=DISABLE;
    pcd.pData=&dev;dev.pData=&pcd;
    if(HAL_PCD_Init(&pcd)!=HAL_OK){usb_ptp_debug.init_error=3;return 3;}
    usb_ptp_debug.init_stage=4;
    /* 1024word shared FIFO:256RX+64EP0+256bulkIN+32eventIN=608words. */
    HAL_PCDEx_SetRxFiFo(&pcd,256);HAL_PCDEx_SetTxFiFo(&pcd,0,64);
    HAL_PCDEx_SetTxFiFo(&pcd,1,256);HAL_PCDEx_SetTxFiFo(&pcd,2,32);
    if(USBD_Init(&dev,&descriptors,0)!=USBD_OK || USBD_RegisterClass(&dev,&ptp_class)!=USBD_OK) {
        usb_ptp_debug.init_error=4;return 4;
    }
    running=1;usb_ptp_debug.init_stage=5;
    HAL_NVIC_SetPriority(USB1_OTG_HS_IRQn,6,0);HAL_NVIC_ClearPendingIRQ(USB1_OTG_HS_IRQn);
#if USB_PTP_USE_IRQ
    HAL_NVIC_EnableIRQ(USB1_OTG_HS_IRQn);
#else
    HAL_NVIC_DisableIRQ(USB1_OTG_HS_IRQn);
#endif
    if(USBD_Start(&dev)!=USBD_OK){running=0;usb_ptp_debug.init_error=5;return 5;}
    usb_ptp_debug.init_stage=6;return 0;
}
void usb_ptp_transport_stop(void) {
    HAL_NVIC_DisableIRQ(USB1_OTG_HS_IRQn);
    if(running){(void)USBD_DeInit(&dev);running=0;}
    tx_active=tx_zlp=rx_armed=event_active=0;
}
void USB1_OTG_HS_IRQHandler(void) {
    if(running){usb_ptp_debug.interrupts++;HAL_PCD_IRQHandler(&pcd);}
}
void usb_ptp_transport_poll(void) {
    if(!running)return;
    usb_ptp_debug.polls++;
#if !USB_PTP_USE_IRQ
    HAL_PCD_IRQHandler(&pcd);
#endif
    usb_ptp_debug.gintsts=USB1_OTG_HS->GINTSTS;usb_ptp_debug.gintmsk=USB1_OTG_HS->GINTMSK;
    usb_ptp_debug.gusbcfg=USB1_OTG_HS->GUSBCFG;usb_ptp_debug.gccfg=USB1_OTG_HS->GCCFG;
    USB_OTG_DeviceTypeDef *d=(USB_OTG_DeviceTypeDef *)((uintptr_t)USB1_OTG_HS+USB_OTG_DEVICE_BASE);
    usb_ptp_debug.dctl=d->DCTL;usb_ptp_debug.dsts=d->DSTS;
    usb_ptp_debug.pwr_svmcr3=PWR->SVMCR3;usb_ptp_debug.rcc_ccipr6=RCC->CCIPR6;
    usb_ptp_debug.phy_cr=USB1_HS_PHYC->USBPHYC_CR;
}

/* ST USB Device core to HAL PCD bridge. PCD initialization is deliberately
 * outside the LL hook so every failure has a bounded, readable init stage. */
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef*d){(void)d;return USBD_OK;}
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef*d){return convert(HAL_PCD_DeInit(d->pData));}
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef*d){return convert(HAL_PCD_Start(d->pData));}
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef*d){return convert(HAL_PCD_Stop(d->pData));}
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef*d,uint8_t a,uint8_t t,uint16_t m){return convert(HAL_PCD_EP_Open(d->pData,a,m,t));}
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef*d,uint8_t a){return convert(HAL_PCD_EP_Close(d->pData,a));}
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef*d,uint8_t a){return convert(HAL_PCD_EP_Flush(d->pData,a));}
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef*d,uint8_t a){return convert(HAL_PCD_EP_SetStall(d->pData,a));}
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef*d,uint8_t a){return convert(HAL_PCD_EP_ClrStall(d->pData,a));}
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef*d,uint8_t a){PCD_HandleTypeDef*h=d->pData;return a&0x80?h->IN_ep[a&15].is_stall:h->OUT_ep[a&15].is_stall;}
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef*d,uint8_t a){return convert(HAL_PCD_SetAddress(d->pData,a));}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef*d,uint8_t a,uint8_t*b,uint32_t n){d->ep_in[a&15].total_length=n;return convert(HAL_PCD_EP_Transmit(d->pData,a,b,n));}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef*d,uint8_t a,uint8_t*b,uint32_t n){return convert(HAL_PCD_EP_Receive(d->pData,a,b,n));}
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef*d,uint8_t a){return HAL_PCD_EP_GetRxCount(d->pData,a);}
void USBD_LL_Delay(uint32_t n){HAL_Delay(n);}

void HAL_PCD_SetupStageCallback(PCD_HandleTypeDef*h){
    uint8_t*s=(uint8_t*)h->Setup;usb_ptp_debug.setups++;
    usb_ptp_debug.last_setup=(uint32_t)s[0]|((uint32_t)s[1]<<8);
    usb_ptp_debug.last_setup_value=(uint32_t)s[2]|((uint32_t)s[3]<<8);
    usb_ptp_debug.last_setup_index_length=(uint32_t)s[4]|((uint32_t)s[5]<<8)|((uint32_t)s[6]<<16)|((uint32_t)s[7]<<24);
    (void)USBD_LL_SetupStage(h->pData,s);
}
void HAL_PCD_DataOutStageCallback(PCD_HandleTypeDef*h,uint8_t ep){
    /* ST core unconditionally ACKs after EP0_RxReady, even when it returns
     * failure. Reject malformed cancellation data before entering that core
     * path so its status stage really is stalled. */
    if(ep==0 && cancel_pending && (HAL_PCD_EP_GetRxCount(h,0)!=6 ||
       control_buffer[0]!=1 || control_buffer[1]!=0x40)) {
        cancel_pending=0;(void)bad_setup(h->pData,&((USBD_HandleTypeDef*)h->pData)->request);return;
    }
    (void)USBD_LL_DataOutStage(h->pData,ep,h->OUT_ep[ep].xfer_buff);
}
void HAL_PCD_DataInStageCallback(PCD_HandleTypeDef*h,uint8_t ep){(void)USBD_LL_DataInStage(h->pData,ep,h->IN_ep[ep].xfer_buff);}
void HAL_PCD_ResetCallback(PCD_HandleTypeDef*h){
    USBD_SpeedTypeDef speed=h->Init.speed==PCD_SPEED_HIGH?USBD_SPEED_HIGH:USBD_SPEED_FULL;
    usb_ptp_debug.resets++;usb_ptp_debug.speed=(speed==USBD_SPEED_HIGH)?480:12;
    (void)USBD_LL_SetSpeed(h->pData,speed);(void)USBD_LL_Reset(h->pData);
    tx_active=tx_zlp=event_active=rx_armed=cancel_pending=0;usb_ptp_debug.configured=0;
    if(cb.reset)cb.reset();
}
void HAL_PCD_SuspendCallback(PCD_HandleTypeDef*h){usb_ptp_debug.suspends++;(void)USBD_LL_Suspend(h->pData);}
void HAL_PCD_ResumeCallback(PCD_HandleTypeDef*h){usb_ptp_debug.resumes++;(void)USBD_LL_Resume(h->pData);}
void HAL_PCD_ConnectCallback(PCD_HandleTypeDef*h){(void)USBD_LL_DevConnected(h->pData);}
void HAL_PCD_DisconnectCallback(PCD_HandleTypeDef*h){(void)USBD_LL_DevDisconnected(h->pData);usb_ptp_debug.configured=0;tx_active=tx_zlp=rx_armed=event_active=0;if(cb.reset)cb.reset();}
