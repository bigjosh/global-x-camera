/* One PTP transaction at a time. USB callbacks never perform storage I/O. */
#include "ptp.h"
#include "transport/usb_ptp_transport.h"
#include "thumbnail/thumbnail_bmp.h"
#include <stddef.h>
#include <string.h>
extern uint32_t HAL_GetTick(void);
#define STORAGE 0x00010001U
#define PNG 0x380BU
#define MAX_OBJECTS 65536U
#define TX_BYTES 16384U
#ifndef PTP_BMP_THUMBNAIL
#define PTP_BMP_THUMBNAIL 1
#endif
#if PTP_BMP_THUMBNAIL != 0 && PTP_BMP_THUMBNAIL != 1
#error "PTP_BMP_THUMBNAIL must be 0 or 1"
#endif
volatile uint32_t ptp_stats[32];
volatile uint32_t ptp_log[128][8];
static photo_store_t *store;
static void *frame;
static uint32_t handles[MAX_OBJECTS], objects;
/* Catalogue layout is known from a successful header read, not guessed after
 * a later I/O error. Warning memory affects later names, never reuses pixels. */
static uint8_t object_flags[MAX_OBJECTS];
#define KNOWN_LEGACY 1U
#define KNOWN_WARNING 2U
static uint32_t pending_events[8][4], event_head, event_count;
static uint8_t dataset[4+MAX_OBJECTS*4] __attribute__((aligned(4)));
static uint8_t tx[TX_BYTES] __attribute__((aligned(4)));
static uint8_t row[PHOTO_STORE_PNG_ROW_BYTES+4] __attribute__((aligned(4)));
static uint8_t command[32] __attribute__((aligned(4)));
/* A timed-out/canceled response may remain owned by USB until a later abort
 * succeeds. Its buffer must outlive this ptp_poll stack frame. */
static uint8_t response[16] __attribute__((aligned(4)));
static uint32_t cleanup_pending;
static volatile uint32_t command_len, epoch, cancel_tid, cancel_seen, reset_pending;
static uint32_t session, active, active_tid, active_epoch, tx_used, sent;
static uint32_t used, log_index;
static uint16_t active_op;
static uint16_t rd16(const void *p){const uint8_t *b=p;return b[0]|(uint16_t)b[1]<<8;}
static uint32_t rd32(const void *p){const uint8_t *b=p;return b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;}
static void wr16(uint8_t *p,uint16_t v){p[0]=v;p[1]=v>>8;}
static void wr32(uint8_t *p,uint32_t v){wr16(p,v);wr16(p+2,v>>16);}
static void u16(uint16_t v){wr16(dataset+used,v);used+=2;}
static void u32(uint32_t v){wr32(dataset+used,v);used+=4;}
static void u64(uint64_t v){u32((uint32_t)v);u32((uint32_t)(v>>32));}
static void string(const char *s){size_t n=strlen(s);if(n>254)n=254;dataset[used++]=n?(uint8_t)(n+1):0;for(size_t i=0;i<n;i++)u16((uint8_t)s[i]);if(n)u16(0);}
static void array16(const uint16_t *v,unsigned n){u32(n);for(unsigned i=0;i<n;i++)u16(v[i]);}
static void rx(const uint8_t *p,uint32_t n){
 if(!command_len&&n<=sizeof command){memcpy(command,p,n);command_len=n;}
 else{ptp_stats[10]++;command_len=0xFFFFFFFFU;}
}
static void reset(void){epoch++;session=0;command_len=0;reset_pending=1;ptp_stats[11]++;}
static void cancel(uint32_t tid){
 if((active&&tid==active_tid)||(!active&&command_len>=12&&command_len<=32&&rd32(command+8)==tid)){
  cancel_tid=tid;cancel_seen=1;ptp_stats[12]++;
 }else ptp_stats[17]++;
}
static uint16_t status(void){return (active||cancel_seen||reset_pending||cleanup_pending)?0x2019:0x2001;}
static const usb_ptp_callbacks callbacks={rx,0,reset,cancel,reset,status};
int ptp_service(void *unused){(void)unused;usb_ptp_transport_poll();return !active || (epoch==active_epoch&&!(cancel_seen&&cancel_tid==active_tid));}
static int wait_tx(void){uint32_t start=HAL_GetTick();while(usb_ptp_tx_busy()){if(!ptp_service(0)||!usb_ptp_configured()||HAL_GetTick()-start>10000U)return 0;}return ptp_service(0)&&usb_ptp_configured();}
static int write_usb(const void *p,uint32_t n,int end){if(!wait_tx())return 0;if(usb_ptp_transmit(p,n,end))return 0;return wait_tx();}
static int append(const void *data,size_t n){const uint8_t *p=data;while(n){unsigned take=TX_BYTES-tx_used;if(take>n)take=(unsigned)n;memcpy(tx+tx_used,p,take);tx_used+=take;p+=take;n-=take;if(tx_used==TX_BYTES){if(!write_usb(tx,tx_used,0))return 0;sent+=tx_used;tx_used=0;}}return 1;}
static int finish_data(void){int ok=write_usb(tx,tx_used,1);sent+=tx_used;tx_used=0;return ok;}
static int data_begin(uint32_t bytes){uint8_t h[12];wr32(h,bytes+12);wr16(h+4,2);wr16(h+6,active_op);wr32(h+8,active_tid);tx_used=sent=0;return append(h,12);}
static int data_dataset(void){return data_begin(used)&&append(dataset,used)&&finish_data();}
static int png_sink(void *unused,const uint8_t *p,size_t n){(void)unused;return ptp_service(0)&&append(p,n);}
#if PTP_BMP_THUMBNAIL
static int thumbnail(const photo_info_t *info){
 uint32_t offset=0;size_t n;
 if(!data_begin(GX_THUMB_SIZE))return 0;
 while(offset<GX_THUMB_SIZE){
  if(!ptp_service(0)||gx_thumbnail_bmp_read((const uint8_t *)frame+info->image_offset,
      MAGIC_SLOTS_IMAGE_BYTES,offset,row,sizeof row,&n)||!n||!append(row,n))return 0;
  offset+=(uint32_t)n;
 }
 return finish_data();
}
#endif
static int visit(void *unused,const photo_info_t *info){(void)unused;if(objects==MAX_OBJECTS)return 0;handles[objects]=info->handle;object_flags[objects]=(info->flags&PHOTO_LEGACY)?KNOWN_LEGACY:0;objects++;return 1;}
static int catalogue(void){objects=0;int r=photo_store_scan(store,visit,0);ptp_stats[5]=objects;ptp_stats[6]=store->unknown_occupied;return r;}
static uint32_t object_index(uint32_t handle){for(unsigned i=0;i<objects;i++)if(handles[i]==handle)return i;return MAX_OBJECTS;}
static int exists(uint32_t handle){return object_index(handle)!=MAX_OBJECTS;}
static void remove_handle(uint32_t handle){for(unsigned i=0;i<objects;i++)if(handles[i]==handle){memmove(handles+i,handles+i+1,(objects-i-1)*4);memmove(object_flags+i,object_flags+i+1,objects-i-1);objects--;break;}ptp_stats[5]=objects;}
static void cached_info(uint32_t handle,photo_info_t *info){
 uint32_t index=object_index(handle);memset(info,0,sizeof(*info));
 info->handle=handle;info->slot_index=handle-1;info->slot_lba=(handle-1)*MAGIC_SLOTS_STRIDE;info->first_bad_lba=0xFFFFFFFFU;
 if(object_flags[index]&KNOWN_LEGACY){info->start_magic=MAGIC_SLOTS_LEGACY_START_MAGIC;info->image_offset=MAGIC_SLOTS_LEGACY_IMAGE_OFFSET;info->flags=PHOTO_LEGACY;}
 else{info->start_magic=MAGIC_SLOTS_START_MAGIC;info->image_offset=MAGIC_SLOTS_IMAGE_OFFSET;}
}
static int remember_warning(const photo_info_t *info){
 uint32_t i=object_index(info->handle);if(i==MAX_OBJECTS||!photo_store_is_recovered(info)||(object_flags[i]&KNOWN_WARNING))return 0;
 object_flags[i]|=KNOWN_WARNING;return 1;
}
static void queue_event(uint16_t code,uint32_t handle,uint32_t tid){
 if(event_count==8){ptp_stats[16]++;return;}
 uint8_t *p=(uint8_t *)pending_events[(event_head+event_count)%8];
 wr32(p,16);wr16(p+4,4);wr16(p+6,code);wr32(p+8,tid);wr32(p+12,handle);event_count++;
}
static void flush_event(void){if(event_count&&!usb_ptp_send_event(pending_events[event_head],16)){event_head=(event_head+1)%8;event_count--;}}
static uint16_t result_code(int r){return r==PHOTO_CANCELLED?0x201F:r==PHOTO_NOT_FOUND?0x2009:r==PHOTO_ARGUMENT?0x201D:0x2002;}
int ptp_init(photo_store_t *s,void *buffer){store=s;frame=buffer;session=active=cleanup_pending=0;cancel_seen=command_len=reset_pending=0;event_head=event_count=0;epoch++;if(catalogue()!=PHOTO_OK)return 1;return usb_ptp_transport_init(&callbacks);}
void ptp_stop(void){usb_ptp_transport_stop();session=active=cleanup_pending=cancel_seen=reset_pending=command_len=0;}
static void device_info(void){
 static const uint16_t ops[]={0x1001,0x1002,0x1003,0x1004,0x1005,0x1006,0x1007,0x1008,0x1009,0x100A,0x100B};
 static const uint16_t events[]={0x4003,0x4007};static const uint16_t formats[]={PNG};
 u16(100);u32(0);u16(100);string("");u16(0);array16(ops,sizeof ops/2);array16(events,2);array16(0,0);array16(0,0);array16(formats,1);
 string("Global X Camera");string("Global X RAW Camera");string("0.1");string("GX-N657-0001");
}
/* Every failed transfer owns its buffers until this bounded cleanup passes.
 * This includes class DeviceReset, which does not itself reset USB endpoints.
 * An actual bus reset/disconnect invalidates hardware ownership independently. */
static int cleanup_bulk(void){
 if(usb_ptp_configured()&&usb_ptp_cancel_transfer()){ptp_stats[19]++;return 0;}
 cleanup_pending=0;cancel_seen=0;active=0;ptp_stats[4]=0;
 if(reset_pending){reset_pending=0;event_head=event_count=0;}
 if(usb_ptp_configured())usb_ptp_receive_enable();
 return 1;
}
static void record_end(unsigned li,uint16_t code){
 ptp_log[li][6]=code;ptp_log[li][7]=HAL_GetTick();ptp_stats[15]=code;
}
static void begin_cleanup(unsigned li,uint16_t code){
 record_end(li,code);cleanup_pending=1;active=1;ptp_stats[4]=1;
 (void)cleanup_bulk();
}
void ptp_poll(void){
 usb_ptp_transport_poll();ptp_stats[0]++;
 if(reset_pending){cleanup_pending=1;active=1;ptp_stats[4]=1;}
 if(cleanup_pending){(void)cleanup_bulk();return;}
 if(!usb_ptp_configured())return;
 flush_event();
 if(!command_len){usb_ptp_receive_enable();return;}
 uint32_t n=command_len;command_len=0;
 if(n<12||n>32||rd32(command)!=n||rd16(command+4)!=1||(n-12)%4){ptp_stats[10]++;cleanup_pending=1;active=1;ptp_stats[4]=1;(void)cleanup_bulk();return;}
 active=1;active_epoch=epoch;active_op=rd16(command+6);active_tid=rd32(command+8);
 if(cancel_seen&&cancel_tid!=active_tid)cancel_seen=0;
 ptp_stats[1]=active_op;ptp_stats[2]=active_tid;ptp_stats[3]++;ptp_stats[4]=1;
 uint32_t p[5]={0};unsigned count=(n-12)/4;for(unsigned i=0;i<count;i++)p[i]=rd32(command+12+i*4);
 unsigned li=log_index++%128;ptp_log[li][0]=HAL_GetTick();ptp_log[li][1]=active_op;ptp_log[li][2]=active_tid;for(unsigned i=0;i<3;i++)ptp_log[li][3+i]=p[i];
 uint16_t code=0x2001,event_code=0;uint32_t response_param=0,event_handle=0;unsigned response_count=0;int ok=1,r=0;used=0;
 photo_info_t info;
 if(cancel_seen)code=0x201F;
 else if(active_op!=0x1001&&active_op!=0x1002&&!session)code=0x2003;
 else switch(active_op){
 case 0x1001:if(count){code=0x201D;break;}device_info();ok=data_dataset();break;
 case 0x1002:if(count!=1||!p[0])code=0x201D;else if(session){code=0x201E;response_param=session;response_count=1;}else session=p[0];break;
 case 0x1003:if(count)code=0x201D;else session=0;break;
 case 0x1004:if(count){code=0x201D;break;}u32(1);u32(STORAGE);ok=data_dataset();break;
 case 0x1005:
  if(count!=1||p[0]!=STORAGE){code=0x2008;break;}
  u16(3);u16(1);u16(0);u64((uint64_t)store->slot_count*PHOTO_STORE_PNG_BYTES);u64((uint64_t)(store->slot_count-objects-store->unknown_occupied)*PHOTO_STORE_PNG_BYTES);u32(store->slot_count-objects-store->unknown_occupied);string("RAW photo slots");string("GLOBALX");ok=data_dataset();break;
 case 0x1006:case 0x1007:
  if(count!=3){code=0x201D;break;}if(p[0]!=STORAGE&&p[0]!=0xFFFFFFFFU){code=0x2008;break;}
  if(p[1]&&p[1]!=PNG){code=0x2014;break;}if(p[2]&&p[2]!=0xFFFFFFFFU){code=0x201D;break;}
  if(active_op==0x1006){response_param=objects;response_count=1;}else{u32(objects);for(unsigned i=0;i<objects;i++)u32(handles[i]);ok=data_dataset();}break;
 case 0x1008:
  if(count!=1||!exists(p[0])){code=0x2009;break;}r=photo_store_info(store,p[0],&info);
  if(r==PHOTO_IO){cached_info(p[0],&info);info.flags|=PHOTO_READ_ERROR;if(store->io.recover)store->io.recover(store->io.user);}
  else if(r){code=result_code(r);break;}
  if(remember_warning(&info)){event_code=0x4007;event_handle=p[0];}
  if(object_flags[object_index(p[0])]&KNOWN_WARNING)info.flags|=PHOTO_READ_ERROR;
  {char name[64];photo_store_filename(&info,name,sizeof name);u32(STORAGE);u16(PNG);u16(0);u32(PHOTO_STORE_PNG_BYTES);
#if PTP_BMP_THUMBNAIL
   u16(GX_THUMB_FORMAT);u32(GX_THUMB_SIZE);u32(GX_THUMB_WIDTH);u32(GX_THUMB_HEIGHT);
#else
   u16(0);u32(0);u32(0);u32(0);
#endif
   u32(MAGIC_SLOTS_WIDTH);u32(MAGIC_SLOTS_HEIGHT);u32(16);u32(0);u16(0);u32(0);u32(p[0]);string(name);string("");string("");string("");ok=data_dataset();}break;
 case 0x1009:case 0x100A:
  if(count!=1||!exists(p[0])){code=0x2009;break;}
#if !PTP_BMP_THUMBNAIL
  if(active_op==0x100A){code=0x2010;break;}
#endif
  cached_info(p[0],&info);r=photo_store_load(store,&info,frame,PHOTO_STORE_BUFFER_BYTES);if(r){code=result_code(r);break;}
  if(remember_warning(&info)){event_code=0x4007;event_handle=p[0];}
  ptp_stats[7]++;ptp_stats[8]=info.flags;ptp_stats[9]=info.unreadable_sectors;
#if PTP_BMP_THUMBNAIL
  if(active_op==0x100A){ok=thumbnail(&info);break;}
#endif
  ok=data_begin(PHOTO_STORE_PNG_BYTES);if(ok)ok=photo_store_png(&info,frame,PHOTO_STORE_BUFFER_BYTES,row,sizeof row,png_sink,0)==PHOTO_OK;if(ok)ok=finish_data();break;
 case 0x100B:
  if((count!=1&&count!=2)||p[1]){code=0x201D;break;}if(p[0]==0xFFFFFFFFU){code=0x201D;break;}if(!exists(p[0])){code=0x2009;break;}
  r=photo_store_delete(store,p[0]);
  if(r){
   code=result_code(r);
   /* A late failure may follow a successful header release. Reconcile only
    * after fresh safe transport recovery, never repeat the deletion. Keep
    * the original failure response even if the requested object is now gone. */
   if(r==PHOTO_IO&&store->io.recover&&store->io.recover(store->io.user)&&
       photo_store_info(store,p[0],&info)==PHOTO_NOT_FOUND){
    remove_handle(p[0]);ptp_stats[18]++;event_code=0x4003;event_handle=p[0];
   }
  }else{remove_handle(p[0]);ptp_stats[13]++;event_code=0x4003;event_handle=p[0];}break;
 default:code=0x2005;break;
 }
 if(cancel_seen&&cancel_tid==active_tid&&epoch==active_epoch){
  /* Host cancellation finishes through GetDeviceStatus, without bulk reply. */
  if(event_code)queue_event(event_code,event_handle,active_tid);
  ptp_stats[14]++;begin_cleanup(li,0x201F);return;
 }
 if(epoch!=active_epoch||!usb_ptp_configured()){
  begin_cleanup(li,0x2007);return;
 }
 if(!ok){
  ptp_stats[14]++;code=0x2007;
  if(usb_ptp_cancel_transfer()){
   /* Do not overwrite tx/response or accept a command while an old IN
    * transfer remains owned. A later poll retries before doing other work. */
   ptp_stats[19]++;record_end(li,code);cleanup_pending=1;return;
  }
 }
 wr32(response,12+response_count*4);wr16(response+4,3);wr16(response+6,code);
 wr32(response+8,active_tid);wr32(response+12,response_param);
 int response_ok=write_usb(response,12+response_count*4,1);
 /* A class cancel/reset can arrive during the final response wait as well
  * as during image data. Consume it before dropping active/Busy state. */
 if(cancel_seen&&cancel_tid==active_tid&&epoch==active_epoch){
  if(event_code)queue_event(event_code,event_handle,active_tid);
  ptp_stats[14]++;begin_cleanup(li,0x201F);return;
 }
 if(!response_ok||epoch!=active_epoch||!usb_ptp_configured()){
  begin_cleanup(li,0x2007);return;
 }
 if(event_code){queue_event(event_code,event_handle,active_tid);flush_event();}
 record_end(li,code);ptp_stats[4]=0;active=0;usb_ptp_receive_enable();
}
