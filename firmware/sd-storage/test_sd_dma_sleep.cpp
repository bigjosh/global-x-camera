#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

#if !SD_DMA_SLEEP_PROFILE || !SD_REVIEW_PROFILE
#error "Sleep tests require the opt-in reviewed profile"
#endif

static sd_card_t reset_sleep_model()
{
    auto card=reset_model();
    /* The startup-reviewed profile also checks the live peripheral gate. */
    test_rcc.AHB5ENR.value=RCC_AHB5ENR_SDMMC2EN;
    return card;
}

#define reset_model reset_sleep_model

static int publish_without_bsec(void *context,uint32_t *available)
{
    int result=publish_stream(context,available);
    test_rcc.APB4LPENR2.value=0;
    return result;
}

static uint32_t race_clock_reads;
static uint32_t completion_before_wfi(void)
{
    /* On the third timebase read, the driver has inspected incomplete STA
     * and is about to enter WFI. The peripheral completes independently.
     * No SD interrupt exists: the next periodic tick must still wake it. */
    if(++race_clock_reads==3U) {
        while(!(uint32_t(test_sd.STA)&SDMMC_STA_DATAEND)) {}
    }
    return milliseconds;
}

static void check_stream_output(uint32_t sectors)
{
    assert(output.size()==sectors*128U);
    for(uint32_t n=0;n<output.size();++n)
        assert(output[n]==load_word(stream_memory+12U+4U*n));
}

int main()
{
#ifdef _WIN32
    stream_memory=static_cast<uint8_t *>(VirtualAlloc(reinterpret_cast<void *>(uintptr_t(0x34000000U)),
        4U*1024U*1024U,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
#else
    stream_memory=static_cast<uint8_t *>(mmap(reinterpret_cast<void *>(uintptr_t(0x34000000U)),
        4U*1024U*1024U,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0));
#endif
    assert(stream_memory==reinterpret_cast<void *>(uintptr_t(0x34000000U)));

    /* Full frame remains one preannounced transaction, not one per wake. */
    { auto c=reset_model();sleep_model=true;stream_time=true;
      StreamSource source{3730U*512U,3730U*512U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      int result=sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,3730,&stream,&wait);
      if(result) std::fprintf(stderr,"full result=%d context=%u calls=%u wall=%u words=%u/%u\n",
          result,wait.context_faults,wait.wait_calls,wait.wall_ms,words,expected_words);
      assert(result==SD_OK);
      assert(stream.mode==SD_STREAM_IDMA && stream.publication_calls==1U);
      assert(stream.initial_available_bytes==source.total && stream.queued_bytes==source.total);
      assert(number_of(55)==1U && number_of(23)==1U && arguments[2]==3730U);
      assert(number_of(25)==1U && stop_count==1U && !dma_fifo_accesses);
      assert(wait.wait_calls>0 && wait.wait_calls==wfi_calls && wait.wall_ms==wait.wait_calls);
      assert(!wait.context_faults && !wait.immediate_wakes);
      assert(wait.active_cycles<wait.wall_ms*400000U);
      assert(c.written_sectors==3730U && c.media_idle && !test_sd.IDMACTRL.value);
      check_stream_output(3730U);
    }
    /* Incomplete publication must not sleep while camera DWT deadlines and
     * the foreground producer callback still need progress. */
    { auto c=reset_model();stream_time=stream_check=true;sleep_model=true;
      StreamSource source{3730U*512U,512U,80U,220U,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,3730,&stream,&wait)==SD_OK);
      assert(stream.mode==SD_STREAM_PIO && stream.initial_available_bytes==512U);
      assert(stream.starved_polls && stream.max_wait_cycles);
      assert(!wfi_calls && !wait.wait_calls && !wait.wall_ms && !wait.context_faults);
      assert(number_of(25)==1U && number_of(23)==1U && stop_count==1U);
      assert(c.written_sectors==3730U && c.media_idle);
      check_stream_output(3730U);
    }
    /* The old entry point stays polling even when the feature is compiled. */
    { auto c=reset_model();stream_time=true;
      StreamSource source{2048U,2048U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_OK);
      assert(stream.mode==SD_STREAM_IDMA && !wfi_calls && c.media_idle);
      check_stream_output(4U);
    }
    /* Both run and sleep clocks are prerequisites, before any SD command or
     * producer callback. Null clocks cannot silently fall back to polling. */
    for(uint32_t missing=0;missing<4U;++missing) {
      auto c=reset_model();stream_time=true;
      StreamSource source{2048U,2048U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      if(missing==0U) test_rcc.APB4ENR2.value=0;
      if(missing==1U) test_rcc.APB4LPENR2.value=0;
      if(missing==2U) wait.milliseconds=nullptr;
      int result=sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,4,
          &stream,missing==3U?nullptr:&wait);
      assert(result==(missing==3U?SD_ERR_ARGUMENT:SD_ERR_WAIT));
      assert(commands.empty() && !stream_calls && !wfi_calls);
      assert(wait.context_faults==(missing<2U?SD_WAIT_BSEC_CLOCK:missing==2U?SD_WAIT_NO_CLOCK:0U));
    }
    { auto c=reset_model();stream_time=true;
      StreamSource source{2048U,2048U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_without_bsec;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,4,&stream,&wait)==SD_ERR_WAIT);
      assert(stream_calls==1U && commands.empty() && !wfi_calls);
      assert(wait.context_faults==SD_WAIT_BSEC_CLOCK && !c.written_sectors);
    }
    for(uint32_t failure=0;failure<5U;++failure) {
      auto c=reset_model();stream_time=sleep_model=true;
      StreamSource source{8192U,8192U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      if(failure==0U) dma_stalled=true;
      if(failure==1U) dma_error_at=512U;
      if(failure==2U) dma_final_error=SDMMC_STA_IDMATE;
      if(failure==3U) wfi_change_context=true;
      if(failure==4U) data_error_at=512U;
      const int expected[]={SD_ERR_DATA_TIMEOUT,SD_ERR_DMA,SD_ERR_DMA,SD_ERR_WAIT,SD_ERR_DATA};
      assert(sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,16,&stream,&wait)==expected[failure]);
      assert(wait.wait_calls && c.media_idle && !test_sd.IDMACTRL.value && !c.written_sectors);
      assert(number_of(25)==1U && stop_count==1U && !dma_fifo_accesses);
      if(failure==0U) assert(wait.wall_ms==5000U && wait.wait_calls==5000U);
      if(failure==3U) assert(wait.wait_calls==1U && wait.context_faults==SD_WAIT_PRIMASK);
    }
    for(uint32_t timing=0;timing<3U;++timing) {
      auto c=reset_model();stream_time=sleep_model=true;
      StreamSource source{8192U,8192U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      sd_dma_wait_t wait{};wait.milliseconds=test_milliseconds;
      if(timing==0U) milliseconds=0xFFFFFFFEU;
      if(timing==1U) wfi_immediate=true;
      if(timing==2U) { race_clock_reads=0;wait.milliseconds=completion_before_wfi; }
      assert(sd_write_blocks_stream_preerase_wait(&c,100,stream_memory+12U,16,&stream,&wait)==SD_OK);
      assert(c.media_idle && c.written_sectors==16U && !wait.context_faults);
      if(timing==0U) assert(milliseconds<0xFFFFFFFEU && wait.wall_ms==wait.wait_calls);
      if(timing==1U) assert(wait.wait_calls && wait.immediate_wakes==wait.wait_calls && !wait.wall_ms);
      if(timing==2U) assert(wait.wait_calls==1U && wait.wall_ms==1U);
      check_stream_output(16U);
    }
#ifdef _WIN32
    assert(VirtualFree(stream_memory,0,MEM_RELEASE));
#else
    assert(!munmap(stream_memory,4U*1024U*1024U));
#endif
    std::puts("DMA sleep protocol cases passed");
    return 0;
}
