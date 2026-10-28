#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

static sd_card_t diagnostic_card()
{
    auto c=reset_init_model();stream_time=true;
    assert(sd_init(&c,25000000U)==SD_OK);
    assert(sd_read_diagnostics.magic==0x31445253U && sd_read_diagnostics.version==1U);
    assert(!sd_read_diagnostics.captured && sd_read_diagnostics.mode==0xFFFFFFFFU);
    commands.clear();arguments.clear();return c;
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
    { auto c=diagnostic_card();memset(destination-4,0xA5,520);
      assert(sd_read_blocks(&c,0,destination,1)==SD_OK);
      assert(sd_read_diagnostics.captured==1 && sd_read_diagnostics.mode==SD_IDMA_READ);
      assert(sd_read_diagnostics.lba==0 && sd_read_diagnostics.count==1);
      assert(sd_read_diagnostics.destination==0x34200000U && sd_read_diagnostics.requested_bytes==512);
      assert(sd_read_diagnostics.words==128 && !sd_read_diagnostics.result && !sd_read_diagnostics.dcount);
      assert(sd_read_diagnostics.sta&SDMMC_STA_DATAEND);
      assert(sd_read_diagnostics.idmactrl==(SD_IDMA_READ?SDMMC_IDMA_IDMAEN:0U));
      assert(sd_read_diagnostics.clkcr==0x34003U && sd_read_diagnostics.dctrl&SDMMC_DCTRL_DTDIR);
      for(unsigned n=0;n<128;n++) assert(load_word(destination+4*n)==data_word(0,n));
      for(unsigned n=0;n<4;n++) assert(destination[-4+int(n)]==0xA5 && destination[512+n]==0xA5);
      uint8_t retained[64];memcpy(retained,(const void *)&sd_read_diagnostics,64);
      assert(sd_deinit(&c)==SD_OK);
      assert(!memcmp(retained,(const void *)&sd_read_diagnostics,64));
      assert(sd_read_blocks(&c,3,destination,1)==SD_ERR_STATE);
      assert(!sd_read_diagnostics.captured && sd_read_diagnostics.mode==0xFFFFFFFFU);
    }
    { auto c=diagnostic_card();memset(destination,0xA5,512);
#if SD_IDMA_READ
      dma_final_error=SDMMC_STA_DCRCFAIL;
#else
      data_error_at=32;
#endif
      assert(sd_read_blocks(&c,0,destination,1)==SD_ERR_DATA);
      assert(sd_read_diagnostics.captured && sd_read_diagnostics.mode==SD_IDMA_READ);
      assert(sd_read_diagnostics.result==SD_ERR_DATA && sd_read_diagnostics.sta&SDMMC_STA_DCRCFAIL);
      assert(!c.read_sectors && c.error==SD_ERR_DATA);
      assert(!dma_fifo_accesses);
      /* Existing PIO abort resets its stopped FIFO; IDMA abort must not.
       * Diagnostics run before this established cleanup and add no drain. */
      assert(fifo_resets==(SD_IDMA_READ?0U:1U));
#if SD_IDMA_READ
      /* Untrusted destination may contain every byte despite words=0/error. */
      assert(sd_read_diagnostics.idmactrl==SDMMC_IDMA_IDMAEN && !sd_read_diagnostics.words);
      for(unsigned n=0;n<128;n++) assert(load_word(destination+4*n)==data_word(0,n));
#else
      assert(sd_read_diagnostics.words==32 && sd_read_diagnostics.dcount==384);
      for(unsigned n=0;n<32;n++) assert(load_word(destination+4*n)==data_word(0,n));
      for(unsigned n=128;n<512;n++) assert(destination[n]==0xA5);
#endif
    }
    { auto c=diagnostic_card();memset(destination,0xA5,512);command_error=17;
      assert(sd_read_blocks(&c,0,destination,1)==SD_ERR_COMMAND_TIMEOUT);
      assert(sd_read_diagnostics.captured && sd_read_diagnostics.mode==SD_IDMA_READ);
      assert(sd_read_diagnostics.result==SD_ERR_COMMAND_TIMEOUT && !sd_read_diagnostics.words);
      assert(sd_read_diagnostics.sta&SDMMC_STA_CTIMEOUT);
      for(unsigned n=0;n<512;n++) assert(destination[n]==0xA5);
    }
    { auto c=diagnostic_card();test_rcc.AHB5ENR.value&=~RCC_AHB5ENR_SDMMC2EN;
      /* Model asserts on every gated SDMMC access. Both public admission and
       * the observer itself must return without any such access. */
      assert(sd_read_blocks(&c,0,destination,1)==SD_ERR_CLOCK && commands.empty());
      assert(!sd_read_diagnostics.captured);
      read_diagnostics_snapshot(&c,0,0,destination,1,0,0,SD_ERR_CLOCK);
      assert(!sd_read_diagnostics.captured);
    }
    { auto c=diagnostic_card();c.controller_owned=0;
      read_diagnostics_snapshot(&c,0,0,destination,1,0,0,SD_ERR_STATE);
      assert(!sd_read_diagnostics.captured);
    }
    { auto c=diagnostic_card();assert(sd_read_blocks(&c,0,destination,1)==SD_OK);
      /* A later failed init must not leave a previous READ looking current. */
      assert(sd_init(nullptr,25000000U)==SD_ERR_ARGUMENT);
      assert(!sd_read_diagnostics.captured && sd_read_diagnostics.mode==0xFFFFFFFFU);
    }
    std::puts("SD read diagnostics protocol cases passed");
}
