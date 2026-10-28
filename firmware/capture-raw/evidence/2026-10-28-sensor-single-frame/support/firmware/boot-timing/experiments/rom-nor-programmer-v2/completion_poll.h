/* Included after status()/fail(); the native tests execute this exact code.
 * Macronix MX25UM51245G PM2183 v1.6, section 9-1 and Figures 17/18:
 * observe WIP=0, then issue another RDSR to check WEL=0. WEL=1 polls again.
 * No WREN, WRDI, reset, retry of the write, or security command in this loop. */
static int wait_write_complete(struct context *c, uint32_t us)
{
    uint32_t start=DWT->CYCCNT, wip_clear_seen=0;
    uint32_t budget=us*CYCLES_PER_US;
    ++D[COMPLETE_CALLS];
    D[LAST_STAGE]=S[STAGE]; D[LAST_ADDRESS]=S[ADDRESS];
    D[FIRST_STATUS]=0xFFFFFFFFUL; D[LAST_STATUS]=0xFFFFFFFFUL;
    D[LAST_READS]=0; D[LAST_WEL_PENDING]=0; D[LAST_ELAPSED]=0;
    for (uint32_t i=0; i<1000000UL; ++i) {
        if (!status(c)) return 0;
        uint32_t value=S[NOR_STATUS], elapsed=(uint32_t)(DWT->CYCCNT-start);
        ++D[TOTAL_READS]; ++D[LAST_READS];
        if (!i) D[FIRST_STATUS]=value;
        D[LAST_STATUS]=value; D[LAST_ELAPSED]=elapsed;
        if (elapsed>D[MAX_COMPLETE_CYCLES]) D[MAX_COMPLETE_CYCLES]=elapsed;
        if ((value&3UL)==2UL) {
            if (!D[WEL_PENDING_READS]) {
                D[FIRST_PENDING_STAGE]=S[STAGE];
                D[FIRST_PENDING_ADDRESS]=S[ADDRESS];
                D[FIRST_PENDING_STATUS]=value;
                D[FIRST_PENDING_ELAPSED]=elapsed;
            }
            ++D[WEL_PENDING_READS];
            if (!D[LAST_WEL_PENDING]) ++D[PENDING_OPERATIONS];
            ++D[LAST_WEL_PENDING];
        }
        /* The accepted byte must be from a new transaction AFTER an earlier
         * WIP-clear observation, even if the first byte already had both zero.
         * Do not require observing WIP=1: a quick operation may finish first. */
        if (wip_clear_seen && !(value&3UL) && elapsed<budget) return 1;
        wip_clear_seen=!(value&1UL);
        if (wip_clear_seen && elapsed>S[MAX_WIP_CYCLES]) S[MAX_WIP_CYCLES]=elapsed;
        if (elapsed>=budget) break;
    }
    fail(c, (S[NOR_STATUS]&1UL) ? NOR_BUSY : WEL_FAILURE);
    return 0;
}
