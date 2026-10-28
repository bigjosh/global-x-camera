#define main historical_protocol_main
#include "test_sd_driver.cpp"
#undef main

#if SD_CLK_GPIO_SPEED == -1
#error "CLK slew tests require an explicit speed"
#endif

static void check_pins()
{
    const uint32_t expected=(0xFF3U&~0x30U)|(uint32_t(SD_CLK_GPIO_SPEED)<<4);
    assert(sd_clk_gpio_proof.magic==0x314B4C43U && sd_clk_gpio_proof.version==1U);
    assert(sd_clk_gpio_proof.requested_speed==SD_CLK_GPIO_SPEED);
    assert(sd_clk_gpio_proof.clk_mask==0x30U && sd_clk_gpio_proof.c_mask==0xFF3U);
    assert(sd_clk_gpio_proof.e_mask==0x300U && sd_clk_gpio_proof.applied==1U);
    assert(sd_clk_gpio_proof.c_before==0xA5A5A5A5U && sd_clk_gpio_proof.e_before==0x5A5A5A5AU);
    assert((sd_clk_gpio_proof.c_configured&0xFF3U)==0xFF3U);
    assert(!((sd_clk_gpio_proof.c_after^sd_clk_gpio_proof.c_configured)&~0x30U));
    assert(sd_clk_gpio_proof.c_after==test_gpio_c.OSPEEDR.value);
    assert(sd_clk_gpio_proof.e_after==test_gpio_e.OSPEEDR.value);
    assert((test_gpio_c.OSPEEDR.value&0xFF3U)==expected);
    assert((test_gpio_e.OSPEEDR.value&0x300U)==0x300U);
    assert(!((test_gpio_c.OSPEEDR.value^0xA5A5A5A5U)&~0xFF3U));
    assert(!((test_gpio_e.OSPEEDR.value^0x5A5A5A5AU)&~0x300U));
    /* Relative to the speed3 control, exactly PC2's two speed bits may differ. */
    assert(!((expected^0xFF3U)&~0x30U));
    assert(!compensation_reads && !compensation_writes);
    assert(test_sd.CLKCR.value==(3U|SDMMC_CLKCR_HWFC_EN|WIDTH_BITS|SDMMC_CLKCR_NEGEDGE));
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
    for(unsigned mode=0;mode<2;mode++) {
        auto c=reset_init_model();stream_time=true;
        assert(sd_init(&c,25000000U)==SD_OK);
        check_pins();
        assert(c.initialized && c.media_idle && sd_bus_width_proof.negotiated_width==4U);
        assert(sd_startup_proof.train_hz==100000U && sd_startup_proof.run_hz==25000000U);
        assert(sd_startup_proof.train_cycles>=400000U && sd_startup_proof.train_cycles<404000U);
        assert(sd_startup_proof.run_settle_cycles>=400U && sd_startup_proof.run_settle_cycles<4000U);
        output.clear();commands.clear();arguments.clear();
        if(mode==0) {
            const auto *buffer=reinterpret_cast<const void *>(uintptr_t(0x34000000U));
            assert(sd_write_blocks_dma_preerase(&c,100,buffer,3730)==SD_OK);
            assert(output.size()==3730U*128U);
            for(unsigned i=0;i<output.size();i++) assert(output[i]==load_word(dma_memory.data()+i*4U));
        } else {
            stream_check=true;
            StreamSource source{3730U*512U,512U,4U,9U,0xFFFFFFFFU,false};
            sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
            const auto *buffer=reinterpret_cast<const void *>(uintptr_t(0x3400000CU));
            assert(sd_write_blocks_stream_preerase(&c,100,buffer,3730,&stream)==SD_OK);
            assert(output.size()==3730U*128U);
            for(unsigned i=0;i<output.size();i++) assert(output[i]==load_word(stream_memory+12U+i*4U));
        }
        assert(c.written_sectors==3730U && c.media_idle && !c.error && !c.cleanup_error);
        assert(number_of(25)==1 && number_of(12)==1 && number_of(23)==1);
        check_pins();
        /* Full-slot reception through ordinary PIO. The model generates the
         * expected receive words; this is not a physical-card round trip. */
        stream_check=false;
        std::vector<uint8_t> read(3730U*512U);
        assert(sd_read_blocks(&c,100,read.data(),3730)==SD_OK);
        assert(c.read_sectors==3730U && c.media_idle && !c.error && !c.cleanup_error);
        check_pins();
        const uint32_t saved_c=sd_clk_gpio_proof.c_after,saved_e=sd_clk_gpio_proof.e_after;
        assert(sd_deinit(&c)==SD_OK && !c.initialized && !c.controller_owned && c.media_idle);
        assert(sd_clk_gpio_proof.applied==1U && sd_clk_gpio_proof.c_after==saved_c && sd_clk_gpio_proof.e_after==saved_e);
    }
    for(unsigned fault_kind=1;fault_kind<=4;fault_kind++) {
        auto c=reset_init_model();stream_time=true;bad_gpio_speed_write=fault_kind;
        assert(sd_init(&c,25000000U)==SD_ERR_GPIO);
        assert(!c.initialized && !sd_clk_gpio_proof.applied);
        if(fault_kind==1 || fault_kind==3) assert(commands.empty() && !c.controller_owned);
    }
    for(uint32_t bad_hz:{100000U,12500000U,50000000U}) {
        auto c=reset_init_model();
        assert(sd_init(&c,bad_hz)==SD_ERR_ARGUMENT && commands.empty());
        assert(!sd_clk_gpio_proof.applied && !sd_clk_gpio_proof.c_configured);
    }
    { auto c=reset_init_model();drop_negedge_write=true;
      assert(sd_init(&c,25000000U)==SD_ERR_CLOCK && commands.empty()); }
    { auto c=reset_init_model();drop_controller_gate=true;
      assert(sd_init(&c,25000000U)==SD_ERR_CLOCK && commands.empty()); }
    std::puts("SD CLK-only slew protocol cases passed");
}
