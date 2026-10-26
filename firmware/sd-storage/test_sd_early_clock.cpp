#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

#if !SD_EARLY_RUN_CLOCK
#error "Early clock tests require the explicit option"
#endif

int main()
{
    /* Exercise every legal decimal encoding and each reserved encoding. */
    const uint32_t units[]={100000,1000000,10000000,100000000};
    const uint32_t tenths[]={0,10,12,13,15,20,25,30,35,40,45,50,55,60,70,80};
    for(uint32_t encoded=0;encoded<256;encoded++) {
        uint32_t unit=encoded&7U,mult=(encoded>>3)&15U;
        uint32_t expected=(encoded&128U)||unit>3U||!mult?0U:units[unit]/10U*tenths[mult];
        assert(csd_transfer_hz(encoded)==expected);
    }
    assert(csd_transfer_hz(0x32U)==25000000U);
    assert(csd_transfer_hz(0x5AU)==50000000U);
    assert(csd_transfer_hz(0x100U)==0U);
    for(uint32_t hz: {12500000U,25000000U}) {
        auto c=reset_init_model();stream_time=true;select_busy_polls=3U;
        assert(sd_init(&c,hz)==SD_OK);
        const auto &p=sd_early_clock_proof;
        assert(p.magic==0x314B4345U && p.version==1U && !p.result);
        assert(p.requested_hz==hz && p.csd_tran_speed==0x32U && p.csd_max_hz==25000000U);
        assert(p.csd_command_count==7U && p.switch_command_count==p.csd_command_count);
        assert(p.select_command_count==p.switch_command_count+1U);
        assert(p.clock_before==(750U|SDMMC_CLKCR_HWFC_EN|SDMMC_CLKCR_NEGEDGE));
        assert(p.clock_after==((150000000U/(2U*hz))|SDMMC_CLKCR_HWFC_EN|SDMMC_CLKCR_NEGEDGE));
        assert(p.timer_before==200000U && p.timer_after==hz*2U);
        assert(p.switch_begin_cycles<p.switch_end_cycles && p.switch_end_cycles<p.select_begin_cycles);
        assert(early_clock_writes==1U && early_timer_writes==1U);
        for(size_t i=0;i<commands.size();i++) {
            auto expected=i<7U?100000U:hz;
            assert(model_sd_kernel_hz/(2U*(early_command_clocks[i]&SDMMC_CLKCR_CLKDIV))==expected);
        }
        assert(select_hz==hz && select_timer==hz*2U && !select_host_timeout);
        assert(sd_startup_proof.run_hz==hz && sd_startup_proof.run_settle_cycles>=400U);
        assert(c.initialized && c.media_idle && c.controller_owned && !c.error);
        assert(sd_deinit(&c)==SD_OK && p.select_command_count && !p.result);
    }
    for(uint32_t encoded: {0U,0x80U,0x34U,0x0AU,0x31U}) {
        auto c=reset_init_model();stream_time=true;early_csd_speed=encoded;
        assert(sd_init(&c,12500000U)==SD_ERR_UNSUPPORTED);
        assert(!number_of(7) && !number_of(13) && !number_of(51));
        assert(!early_clock_writes && !early_timer_writes && !c.initialized);
        assert(sd_early_clock_proof.result==SD_ERR_UNSUPPORTED && c.controller_owned);
    }
    /* 20 MHz supports12.5 MHz but refuses25 MHz without fallback. */
    { auto c=reset_init_model();stream_time=true;early_csd_speed=0x2AU;
      assert(sd_init(&c,12500000U)==SD_OK);assert(sd_deinit(&c)==SD_OK); }
    { auto c=reset_init_model();stream_time=true;early_csd_speed=0x2AU;
      assert(sd_init(&c,25000000U)==SD_ERR_UNSUPPORTED && !early_clock_writes && !number_of(7)); }
    for(uint32_t busy: {1U,2U,3U}) {
        auto c=reset_init_model();stream_time=true;early_busy_kind=busy;
        assert(sd_init(&c,12500000U)==SD_ERR_CONTROLLER_BUSY);
        assert(!number_of(7) && !number_of(13) && !early_clock_writes && !early_timer_writes);
        assert(!c.initialized && c.controller_owned && !c.media_idle);
    }
    for(uint32_t refusal: {1U,2U,3U}) {
        auto c=reset_init_model();stream_time=true;early_clock_refusal=refusal;
        assert(sd_init(&c,12500000U)==SD_ERR_CLOCK);
        assert(early_clock_writes==1U && !early_timer_writes && !number_of(7));
        assert(!c.initialized && c.controller_owned && !c.media_idle);
    }
    { auto c=reset_init_model();stream_time=true;early_initial_clock_corrupt=true;
      assert(sd_init(&c,12500000U)==SD_ERR_CLOCK && !early_clock_writes && !number_of(7)); }
    { auto c=reset_init_model();stream_time=true;early_timer_refusal=true;
      assert(sd_init(&c,12500000U)==SD_ERR_TIMER && early_clock_writes==1U && early_timer_writes==1U);
      assert(!number_of(7) && !number_of(13) && !c.initialized && c.controller_owned); }
    { auto c=reset_init_model();stream_time=true;command_crc_error=9U;
      assert(sd_init(&c,12500000U)==SD_ERR_COMMAND_CRC && !early_clock_writes && !number_of(7)); }
    { auto c=reset_init_model();stream_time=true;command_error=7U;
      assert(sd_init(&c,12500000U)==SD_ERR_COMMAND_TIMEOUT && !number_of(13));
      assert(!sd_early_clock_proof.select_command_count && sd_early_clock_proof.result==SD_ERR_COMMAND_TIMEOUT); }
    { auto c=reset_init_model();stream_time=true;select_busy_polls=3000U;
      assert(sd_init(&c,12500000U)==SD_ERR_NOT_READY && select_host_timeout);
      assert(!c.initialized && !c.media_idle && c.controller_owned); }
    { auto c=reset_init_model();stream_time=true;test_dwt.CYCCNT.value=0xFFF3B000U;
      assert(sd_init(&c,12500000U)==SD_OK);
      assert((uint32_t)(sd_early_clock_proof.switch_end_cycles-sd_early_clock_proof.switch_begin_cycles)<4000U);
      assert(sd_deinit(&c)==SD_OK); }
    std::puts("SD early clock protocol cases passed");
}
