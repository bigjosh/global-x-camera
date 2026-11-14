#include "photo_store.h"
#include "../capture_controls.h"
#include <string.h>

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void be16(uint8_t *p, uint32_t x) { p[0]=(uint8_t)(x>>8); p[1]=(uint8_t)x; }
static void be32(uint8_t *p, uint32_t x) {
    p[0]=(uint8_t)(x>>24); p[1]=(uint8_t)(x>>16); p[2]=(uint8_t)(x>>8); p[3]=(uint8_t)x;
}
static int service(photo_store_t *s) { return !s->io.service || s->io.service(s->io.user); }
static uint32_t free_word(photo_store_t *s) { return s->erased_byte ? UINT32_MAX : 0; }
static int valid_handle(photo_store_t *s, uint32_t h) { return s && h && h<=s->slot_count; }
static int recover(photo_store_t *s) { return s->io.recover && s->io.recover(s->io.user); }

static int parse_header(photo_store_t *s, uint32_t h, const uint8_t *p, photo_info_t *i) {
    uint32_t magic=le32(p);
    memset(i,0,sizeof(*i));
    i->handle=h; i->slot_index=h-1; i->slot_lba=(h-1)*MAGIC_SLOTS_STRIDE;
    i->start_magic=magic; i->first_bad_lba=UINT32_MAX;
    if (magic==free_word(s)) return PHOTO_NOT_FOUND;
    if (magic!=MAGIC_SLOTS_START_MAGIC && magic!=MAGIC_SLOTS_LEGACY_START_MAGIC)
        return PHOTO_UNSUPPORTED;
    i->flags=PHOTO_PREFIX_VALID;
    if (magic==MAGIC_SLOTS_START_MAGIC) {
        i->image_offset=MAGIC_SLOTS_IMAGE_OFFSET;
        memcpy(i->metadata,p+MAGIC_SLOTS_METADATA_OFFSET,MAGIC_SLOTS_METADATA_BYTES);
    } else {
        i->flags|=PHOTO_LEGACY; i->image_offset=MAGIC_SLOTS_LEGACY_IMAGE_OFFSET;
    }
    return PHOTO_OK;
}
static uint32_t trailer_offset(const photo_info_t *i) { return i->image_offset+MAGIC_SLOTS_IMAGE_BYTES; }
static void check_tail(photo_info_t *i, uint32_t marker) {
    i->flags|=PHOTO_TRAILER_CHECKED;
    i->flags&=~(uint32_t)(PHOTO_TRAILER_VALID|PHOTO_PARTIAL);
    i->flags|=marker==MAGIC_SLOTS_END_MAGIC ? PHOTO_TRAILER_VALID : PHOTO_PARTIAL;
}

int photo_store_open(photo_store_t *s, const photo_io_t *io, uint64_t sectors, uint32_t erased) {
    if (!s || !io || !io->read || (erased!=0 && erased!=255) ||
        sectors<MAGIC_SLOTS_STRIDE || sectors>UINT64_C(0x100000000)) return PHOTO_ARGUMENT;
    memset(s,0,sizeof(*s)); s->io=*io;
    s->slot_count=(uint32_t)(sectors/MAGIC_SLOTS_STRIDE); s->erased_byte=erased;
    return PHOTO_OK;
}
int photo_store_scan(photo_store_t *s, photo_visit_fn visit, void *user) {
    photo_info_t i;
    uint32_t slot;
    int r;
    if (!s || !s->io.read || !visit) return PHOTO_ARGUMENT;
    s->scanned_slots=s->known_objects=s->unknown_occupied=s->unreadable_headers=0;
    for (slot=0; slot<s->slot_count; ++slot) {
        if (!service(s)) return PHOTO_CANCELLED;
        if (!s->io.read(s->io.user,slot*MAGIC_SLOTS_STRIDE,s->scratch,1)) {
            ++s->unreadable_headers; return PHOTO_IO;
        }
        ++s->scanned_slots;
        r=parse_header(s,slot+1,(const uint8_t *)s->scratch,&i);
        if (r==PHOTO_UNSUPPORTED) ++s->unknown_occupied;
        if (r==PHOTO_OK) {
            ++s->known_objects;
            if (!visit(user,&i)) return PHOTO_CANCELLED;
        }
    }
    return PHOTO_OK;
}
int photo_store_info(photo_store_t *s, uint32_t h, photo_info_t *i) {
    int r;
    if (!valid_handle(s,h) || !i) return PHOTO_ARGUMENT;
    if (!s->io.read(s->io.user,(h-1)*MAGIC_SLOTS_STRIDE,s->scratch,1)) return PHOTO_IO;
    r=parse_header(s,h,(const uint8_t *)s->scratch,i);
    if (r) return r;
    if (!service(s)) return PHOTO_CANCELLED;
    if (!s->io.read(s->io.user,i->slot_lba+MAGIC_SLOTS_STRIDE-1,s->scratch,1)) {
        i->flags|=PHOTO_READ_ERROR|PHOTO_PARTIAL; i->read_errors=1;
        i->first_bad_lba=i->slot_lba+MAGIC_SLOTS_STRIDE-1;
        return recover(s) ? PHOTO_OK : PHOTO_IO;
    }
    check_tail(i,le32((const uint8_t *)s->scratch+trailer_offset(i)%SD_SECTOR_BYTES));
    return PHOTO_OK;
}
static void note_error(photo_info_t *i, uint32_t lba) {
    i->flags|=PHOTO_READ_ERROR; ++i->read_errors;
    if (i->first_bad_lba==UINT32_MAX) i->first_bad_lba=lba;
}
int photo_store_load(photo_store_t *s, photo_info_t *i, void *buffer, size_t bytes) {
    uint8_t *p=(uint8_t *)buffer;
    uint32_t n=0, count, k, magic;
    int stopped=0, header_missing=0;
    if (!i || !valid_handle(s,i->handle) || !buffer || ((uintptr_t)buffer&3U) ||
        bytes<PHOTO_STORE_BUFFER_BYTES || i->slot_index!=i->handle-1 ||
        i->slot_lba!=i->slot_index*MAGIC_SLOTS_STRIDE ||
        !((i->start_magic==MAGIC_SLOTS_START_MAGIC && i->image_offset==MAGIC_SLOTS_IMAGE_OFFSET) ||
          (i->start_magic==MAGIC_SLOTS_LEGACY_START_MAGIC && i->image_offset==MAGIC_SLOTS_LEGACY_IMAGE_OFFSET)))
        return PHOTO_ARGUMENT;
    /* Drop prior per-read counters; markers and this retrieval alone determine
     * fresh corruption status. Do not cache successful image bytes across reads. */
    i->flags&=PHOTO_LEGACY; i->read_errors=i->unreadable_sectors=0; i->first_bad_lba=UINT32_MAX;
    memset(p,0,PHOTO_STORE_BUFFER_BYTES);
    while (n<MAGIC_SLOTS_STRIDE) {
        if (!service(s)) return PHOTO_CANCELLED;
        count=MAGIC_SLOTS_STRIDE-n;
        if (count>PHOTO_STORE_IO_SECTORS) count=PHOTO_STORE_IO_SECTORS;
        if (stopped) { i->unreadable_sectors+=count; n+=count; continue; }
        if (!s->io.read(s->io.user,i->slot_lba+n,p+n*SD_SECTOR_BYTES,count)) {
            note_error(i,i->slot_lba+n);
            memset(p+n*SD_SECTOR_BYTES,0,count*SD_SECTOR_BYTES);
            if (!recover(s)) stopped=1;
            for (k=0;k<count;++k) {
                if (!service(s)) return PHOTO_CANCELLED;
                if (stopped || !s->io.read(s->io.user,i->slot_lba+n+k,p+(n+k)*SD_SECTOR_BYTES,1)) {
                    if (!stopped) {
                        note_error(i,i->slot_lba+n+k);
                        if (!recover(s)) stopped=1;
                    }
                    memset(p+(n+k)*SD_SECTOR_BYTES,0,SD_SECTOR_BYTES);
                    ++i->unreadable_sectors;
                    if (n+k==0) header_missing=1;
                }
            }
        }
        n+=count;
    }
    if (i->unreadable_sectors) i->flags|=PHOTO_UNREADABLE_SECTORS;
    magic=le32(p);
    if (!header_missing) {
        if (magic==free_word(s)) return PHOTO_NOT_FOUND;
        if (magic!=i->start_magic) return PHOTO_CHANGED;
        i->flags|=PHOTO_PREFIX_VALID;
        if (magic==MAGIC_SLOTS_START_MAGIC)
            memcpy(i->metadata,p+MAGIC_SLOTS_METADATA_OFFSET,MAGIC_SLOTS_METADATA_BYTES);
    } else memset(i->metadata,0,sizeof(i->metadata));
    check_tail(i,le32(p+trailer_offset(i)));
    return PHOTO_OK;
}
int photo_store_delete(photo_store_t *s, uint32_t h) {
    photo_info_t i;
    uint32_t remaining=MAGIC_SLOTS_STRIDE-1, count, pos, k;
    int r;
    if (!valid_handle(s,h) || !s->io.write || !s->io.sync) return PHOTO_ARGUMENT;
    if (!s->io.read(s->io.user,(h-1)*MAGIC_SLOTS_STRIDE,s->scratch,1)) return PHOTO_IO;
    r=parse_header(s,h,(const uint8_t *)s->scratch,&i);
    if (r) return r;
    memset(s->scratch,(int)s->erased_byte,sizeof(s->scratch));
    while (remaining) {
        if (!service(s)) return PHOTO_CANCELLED;
        count=remaining>PHOTO_STORE_IO_SECTORS ? PHOTO_STORE_IO_SECTORS : remaining;
        pos=1+remaining-count;
        if (!s->io.write(s->io.user,i.slot_lba+pos,s->scratch,count)) return PHOTO_IO;
        remaining-=count;
    }
    if (!s->io.sync(s->io.user)) return PHOTO_IO;
    if (!service(s)) return PHOTO_CANCELLED;
    if (!s->io.write(s->io.user,i.slot_lba,s->scratch,1) ||
        !s->io.sync(s->io.user) || !s->io.read(s->io.user,i.slot_lba,s->scratch,1)) return PHOTO_IO;
    for (k=0;k<SD_SECTOR_BYTES;++k)
        if (((const uint8_t *)s->scratch)[k]!=s->erased_byte) return PHOTO_IO;
    return PHOTO_OK;
}
int photo_store_is_recovered(const photo_info_t *i) {
    return i && (i->flags&(PHOTO_PARTIAL|PHOTO_READ_ERROR|PHOTO_UNREADABLE_SECTORS));
}
static size_t append(char *dst, size_t n, const char *src) {
    while (*src) dst[n++]=*src++;
    dst[n]=0; return n;
}
static size_t decimal(char *dst, size_t n, uint32_t x, uint32_t minimum) {
    char rev[10]; uint32_t used=0;
    do { rev[used++]=(char)('0'+x%10); x/=10; } while (x);
    while (minimum>used) { dst[n++]='0'; --minimum; }
    while (used) dst[n++]=rev[--used];
    dst[n]=0; return n;
}
int photo_store_filename(const photo_info_t *i, char *out, size_t cap) {
    char temp[48]; size_t n=0;
    if (!i || !out || !i->handle) return PHOTO_ARGUMENT;
    n=append(temp,n,"GX_"); n=decimal(temp,n,i->handle,7);
    if (photo_store_is_recovered(i)) n=append(temp,n,"_RECOVERED");
    n=append(temp,n,".png");
    if (cap<=n) return PHOTO_ARGUMENT;
    memcpy(out,temp,n+1); return (int)n;
}

static uint32_t crc_update(uint32_t crc,const uint8_t *p,size_t n) {
    static const uint32_t tab[16]={0,0x1db71064U,0x3b6e20c8U,0x26d930acU,
        0x76dc4190U,0x6b6b51f4U,0x4db26158U,0x5005713cU,0xedb88320U,0xf00f9344U,
        0xd6d6a3e8U,0xcb61b38cU,0x9b64c2b0U,0x86d3d2d4U,0xa00ae278U,0xbdbdf21cU};
    while (n--) {
        crc^=*p++; crc=(crc>>4)^tab[crc&15U]; crc=(crc>>4)^tab[crc&15U];
    }
    return crc;
}
static int emit(photo_write_fn wr,void *u,const uint8_t *p,size_t n) { return wr(u,p,n); }
static int chunk(photo_write_fn wr,void *u,const char type[4],const uint8_t *p,uint32_t n) {
    uint8_t h[8],c[4]; uint32_t crc;
    be32(h,n); memcpy(h+4,type,4); crc=crc_update(UINT32_MAX,h+4,4);
    crc=crc_update(crc,p,n); be32(c,crc^UINT32_MAX);
    return emit(wr,u,h,8) && (!n || emit(wr,u,p,n)) && emit(wr,u,c,4);
}
static int capture_settings(const photo_info_t *i,capture_controls_t *r) {
    if(i->start_magic!=MAGIC_SLOTS_START_MAGIC)return 0;
    memcpy(r,i->metadata,sizeof(*r));
    if(!capture_controls_valid(r) || (r->state!=CC_SENSOR_CONFIGURED && r->state!=CC_APPLIED_VERIFIED) ||
       r->flags!=(CC_REQUIRED_FLAGS|CC_F_SENSOR_CONFIGURED|(r->state==CC_APPLIED_VERIFIED?CC_F_APPLIED_VALID:0)) ||
       r->reserved0 || r->reserved1 || r->requested_us<1000 || r->requested_us>500000 ||
       r->line_length!=1280 || r->vt_hz!=160800000 || r->manual[0]!=2 || r->margin>1993)return 0;
    uint32_t coarse=r->manual[2]|(uint32_t)r->manual[3]<<8;
    uint32_t expected=(uint32_t)(((uint64_t)r->requested_us*160800000U+1279999999U)/1280000000U);
    uint32_t frame=coarse+2000U;if(frame<4336U)frame=4336U;
    if(coarse!=expected || r->frame_length!=frame || frame>65535 || frame<coarse+r->margin+7U)return 0;
    static const uint8_t gain[4]={0,16,24,28};unsigned sector;
    for(sector=0;sector<4 && gain[sector]!=r->manual[1];sector++){}
    if(sector==4 || r->asa!=(100U<<sector))return 0;
    for(unsigned j=4;j<12;j+=2)if(r->manual[j] || r->manual[j+1]!=1)return 0;
    if(r->state==CC_APPLIED_VERIFIED) {
        if(r->applied_coarse!=coarse || r->applied_gain!=r->manual[1] || r->applied_digital!=256)return 0;
    } else if(r->applied_coarse || r->applied_gain || r->applied_digital)return 0;
    return 1;
}
static void exif(const photo_info_t *i,uint8_t *p) {
    char *comment=(char *)(p+44+8); size_t n=0;
    memset(p,0,PHOTO_STORE_EXIF_BYTES);
    p[0]='M';p[1]='M';be16(p+2,42);be32(p+4,8);
    be16(p+8,1);be16(p+10,0x8769);be16(p+12,4);be32(p+14,1);be32(p+18,26);
    be16(p+26,1);be16(p+28,0x9286);be16(p+30,7);
    be32(p+32,PHOTO_STORE_COMMENT_BYTES);be32(p+36,44);
    memcpy(p+44,"ASCII\0\0\0",8);
    n=append(comment,n,"Global X; ");
    n=append(comment,n,photo_store_is_recovered(i) ? "RECOVERED; " : "no reported read errors; ");
    n=append(comment,n,"slot=");n=decimal(comment,n,i->slot_index,1);
    n=append(comment,n,"; completion_marker=");
    n=append(comment,n,(i->flags&PHOTO_TRAILER_VALID) ? "present" : "missing/unreadable");
    n=append(comment,n,"; failed_read_attempts=");n=decimal(comment,n,i->read_errors,1);
    n=append(comment,n,"; zero_filled_sectors=");n=decimal(comment,n,i->unreadable_sectors,1);
    if (i->first_bad_lba!=UINT32_MAX) {
        n=append(comment,n,"; first_error_lba=");n=decimal(comment,n,i->first_bad_lba,1);
    }
    capture_controls_t settings;
    if(capture_settings(i,&settings)) {
        uint32_t coarse=settings.manual[2]|(uint32_t)settings.manual[3]<<8;
        uint32_t us=(uint32_t)(((uint64_t)coarse*1280U*1000000U+80400000U)/160800000U);
        n=append(comment,n,"; settings=");n=append(comment,n,settings.state==CC_APPLIED_VERIFIED?"applied":"configured");
        n=append(comment,n,"; exposure_us=");n=decimal(comment,n,us,1);
        n=append(comment,n,"; analog_gain=");n=decimal(comment,n,32U/(32U-settings.manual[1]),1);
        n=append(comment,n,"x; ASA=");n=decimal(comment,n,settings.asa,1);n=append(comment,n," (provisional)");
    } else n=append(comment,n,"; capture settings unavailable");
    n=append(comment,n,"; packed RAW10 to gray16 (sample<<6). No stored payload checksum; markers and SD transport checks do not prove pixel integrity. Capture date/orientation unavailable.");
    (void)n; /* bounded literals + seven numeric fields fit504 bytes (worst-case test) */
}
int photo_store_png(const photo_info_t *i,const void *buffer,size_t bytes,
                    uint8_t *row,size_t row_bytes,photo_write_fn wr,void *u) {
    static const uint8_t signature[8]={137,80,78,71,13,10,26,10};
    const uint8_t *image;
    uint8_t hdr[13],ex[PHOTO_STORE_EXIF_BYTES],small[8];
    uint32_t crc,a=1,b=0,y,x,j,n=PHOTO_STORE_PNG_ROW_BYTES;
    uint32_t idat_size=2U+MAGIC_SLOTS_HEIGHT*(5U+PHOTO_STORE_PNG_ROW_BYTES)+4U;
    if (!i || !buffer || bytes<PHOTO_STORE_BUFFER_BYTES || !row || row_bytes<n || !wr ||
        !(i->flags&PHOTO_TRAILER_CHECKED) ||
        !((i->start_magic==MAGIC_SLOTS_START_MAGIC && i->image_offset==MAGIC_SLOTS_IMAGE_OFFSET) ||
          (i->start_magic==MAGIC_SLOTS_LEGACY_START_MAGIC && i->image_offset==MAGIC_SLOTS_LEGACY_IMAGE_OFFSET)))
        return PHOTO_ARGUMENT;
    image=(const uint8_t *)buffer+i->image_offset;
    be32(hdr,MAGIC_SLOTS_WIDTH);be32(hdr+4,MAGIC_SLOTS_HEIGHT);
    hdr[8]=16;hdr[9]=hdr[10]=hdr[11]=hdr[12]=0;
    small[0]=10;exif(i,ex);
    if (!emit(wr,u,signature,8) || !chunk(wr,u,"IHDR",hdr,13) ||
        !chunk(wr,u,"sBIT",small,1) || !chunk(wr,u,"eXIf",ex,sizeof(ex))) return PHOTO_WRITE_FAILED;
    be32(small,idat_size);memcpy(small+4,"IDAT",4);
    if (!emit(wr,u,small,8)) return PHOTO_WRITE_FAILED;
    crc=crc_update(UINT32_MAX,small+4,4);
    small[0]=0x78;small[1]=0x01;
    crc=crc_update(crc,small,2);
    if (!emit(wr,u,small,2)) return PHOTO_WRITE_FAILED;
    for (y=0;y<MAGIC_SLOTS_HEIGHT;++y) {
        const uint8_t *in=image+y*MAGIC_SLOTS_ROW_BYTES;
        row[0]=0;
        for (x=0;x<MAGIC_SLOTS_WIDTH;x+=4,in+=5) {
            for (j=0;j<4;++j) {
                uint32_t v=(((uint32_t)in[j]<<2)|((in[4]>>(2*j))&3U))<<6;
                be16(row+1+(x+j)*2,v);
            }
        }
        small[0]=(uint8_t)(y==MAGIC_SLOTS_HEIGHT-1);
        small[1]=(uint8_t)n;small[2]=(uint8_t)(n>>8);
        small[3]=(uint8_t)~n;small[4]=(uint8_t)(~n>>8);
        crc=crc_update(crc,small,5);crc=crc_update(crc,row,n);
        for (x=0;x<n;++x) { a+=row[x];b+=a; }
        a%=65521U;b%=65521U;
        if (!emit(wr,u,small,5) || !emit(wr,u,row,n)) return PHOTO_WRITE_FAILED;
    }
    be32(small,(b<<16)|a);crc=crc_update(crc,small,4);
    if (!emit(wr,u,small,4)) return PHOTO_WRITE_FAILED;
    be32(small,crc^UINT32_MAX);
    if (!emit(wr,u,small,4) || !chunk(wr,u,"IEND",0,0)) return PHOTO_WRITE_FAILED;
    return PHOTO_OK;
}
