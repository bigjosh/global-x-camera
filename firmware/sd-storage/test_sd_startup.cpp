#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

#if !SD_STARTUP_OPT
#error "Startup tests require the opt-in profile"
#endif

static uint32_t startup_test_hz()
{
    return SD_HIGH_SPEED?50000000U:12500000U;
}

int main()
{
    /* Use a 1us model step, rather than the historical coarse 1ms step,
     * so the short divider wait and retained clock train are distinguished. */
    for(uint32_t hz: {startup_test_hz(),SD_HIGH_SPEED?50000000U:25000000U}) {
        auto c=reset_init_model();stream_time=true;
        assert(sd_init(&c,hz)==SD_OK);
        assert(c.initialized && c.controller_owned && c.media_idle && !c.error);
        assert(sd_startup_proof.magic==0x31504F53U && sd_startup_proof.version==1U);
        assert(sd_startup_proof.gpio_settle_cycles>=400000U);
        assert(sd_startup_proof.gpio_settle_cycles<404000U);
        assert(sd_startup_proof.train_cycles>=400000U && sd_startup_proof.train_cycles<404000U);
        assert(sd_startup_proof.train_hz==100000U && sd_startup_proof.train_min_cycles==400000U);
        assert(startup_command0_cycle-startup_power_cycle>=400000U);
        assert(startup_command0_cycle-startup_power_cycle<410000U);
        assert(sd_startup_proof.run_settle_cycles>=400U && sd_startup_proof.run_settle_cycles<4000U);
        assert(sd_startup_proof.run_hz==(SD_HIGH_SPEED?25000000U:hz));
        assert(number_of(51)==1 && sd_startup_proof.scr_reads==1 && !sd_startup_proof.scr_hits);
        assert(sd_startup_proof.scr_valid && startup_scr_owner==&c);
        uint8_t original[8];memcpy(original,scr_bytes,8);
        auto n=commands.size();sd_scr_t scr{};
        assert(sd_read_scr(&c,&scr)==SD_OK && commands.size()==n);
        assert(scr.valid && scr.erased_byte==255U && !memcmp(scr.bytes,original,8));
        assert(sd_startup_proof.scr_hits==1 && c.stage==SD_STAGE_SCR);

        /* SCR is immutable for the same physical card. A synthetic changed
         * response stays unobserved until a deliberately fresh diagnostic. */
        scr_bytes[1]&=~0x80U;scr_bytes[7]=0xA5U;
        assert(sd_read_scr(&c,&scr)==SD_OK && commands.size()==n);
        assert(!memcmp(scr.bytes,original,8) && sd_startup_proof.scr_hits==2);
        assert(sd_read_scr_fresh(&c,&scr)==SD_OK);
        assert(number_of(51)==2 && sd_startup_proof.scr_reads==2);
        assert(scr.valid && !scr.erased_byte && !memcmp(scr.bytes,scr_bytes,8));
        assert(sd_deinit(&c)==SD_OK);
        assert(!startup_scr.valid && !startup_scr_owner);
        assert(!sd_startup_proof.scr_valid && !sd_startup_proof.cache_owner && !sd_startup_proof.result);
        n=commands.size();assert(sd_read_scr(&c,&scr)==SD_ERR_STATE && !scr.valid && commands.size()==n);
    }
    { auto c=reset_init_model();stream_time=true;
      test_dwt.CYCCNT.value=0xFFFF0000U;
      assert(sd_init(&c,startup_test_hz())==SD_OK && sd_startup_proof.train_cycles>=400000U);
      assert(sd_deinit(&c)==SD_OK);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      auto n=commands.size();test_rcc.AHB5ENR.value&=~RCC_AHB5ENR_SDMMC2EN;
      sd_scr_t scr{};assert(sd_read_scr(&c,&scr)==SD_ERR_CLOCK && commands.size()==n);
      assert(!startup_scr.valid && !startup_scr_owner && !sd_startup_proof.scr_valid);
      assert(sd_startup_proof.result==SD_ERR_CLOCK && !scr.valid);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      command_crc_error=13U;
      assert(sd_sync(&c)==SD_ERR_COMMAND_CRC);
      assert(!startup_scr.valid && !sd_startup_proof.cache_owner);
      auto n=commands.size();sd_scr_t scr{};
      assert(sd_read_scr(&c,&scr)==SD_ERR_COMMAND_CRC && commands.size()==n && !scr.valid);
    }
    for(unsigned failure=0;failure<4;failure++) {
      auto c=reset_init_model();stream_time=true;
      if(failure==0) command_error=51U;
      if(failure==1) scr_bytes[0]=0xF0U;
      if(failure==2) scr_bytes[1]=0x81U; /* Valid SCR, no four-bit support. */
      if(failure==3) app_width_r1=0x900U; /* Failed width negotiation after SCR. */
      assert(sd_init(&c,startup_test_hz())!=SD_OK);
      assert(!c.initialized && !startup_scr.valid && !startup_scr_owner);
      assert(!sd_startup_proof.scr_valid && !sd_startup_proof.cache_owner && sd_startup_proof.result);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      data_error_at=0;sd_scr_t scr{};
      assert(sd_read_scr_fresh(&c,&scr)==SD_ERR_DATA);
      assert(!scr.valid && !startup_scr.valid && !startup_scr_owner);
      assert(sd_startup_proof.scr_reads==2 && !sd_startup_proof.scr_hits);
    }
    { auto c=reset_init_model();stream_time=true;drop_negedge_write=true;
      assert(sd_init(&c,startup_test_hz())==SD_ERR_CLOCK);
      assert(!number_of(0) && !number_of(51) && !startup_scr.valid && !sd_startup_proof.train_cycles);
    }
    { auto c=reset_init_model();stream_time=true;drop_controller_gate=true;
      assert(sd_init(&c,startup_test_hz())==SD_ERR_CLOCK);
      assert(commands.empty() && !c.controller_owned && !startup_scr.valid);
    }
    { auto c=reset_init_model();test_dwt.CTRL.value=DWT_CTRL_NOCYCCNT_Msk;
      assert(sd_init(&c,startup_test_hz())==SD_ERR_TIMER);
      assert(commands.empty() && !c.controller_owned && !startup_scr.valid);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      test_rcc.AHB5ENR.value&=~RCC_AHB5ENR_SDMMC2EN;
      auto n=commands.size();assert(sd_deinit(&c)==SD_ERR_CLOCK && commands.size()==n);
      assert(c.controller_owned && !startup_scr.valid && !startup_scr_owner);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      sd_card_t other=c;sd_scr_t scr{};scr_bytes[7]=0x55U;
      assert(sd_read_scr(&other,&scr)==SD_OK && number_of(51)==2);
      assert(startup_scr_owner==&other && !sd_startup_proof.scr_hits && scr.bytes[7]==0x55U);
      assert(sd_deinit(&other)==SD_OK);
    }
    { auto c=reset_init_model();stream_time=true;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      assert(sd_deinit(&c)==SD_OK);
      c=reset_init_model();stream_time=true;scr_bytes[1]=5U;
      assert(sd_init(&c,startup_test_hz())==SD_OK);
      sd_scr_t scr{};assert(sd_read_scr(&c,&scr)==SD_OK && !scr.erased_byte);
      assert(sd_startup_proof.scr_reads==1 && sd_startup_proof.scr_hits==1 && !sd_startup_proof.result);
      assert(sd_deinit(&c)==SD_OK);
    }
    { auto c=reset_init_model();c.error=SD_ERR_DATA;c.stage=SD_STAGE_DEINIT;
      assert(sd_init(&c,100000U)==SD_ERR_ARGUMENT && commands.empty());
      assert(c.error==SD_ERR_ARGUMENT && c.error_stage==SD_STAGE_PREFLIGHT);
      assert(!sd_startup_proof.train_cycles && !startup_scr.valid);
    }
    std::puts("SD startup protocol cases passed");
}
