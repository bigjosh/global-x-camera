
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint32_t MODER,OTYPER,PUPDR,OSPEEDR,BSRR,ODR,IDR;} GPIO_TypeDef;
static GPIO_TypeDef ga,gc,gf,gh;
#define GPIOA (&ga)
#define GPIOC (&gc)
#define GPIOF (&gf)
#define GPIOH (&gh)
static void outputs(GPIO_TypeDef *g, uint32_t pins, uint32_t modes)
{
    g->BSRR = pins << 16; /* Preload LOW before connecting output drivers. */
    g->OTYPER &= ~pins;
    g->PUPDR &= ~(modes * 3U);
    g->OSPEEDR &= ~(modes * 3U);
    g->MODER = (g->MODER & ~(modes * 3U)) | modes;
}
static uint32_t packed(unsigned input)
{
    uint32_t a = input ? GPIOA->IDR : GPIOA->ODR;
    uint32_t c = input ? GPIOC->IDR : GPIOC->ODR;
    uint32_t f = input ? GPIOF->IDR : GPIOF->ODR;
    uint32_t h = input ? GPIOH->IDR : GPIOH->ODR;
    return ((f >> 5) & 1U) | (((c >> 10) & 1U) << 1)
        | (((f >> 6) & 1U) << 2) | (((a >> 2) & 1U) << 3)
        | (((c >> 12) & 1U) << 4) | (((h >> 2) & 1U) << 5);
}
static uint32_t seed=0x1459bc31U;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
#define CHECK(x) do {if(!(x)){printf("fail line%d %s\n",__LINE__,#x);return 1;}}while(0)
int main(void){
 GPIO_TypeDef *ports[]={&ga,&gc,&gf,&gh};
 const unsigned bits[]={4,0x1400,0x60,4};
 const unsigned modes[]={0x10,0x1100000,0x1400,0x10};
 for(unsigned c=0;c<4096;c++)for(unsigned p=0;p<4;p++){
  GPIO_TypeDef *g=ports[p]; uint32_t *w=(uint32_t*)g;
  for(unsigned i=0;i<7;i++)w[i]=next();
  GPIO_TypeDef old=*g;outputs(g,bits[p],modes[p]);
  unsigned two=0;
  for(unsigned i=0;i<16;i++)if(bits[p]&(1U<<i))two|=3U<<(i*2);
  CHECK(g->BSRR==(bits[p]<<16));CHECK(g->MODER==((old.MODER&~two)|modes[p]));
  CHECK(g->PUPDR==(old.PUPDR&~two));CHECK(g->OSPEEDR==(old.OSPEEDR&~two));
  CHECK(g->OTYPER==(old.OTYPER&~bits[p]));CHECK(g->ODR==old.ODR);CHECK(g->IDR==old.IDR);
 }
 for(unsigned pattern=0;pattern<64;pattern++){
  ga.IDR=ga.ODR=(pattern&8)?4:0;
  gc.IDR=gc.ODR=((pattern&2)?0x400:0)|((pattern&16)?0x1000:0);
  gf.IDR=gf.ODR=((pattern&1)?0x20:0)|((pattern&4)?0x40:0);
  gh.IDR=gh.ODR=(pattern&32)?4:0;
  CHECK(packed(0)==pattern);CHECK(packed(1)==pattern);
 }
 puts("16384 output-preservation cases; all64 input/output packed patterns passed");return 0;
}
