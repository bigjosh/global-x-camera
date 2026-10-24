#ifndef MVE_MODEL_H
#define MVE_MODEL_H
/* Semantic host model only: no claim to emulate M55 timing or CPU context. */
#include <stdint.h>
typedef struct {uint8_t a[16];} uint8x16_t;
typedef struct {uint16_t a[8];} uint16x8_t;
static uint16x8_t vdupq_n_u16(uint16_t a) {uint16x8_t r;for(int i=0;i<8;i++)r.a[i]=a;return r;}
static uint8x16_t vld1q_u8(const uint8_t *p) {uint8x16_t r;for(int i=0;i<16;i++)r.a[i]=p[i];return r;}
static void vst1q_u8(uint8_t *p,uint8x16_t a) {for(int i=0;i<16;i++)p[i]=a.a[i];}
static uint16x8_t vreinterpretq_u16_u8(uint8x16_t a) {uint16x8_t r;for(int i=0;i<8;i++)r.a[i]=(uint16_t)(a.a[2*i]|((uint16_t)a.a[2*i+1]<<8));return r;}
static uint8x16_t vreinterpretq_u8_u16(uint16x8_t a) {uint8x16_t r;for(int i=0;i<8;i++){r.a[2*i]=(uint8_t)a.a[i];r.a[2*i+1]=(uint8_t)(a.a[i]>>8);}return r;}
static uint16x8_t vorrq_u16(uint16x8_t a,uint16x8_t b) {for(int i=0;i<8;i++)a.a[i]|=b.a[i];return a;}
static uint16x8_t vshlq_n_u16(uint16x8_t a,int n) {for(int i=0;i<8;i++)a.a[i]=(uint16_t)(a.a[i]<<n);return a;}
static uint8x16_t vrev16q_u8(uint8x16_t a) {uint8x16_t r;for(int i=0;i<16;i++)r.a[i]=a.a[i^1];return r;}
static uint8x16_t vsubq_u8(uint8x16_t a,uint8x16_t b) {for(int i=0;i<16;i++)a.a[i]=(uint8_t)(a.a[i]-b.a[i]);return a;}
static uint16_t vmaxvq_u16(uint16_t a,uint16x8_t b) {for(int i=0;i<8;i++)if(b.a[i]>a)a=b.a[i];return a;}
#endif
