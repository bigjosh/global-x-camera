/* Offline standalone ASan/UBSan stressor. Independent PNG decoding is in
 * test_png16.py. This adds actual C memory/alignment instrumentation. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "png16.h"
#include "miniz_config.h"
#include "vendor/miniz/miniz.h"
#if MINIZ_USE_UNALIGNED_LOADS_AND_STORES != 1
#error Sanitized test must exercise the experimental fast path
#endif
static uint32_t sink_hash;
static int sink(void *user, const uint8_t *data, size_t bytes)
{
    (void)user;
    for (size_t i=0;i<bytes;i++) sink_hash=(sink_hash^data[i])*16777619u;
    return bytes>0 && bytes<=PNG16_MAX_CALLBACK_BYTES;
}
int main(void)
{
    uint8_t *owner=malloc(1120u*1364u*3u+1u);
    void *workspace=malloc(png16_workspace_size());
    if (!owner || !workspace) return 2;
    uint32_t seed=0x59438b;
    const unsigned widths[]={1,2,3,4,63,1023,1024,1120};
    const unsigned heights[]={1,2,3,4,15,16,17,30,1364};
    unsigned passed=0;
    for (unsigned wi=0;wi<sizeof(widths)/sizeof(widths[0]);wi++)
        for (unsigned hi=0;hi<sizeof(heights)/sizeof(heights[0]);hi++)
            for (unsigned pattern=0;pattern<3;pattern++) {
                unsigned w=widths[wi],h=heights[hi],stride=w*2+1;
                uint8_t *input=owner+1;
                for (unsigned y=0;y<h;y++) for (unsigned x=0;x<w;x++) {
                    seed=seed*1664525u+1013904223u;
                    unsigned v=pattern==0 ? 0 : pattern==1 ? (x+y)%31 : (seed>>16)&1023;
                    input[y*stride+2*x]=(uint8_t)v;
                    input[y*stride+2*x+1]=(uint8_t)(v>>8);
                }
                for (unsigned mode=1;mode<=3;mode++) {
                    memset(workspace,pattern ? 0xff : 0,png16_workspace_size());
                    png16_stats stats;
                    int rc=png16_encode(input,(size_t)stride*h,w,h,stride,
                        (png16_mode)mode,workspace,png16_workspace_size(),sink,NULL,&stats);
                    if (rc || stats.rows_encoded!=h) return 3;
                    passed++;
                }
            }
    printf("%u ASan/UBSan encode cases passed; sink hash %08x\n",passed,sink_hash);
    free(workspace); free(owner);
    return 0;
}
