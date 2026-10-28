#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

static sd_card_t read_card()
{
    auto c=reset_init_model();
    assert(sd_init(&c,SD_HIGH_SPEED?50000000U:25000000U)==SD_OK);
    commands.clear();arguments.clear();stop_count=0;
    return c;
}

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
    auto *destination=stream_memory+0x200000U;
    for(uint32_t count: {1U,2U,64U,512U,513U}) {
        auto c=read_card();stop_busy_polls=3;
        memset(destination-4,0xA5,count*512U+8U);
        auto clk=test_sd.CLKCR.value;
        assert(sd_read_blocks(&c,100,destination,count)==SD_OK);
        assert(c.read_sectors==count && c.media_idle && !c.cleanup_error);
        assert(!test_sd.IDMACTRL.value && !dma_fifo_accesses && !fifo_resets && !dctrl_active_writes);
        assert(test_sd.CLKCR.value==clk && (clk&SDMMC_CLKCR_HWFC_EN));
        assert(number_of(17)==(count==1U || count==513U));
        assert(number_of(18)==(count>1U));
        assert(stop_count==(count>1U));
        assert(!number_of(23) && !number_of(24) && !number_of(25));
        for(uint32_t i=0;i<count*128U;i++) assert(load_word(destination+4U*i)==data_word(100,i));
        for(uint32_t i=0;i<4;i++) assert((destination-4)[i]==0xA5 && destination[count*512U+i]==0xA5);
        assert(sd_deinit(&c)==SD_OK && !c.controller_owned);
    }
    { auto c=read_card();c.ocr=0;
      assert(sd_read_blocks(&c,19,destination,2)==SD_OK);
      for(size_t i=0;i<commands.size();i++) if(commands[i]==18) assert(arguments[i]==19U*512U);
    }
    { auto c=read_card();c.sector_count=102;stop_response_bits=1U<<31;
      assert(sd_read_blocks(&c,100,destination,2)==SD_OK && c.media_idle);
    }
    { auto c=read_card();stop_response_bits=1U<<31;
      assert(sd_read_blocks(&c,100,destination,2)==SD_ERR_CARD && c.error==SD_ERR_CARD);
    }
    for(unsigned failure=0;failure<9;failure++) {
        auto c=read_card();uint32_t expected=0;
        switch(failure) {
        case 0:data_error_at=512;expected=SD_ERR_DATA;break;
        case 1:dma_error_at=512;expected=SD_ERR_DMA;break;
        case 2:dma_final_error=SDMMC_STA_IDMATE;expected=SD_ERR_DMA;break;
        case 3:dma_final_error=SDMMC_STA_DCRCFAIL;expected=SD_ERR_DATA;break;
        case 4:dma_residual=4;expected=SD_ERR_LENGTH;break;
        case 5:dma_stalled=true;expected=SD_ERR_DATA_TIMEOUT;break;
        case 6:command_error=18;expected=SD_ERR_COMMAND_TIMEOUT;break;
        case 7:stop_completion_error=SDMMC_STA_DTIMEOUT;stop_busy_polls=3;expected=SD_ERR_DATA;break;
        case 8:stop_completion_error=SDMMC_STA_DCRCFAIL;stop_busy_polls=3;expected=SD_ERR_DATA;break;
        }
        assert(sd_read_blocks(&c,100,destination,512)==(int)expected);
        assert(c.error==expected && !c.read_sectors && !dma_fifo_accesses && !fifo_resets);
        assert(c.error_stage==SD_STAGE_READ && !dctrl_active_writes);
        assert(!test_sd.IDMACTRL.value); /* successful modeled DMA abort, not a success result */
    }
    { auto c=read_card();dma_error_at=0;dma_abort_stuck=true;
      assert(sd_read_blocks(&c,100,destination,512)==SD_ERR_DMA);
      assert(!c.read_sectors && !c.media_idle && c.controller_owned && c.cleanup_error);
      assert(test_sd.IDMACTRL.value && !dma_fifo_accesses && !fifo_resets);
    }
    for(uintptr_t address: {uintptr_t(0x34200001U),uintptr_t(0x33FFFFFCU),uintptr_t(0x343FFF00U)}) {
        auto c=read_card();
        assert(sd_read_blocks(&c,0,reinterpret_cast<void *>(address),1)==SD_ERR_ARGUMENT);
        assert(commands.empty() && !test_sd.IDMACTRL.value);
    }
    for(unsigned failure=0;failure<4;failure++) {
        auto c=read_card();uint32_t expected=SD_ERR_SECURITY;
        if(failure==0) {test_scb.CCR.value=SCB_CCR_DC_Msk;expected=SD_ERR_CACHE;}
        if(failure==1) test_rcc.AHB3ENR.value=0;
        if(failure==2) test_rif.RIMC_ATTRx[3].value=0;
        if(failure==3) test_rif.RISC_SECCFGRx[1].value=0;
        assert(sd_read_blocks(&c,100,destination,512)==(int)expected);
        assert(commands.empty() && !test_sd.IDMACTRL.value && c.error_stage==SD_STAGE_READ);
    }
    { auto c=read_card();c.sector_count=101;
      assert(sd_read_blocks(&c,100,destination,2)==SD_ERR_CAPACITY && commands.empty());
    }
    { auto c=read_card();test_dwt.CYCCNT.value=0xFFF00000U;
      assert(sd_read_blocks(&c,100,destination,512)==SD_OK);
      assert(c.read_sectors==512 && c.media_idle);
    }
    { auto c=read_card();test_rcc.AHB5ENR.value&=~RCC_AHB5ENR_SDMMC2EN;
      assert(sd_read_blocks(&c,100,destination,512)==SD_ERR_CLOCK && commands.empty());
    }
    { auto c=read_card();test_sd.IDMACTRL.value=SDMMC_IDMA_IDMAEN;
      assert(sd_read_blocks(&c,100,destination,1)!=SD_OK);
      assert(!number_of(17) && !number_of(18) && test_sd.IDMACTRL.value);
    }
#ifdef _WIN32
    assert(VirtualFree(stream_memory,0,MEM_RELEASE));
#else
    assert(!munmap(stream_memory,4U*1024U*1024U));
#endif
    puts("IDMA read protocol cases passed");return 0;
}
