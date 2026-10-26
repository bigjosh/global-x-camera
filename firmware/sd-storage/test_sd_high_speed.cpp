#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

int main()
{
#ifdef _WIN32
    stream_memory=static_cast<uint8_t *>(VirtualAlloc(reinterpret_cast<void *>(uintptr_t(0x34000000U)),
        4U*1024U*1024U,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
#else
    stream_memory=static_cast<uint8_t *>(mmap(reinterpret_cast<void *>(uintptr_t(0x34000000U)),
        4U*1024U*1024U,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0));
#endif
    assert(stream_memory==reinterpret_cast<void *>(uintptr_t(0x34000000U)));
    { auto c=reset_init_model();
      assert(sd_init(&c,50000000U)==SD_OK);
      assert(c.initialized && c.clock_hz==50000000U && c.media_idle);
      const uint32_t expected_c=SD_HIGH_SPEED_MIXED_SLEW?0x10U:0xFF3U;
      const uint32_t expected_e=SD_HIGH_SPEED_MIXED_SLEW?0:0x300U;
      assert((test_gpio_c.OSPEEDR.value&0xFF3U)==expected_c && (test_gpio_e.OSPEEDR.value&0x300U)==expected_e);
      assert(!((test_gpio_c.OSPEEDR.value^0xA5A5A5A5U)&~0xFF3U));
      assert(!((test_gpio_e.OSPEEDR.value^0x5A5A5A5AU)&~0x300U));
      assert(sd_high_speed_proof.gpio_c_after==test_gpio_c.OSPEEDR.value);
      assert(sd_high_speed_proof.gpio_e_after==test_gpio_e.OSPEEDR.value);
      assert(SD_HIGH_SPEED_FIXED_COMPENSATION ? (compensation_reads && compensation_writes==1U) : (!compensation_reads && !compensation_writes));
      assert(test_sd.CLKCR.value==0x24001U);
      assert(sd_high_speed_proof.check_done && sd_high_speed_proof.switch_done && sd_high_speed_proof.qualified);
      assert(number_of(6)==3);
      std::vector<uint32_t> functions;
      for(size_t n=0;n<commands.size();n++) if(commands[n]==6) functions.push_back(arguments[n]);
      assert((functions==std::vector<uint32_t>{2U,0x00FFFFF1U,0x80FFFFF1U}));
      assert(sd_bus_width_proof.configured_clkcr==0x24001U);
      assert(sd_review_clock_proof.state==4U && sd_review_clock_proof.owned);
      assert(sd_deinit(&c)==SD_OK);
      assert(sd_review_clock_proof.state==5U && !sd_review_clock_proof.owned);
      assert(!(test_rcc.CCIPR8.value&RCC_CCIPR8_SDMMC2SEL));
      assert(!(test_rcc.DIVENR.value&RCC_DIVENR_IC5EN));
    }
    for(unsigned mode=0;mode<2;mode++) for(unsigned failure=0;failure<11;failure++) {
      auto c=reset_init_model();
      auto *s=hs_status[mode];
      switch(failure) {
      case 0:s[13]=0;break;
      case 1:s[16]=15;break;
      case 2:s[17]=2;break;
      case 3:s[29]=2;break;
      case 4:s[1]=0;break;
      case 5:s[1]=201;break;
      case 6:s[14]=15;break;
      case 7:s[14]=0xF0;break;
      case 8:s[15]=15;break;
      case 9:s[15]=0xF0;break;
      case 10:s[16]=0xF1;break;
      }
      int expected=failure==3?SD_ERR_NOT_READY:SD_ERR_UNSUPPORTED;
      assert(sd_init(&c,50000000U)==expected);
      assert(!c.initialized && !c.controller_owned && c.media_idle && !c.cleanup_error);
      assert(c.error==(uint32_t)expected && !sd_high_speed_proof.qualified);
      assert(!sd_review_clock_proof.owned && sd_review_clock_proof.state==5U);
      assert(number_of(6)==(mode?3U:2U));
    }
    { auto c=reset_init_model();hs_command_error=2;
      assert(sd_init(&c,50000000U)==SD_ERR_COMMAND_CRC);
      assert(!sd_high_speed_proof.qualified && c.error==SD_ERR_COMMAND_CRC);
    }
    { auto c=reset_init_model();hs_error_at=3;
      assert(sd_init(&c,50000000U)==SD_ERR_DATA);
      assert(!sd_high_speed_proof.qualified && c.error==SD_ERR_DATA);
    }
    { auto c=reset_init_model();
      assert(sd_init(&c,25000000U)==SD_ERR_ARGUMENT && commands.empty());
    }
    { auto c=reset_init_model();scr_bytes[0]=0;
      assert(sd_init(&c,50000000U)==SD_ERR_UNSUPPORTED);
      assert(!c.controller_owned && !number_of(6));
    }
    { auto c=reset_init_model();drop_controller_gate=true;
      assert(sd_init(&c,50000000U)==SD_ERR_CLOCK);
      assert(!c.controller_owned && !sd_review_clock_proof.owned && commands.empty());
    }
    { auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      drop_ic5_disable=true;assert(sd_deinit(&c)==SD_ERR_CLOCK);
      assert(c.controller_owned && sd_review_clock_proof.owned);
      assert(!(test_rcc.AHB5ENR.value&RCC_AHB5ENR_SDMMC2EN));
      auto n=commands.size();assert(sd_sync(&c)==SD_ERR_CLOCK);
      assert(sd_deinit(&c)==SD_ERR_CLOCK && commands.size()==n);
    }
    { auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      c.clock_hz=0x80000000U;auto n=commands.size();
      assert(sd_sync(&c)==SD_ERR_CLOCK && commands.size()==n);
    }
    { auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      test_sd.CLKCR.value|=SDMMC_CLKCR_NEGEDGE;
      auto n=commands.size();uint8_t buffer[512];
      assert(sd_read_blocks(&c,0,buffer,1)==SD_ERR_CLOCK && commands.size()==n);
    }
    { auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      auto n=commands.size();auto clk=test_sd.CLKCR.value;
      assert(sd_init(&c,50000000U)==SD_ERR_STATE && commands.size()==n);
      assert(c.initialized && c.controller_owned && sd_review_clock_proof.owned && test_sd.CLKCR.value==clk);
      assert(sd_deinit(&c)==SD_OK);
    }
    { auto c=reset_init_model();hs_final_ready_error=true;
      assert(sd_init(&c,50000000U)==SD_ERR_COMMAND_CRC);
      assert(!c.initialized && !c.controller_owned && !c.cleanup_error);
      assert(!sd_high_speed_proof.qualified && sd_high_speed_proof.configured_clkcr==0x24001U);
      assert(sd_review_clock_proof.state==5U && !sd_review_clock_proof.owned);
    }
    { auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      sd_erase_t proof{};erase_busy_polls=100000;
      assert(sd_erase_all(&c,1000,&proof)==SD_ERR_NOT_READY);
      assert(c.clock_hz==100000U && !(test_sd.CLKCR.value&SDMMC_CLKCR_NEGEDGE));
      busy_polls=0;erase_active=false;erase_host_timeout=false;
      test_sd.STA.value=0;test_gpio_c.IDR.value|=1U<<4;
      assert(sd_sync(&c)==SD_OK && sd_deinit(&c)==SD_OK);
      assert(!c.controller_owned && sd_review_clock_proof.state==5U);
    }
    for(unsigned failure=1;failure<=3;failure++) {
      auto c=reset_init_model();bad_gpio_speed_write=failure;
      assert(sd_init(&c,50000000U)==SD_ERR_GPIO);
      assert(!sd_high_speed_proof.qualified && !c.controller_owned && !c.cleanup_error);
      assert(SD_HIGH_SPEED_FIXED_COMPENSATION ? (compensation_reads && compensation_writes==1U) : (!compensation_reads && !compensation_writes));
    }
#if SD_HIGH_SPEED_FIXED_COMPENSATION
    for(unsigned failure=1;failure<=6;failure++) {
      auto c=reset_init_model();bad_compensation_gate=failure;
      if(failure==3)test_pwr.SVMCR3.value=0;
      if(failure==4)test_rcc.APB4RSTR2.value=RCC_APB4RSTR2_SYSCFGRST;
      assert(sd_init(&c,50000000U)!=SD_OK);
      assert(!c.controller_owned && !sd_high_speed_proof.qualified && !number_of(6));
    }
#endif
    for(unsigned progressive=0;progressive<2;progressive++) {
      auto c=reset_init_model();assert(sd_init(&c,50000000U)==SD_OK);
      stream_time=true;stream_check=progressive;stop_busy_polls=3;
      StreamSource source{3730U*512U,progressive?512U:3730U*512U,80U,220U,0xFFFFFFFFU,false};
      if(!progressive)source.second_at=source.all_at=0xFFFFFFFFU;
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,3730,&stream)==SD_OK);
      assert(stream.mode==(progressive?SD_STREAM_PIO:SD_STREAM_IDMA));
      assert(number_of(25)==1 && number_of(23)==1 && stop_count==1);
      assert(c.written_sectors==3730 && c.media_idle && !test_sd.IDMACTRL.value);
      assert(stop_timer==100000000U && stop_hz==50000000U && !dctrl_active_writes);
      assert(stream.queued_bytes==source.total && output.size()==3730U*128U);
      for(unsigned n=0;n<output.size();n++)assert(output[n]==load_word(stream_memory+12U+4U*n));
      assert(sd_deinit(&c)==SD_OK);
    }
#ifdef _WIN32
    assert(VirtualFree(stream_memory,0,MEM_RELEASE));
#else
    assert(!munmap(stream_memory,4U*1024U*1024U));
#endif
    puts("high-speed protocol cases passed");
    return 0;
}
