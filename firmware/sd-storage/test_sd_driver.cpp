#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#include "stm32n657xx.h"

extern "C" unsigned sd_hook_calls;
SDMMC_TypeDef test_sd{};
MockRcc test_rcc{};
MockGpio test_gpio_c{},test_gpio_e{};
MockPwr test_pwr{};
MockDwt test_dwt{};
MockDebug test_debug{};
MockDbgMcu test_dbgmcu{};
MockScb test_scb{};
MockRif test_rif{};
MockSysTick test_systick{};
uint32_t test_primask,test_basepri,test_faultmask;

static std::vector<uint32_t> commands, arguments, output;
static uint32_t words, expected_words, current_lba, operation, stop_count, fifo_resets;
static uint32_t data_error_at, busy_polls, command_error, late_card_error;
static uint32_t app_prefix_r1, app_preerase_r1;
static uint32_t erase_busy_polls;
static bool erase_active,erase_host_timeout;
static uint64_t modeled_cycles,erase_start_cycles;
static uint32_t erase_hz,erase_timer;
static uint8_t scr_bytes[8];
static uint32_t abort_tail_end;
static uint32_t tx_sent, tx_start_words, tx_max_occupancy;
static bool tx_started;
static bool waiting_for_stop, permanent_busy, abort_pending;
static std::vector<uint8_t> dma_memory;
static uint32_t dma_error_at, dma_final_error, dma_residual, dma_fifo_accesses;
static bool dma_stalled, dma_abort_stuck;
static uint32_t milliseconds,wfi_calls;
static bool sleep_model,wfi_immediate,wfi_change_context;
static uint8_t *stream_memory;
static bool stream_check,stream_time;
static uint32_t stream_published,stream_calls,stream_failure_at,stream_modeled_gap;
static uint32_t stream_slow_at,stream_words_before_slow;

static uint32_t test_milliseconds(void) { return milliseconds; }
void test_wfi(void)
{
    ++wfi_calls;
    if(!wfi_immediate) ++milliseconds;
    if(wfi_change_context) test_primask=1;
}

static uint32_t data_word(uint32_t lba, uint32_t index)
{
    uint32_t result=0;
    for(unsigned byte=0;byte<4;++byte)
        result|=((lba*17U+(index*4U+byte)*5U)&255U)<<(byte*8);
    return result;
}

static void command_write(uint32_t value)
{
    if (!(value&SDMMC_CMD_CPSMEN)) return;
    uint32_t index=value&63U;
    commands.push_back(index); arguments.push_back(test_sd.ARG.value);
    test_sd.RESPCMD.value=index;
    test_sd.RESP1.value=0x900;
    test_sd.STA.value|=SDMMC_STA_CMDREND;
    if (index==command_error) {
        test_sd.STA.value=SDMMC_STA_CTIMEOUT;
        return;
    }
    if (index==55) test_sd.RESP1.value=app_prefix_r1;
    else if (index==23) {
        assert(commands.size()>=2 && commands[commands.size()-2]==55);
        assert(!test_sd.IDMACTRL.value && !operation);
        test_sd.RESP1.value=app_preerase_r1;
    } else if (index==38) {
        busy_polls=erase_busy_polls;erase_active=true;erase_host_timeout=false;
        erase_start_cycles=modeled_cycles;
        erase_hz=150000000U/(2U*(test_sd.CLKCR.value&SDMMC_CLKCR_CLKDIV));
        erase_timer=test_sd.DTIMER.value;
    }
    else if (index==17 || index==18 || index==24 || index==25 || index==51) {
        assert(value&SDMMC_CMD_CMDTRANS);
        assert(!(value&SDMMC_CMD_CMDSTOP));
        operation=index; words=0; expected_words=test_sd.DLEN.value/4;
        test_sd.DCOUNT.value=test_sd.DLEN.value;
        tx_sent=0; tx_started=false; tx_start_words=0; tx_max_occupancy=0;
        current_lba=test_sd.ARG.value;
        waiting_for_stop=index==18 || index==25;
        if(index==51) test_sd.RESP1.value=0x920;
    } else if (index==12) {
        assert(value&SDMMC_CMD_CMDSTOP);
        assert(!(value&SDMMC_CMD_CMDTRANS));
        ++stop_count; waiting_for_stop=false;
        if (test_sd.IDMACTRL.value && !dma_abort_stuck) {
            /* RM0486 30.6.2: IDMA hardware owns the abort FIFO cleanup. */
            operation=0;
            test_sd.STA.value=SDMMC_STA_CMDREND|SDMMC_STA_DABORT;
        } else if (operation && words<expected_words) {
            /* Pending TX data deliberately keeps DPSM active until FIFORST. */
            abort_pending=true;
            abort_tail_end=words+16U;
            if (abort_tail_end>expected_words) abort_tail_end=expected_words;
            test_sd.STA.value=SDMMC_STA_CMDREND;
        } else {
            operation=0;
            test_sd.STA.value=SDMMC_STA_CMDREND|SDMMC_STA_DABORT;
        }
    } else if (index==13) {
        if (permanent_busy || busy_polls || waiting_for_stop) {
            test_sd.RESP1.value=0xE00;
            if (busy_polls) --busy_polls;
            if(erase_active) test_gpio_c.IDR.value&=~(1U<<4);
        } else if (late_card_error && !output.empty())
            test_sd.RESP1.value=0x900|(1U<<19);
        else if(erase_active) test_gpio_c.IDR.value|=1U<<4;
    }
}

MockReg::operator uint32_t() const
{
    if (this==&test_dbgmcu.CR) {
        assert(test_rcc.MISCENR.value&RCC_MISCENR_DBGEN);
        assert(!(test_rcc.MISCRSTR.value&RCC_MISCRSTR_DBGRST));
    }
    if (this==&test_dwt.CYCCNT) {
        /* Active DMA wait uses 1us reads; WFI advances wall time only. */
        uint32_t increment=((sleep_model && test_sd.IDMACTRL.value)||stream_time)?400U:400000U;
        test_dwt.CYCCNT.value+=increment;modeled_cycles+=increment;
        return value;
    }
    if (this==&test_sd.STA) {
        uint32_t state=value;
        if(erase_active) {
            /* R1b timeout latches the host in Busy even after physical DAT0
             * rises and CMD13 reports TRANSFER. This matches RM0486 Table220. */
            if((modeled_cycles-erase_start_cycles)*erase_hz/400000000ULL>=erase_timer)
                erase_host_timeout=true;
            if(erase_host_timeout)
                return state|SDMMC_STA_DPSMACT|SDMMC_STA_BUSYD0|SDMMC_STA_DTIMEOUT;
            if(busy_polls || permanent_busy)
                return state|SDMMC_STA_DPSMACT|SDMMC_STA_BUSYD0;
            erase_active=false;test_gpio_c.IDR.value|=1U<<4;state|=SDMMC_STA_BUSYD0END;
        }
        if (operation) {
            if (test_sd.IDMACTRL.value) {
                assert(operation==24 || operation==25);
                if (dma_abort_stuck && abort_pending) return state|SDMMC_STA_DPSMACT;
                if (words>=dma_error_at) return state|SDMMC_STA_IDMATE|SDMMC_STA_TXUNDERR|SDMMC_STA_DPSMACT;
                if (dma_stalled) return state|SDMMC_STA_DPSMACT;
                uint32_t offset=test_sd.IDMABASER.value-0x34000000U;
                assert(offset+expected_words*4<=dma_memory.size());
                for(unsigned n=0;n<256 && words<expected_words;++n) {
                    uint32_t v=0;
                    for(unsigned b=0;b<4;++b) v|=uint32_t(dma_memory[offset+words*4+b])<<(b*8);
                    output.push_back(v); ++words;
                }
                test_sd.DCOUNT.value=(expected_words-words)*4+dma_residual;
                if (words==expected_words) return state|SDMMC_STA_DATAEND|dma_final_error;
                return state|SDMMC_STA_DPSMACT;
            }
            if (abort_pending) {
                state|=SDMMC_STA_DPSMACT;
                if ((operation==17 || operation==18 || operation==51) && words>=abort_tail_end)
                    state|=SDMMC_STA_RXFIFOE;
                return state;
            }
            if (words>=data_error_at) return state|SDMMC_STA_DCRCFAIL|SDMMC_STA_DPSMACT;
            if (operation==24 || operation==25) {
                /* RM0486: 256-word FIFO, half-empty at <=128 occupied.
                 * BUSSPEED=0 does not launch before FIFO full or all DLEN
                 * bytes are queued. Drain only after that startup event. */
                if (!tx_started && (words-tx_sent==256 || words==expected_words)) {
                    tx_started=true; tx_start_words=words;
                }
                if (tx_started && tx_sent<words) {
                    uint32_t drain=words-tx_sent;
                    if (drain>16) drain=16;
                    tx_sent+=drain;
                }
                test_sd.DCOUNT.value=(expected_words-tx_sent)*4;
                if(tx_started && tx_sent==words && words<expected_words) {
                    if(!(test_sd.CLKCR.value&SDMMC_CLKCR_HWFC_EN)) return state|SDMMC_STA_TXUNDERR|SDMMC_STA_DPSMACT;
                    ++stream_modeled_gap;
                }
                if (tx_sent==expected_words) return state|SDMMC_STA_DATAEND;
                state|=SDMMC_STA_DPSMACT;
                if (words-tx_sent<=128) state|=SDMMC_STA_TXFIFOHE;
                if (words-tx_sent==256) state|=SDMMC_STA_TXFIFOF;
            } else {
                if (words==expected_words) return state|SDMMC_STA_DATAEND;
                state|=SDMMC_STA_DPSMACT;
                if (expected_words-words>=128) state|=SDMMC_STA_RXFIFOHF;
            }
        }
        return state;
    }
    if (this==&test_sd.FIFO) {
        if (test_sd.IDMACTRL.value) ++dma_fifo_accesses;
        assert(!test_sd.IDMACTRL.value);
        assert(operation==17 || operation==18 || operation==51);
        assert(words<expected_words); /* catches any read after DATAEND */
        uint32_t v=data_word(current_lba,words);
        if(operation==51) {
            v=0;for(unsigned b=0;b<4;b++) v|=uint32_t(scr_bytes[words*4+b])<<(8*b);
        }
        ++words;
        return v;
    }
    return value;
}

MockReg& MockReg::operator=(uint32_t input)
{
    if(this==&test_sd.DTIMER || this==&test_sd.CLKCR || this==&test_sd.DLEN)
        assert(!(uint32_t(test_sd.STA)&(SDMMC_STA_DPSMACT|SDMMC_STA_CPSMACT)));
    value=input;
    if (this==&test_sd.ICR) test_sd.STA.value&=~input;
    else if (this==&test_sd.CMD) {
        command_write(input);
        value&=~SDMMC_CMD_CPSMEN;
    } else if (this==&test_sd.FIFO) {
        if (test_sd.IDMACTRL.value) ++dma_fifo_accesses;
        assert(!test_sd.IDMACTRL.value);
        assert(operation==24 || operation==25);
        assert(words<expected_words);
        assert(words-tx_sent<256);
        if(stream_check) assert(words*4<(stream_published/512U)*512U);
        output.push_back(input); ++words;
        if (words-tx_sent>tx_max_occupancy) tx_max_occupancy=words-tx_sent;
    } else if (this==&test_sd.DCTRL && (input&SDMMC_DCTRL_FIFORST)) {
        assert(uint32_t(test_sd.STA)&SDMMC_STA_DPSMACT);
        assert(!test_sd.IDMACTRL.value);
        ++fifo_resets; operation=0; abort_pending=false;
        test_sd.STA.value|=SDMMC_STA_DABORT;
        value&=~SDMMC_DCTRL_FIFORST;
    } else if (this==&test_sd.IDMACTRL) {
        assert(!operation || words==expected_words); /* IDMAEN writable only idle. */
    } else if (this==&test_rcc.AHB5ENCR) test_rcc.AHB5ENR.value&=~input;
    return *this;
}
MockReg& MockReg::operator|=(uint32_t input) {return *this=uint32_t(*this)|input;}
MockReg& MockReg::operator&=(uint32_t input) {return *this=uint32_t(*this)&input;}

extern "C" {
#include "sd_card.c"
}

static sd_card_t reset_model()
{
    test_sd={}; test_rcc={}; test_gpio_c={}; test_gpio_e={};
    test_pwr={}; test_dwt={}; test_debug={}; test_dbgmcu={};
    test_scb={}; test_rif={};
    test_systick={}; test_primask=test_basepri=test_faultmask=0;
    milliseconds=wfi_calls=0; sleep_model=wfi_immediate=wfi_change_context=false;
    commands.clear(); arguments.clear(); output.clear();
    words=0; expected_words=0; current_lba=0; operation=0; stop_count=0; fifo_resets=0;
    data_error_at=0xFFFFFFFFU; busy_polls=0; command_error=0xFFFFFFFFU;
    app_prefix_r1=app_preerase_r1=0x920U;
    erase_busy_polls=0;
    erase_active=erase_host_timeout=false;modeled_cycles=erase_start_cycles=0;
    erase_hz=erase_timer=0;
    memset(scr_bytes,0,sizeof(scr_bytes));scr_bytes[0]=2;scr_bytes[1]=0x85;
    stream_check=stream_time=false;stream_published=stream_calls=stream_modeled_gap=0;
    stream_failure_at=0xFFFFFFFFU;
    stream_slow_at=0xFFFFFFFFU;stream_words_before_slow=0;
    late_card_error=0; waiting_for_stop=false; permanent_busy=false;
    abort_pending=false; abort_tail_end=0;
    tx_sent=0; tx_started=false; tx_start_words=0; tx_max_occupancy=0;
    dma_error_at=0xFFFFFFFFU; dma_final_error=0; dma_residual=0; dma_fifo_accesses=0;
    dma_stalled=false; dma_abort_stuck=false;
    dma_memory.resize(4097U*512U);
    for(unsigned n=0;n<dma_memory.size();++n) dma_memory[n]=uint8_t(n*7U+19U);
    test_rcc.AHB3ENR.value=RCC_AHB3ENR_RIFSCEN;
    test_rif.RIMC_ATTRx[3].value=0x310;
    test_rif.RISC_SECCFGRx[1].value=1U<<22;
    test_systick.CTRL.value=7; test_systick.LOAD.value=399999;
    test_rcc.MEMLPENR.value=0x18FU;
    test_rcc.AHB3LPENR.value=RCC_AHB3LPENR_RIFSCLPEN|RCC_AHB3LPENR_RISAFLPEN;
    test_rcc.AHB5LPENR.value=RCC_AHB5LPENR_SDMMC2LPEN;
    test_rcc.BUSLPENR.value=RCC_BUSLPENR_ACLKNLPEN|RCC_BUSLPENR_ACLKNCLPEN;
    test_rcc.MISCENR.value=RCC_MISCENR_DBGEN;
    test_gpio_c.IDR.value=1U<<4;
    test_sd.CLKCR.value=SDMMC_CLKCR_HWFC_EN|3U;
    sd_card_t card{};
    card.initialized=1; card.controller_owned=1; card.media_idle=1;
    card.clock_hz=25000000; card.rca=0x12340000; card.ocr=1U<<30;
    card.sector_count=122507264;
    return card;
}

static uint32_t number_of(uint32_t command)
{
    uint32_t n=0;
    for(auto v:commands) n+=v==command;
    return n;
}

struct StreamSource {uint32_t total,initial,second_at,all_at,fail_at;bool regress;};
static int publish_stream(void *context,uint32_t *available)
{
    auto *source=static_cast<StreamSource *>(context);++stream_calls;
    if(stream_calls==stream_slow_at) {
        stream_words_before_slow=uint32_t(output.size());
        test_dwt.CYCCNT.value+=1240000000U; /* 3.1 s bounded fault path */
    }
    if(stream_calls==source->fail_at) return 0x62;
    uint32_t next=source->initial;
    if(stream_calls>=source->second_at) next=1024;
    if(stream_calls>=source->all_at) next=source->total;
    if(source->regress && stream_calls>1) next=0;
    if(next>stream_published && next<=source->total) {
        for(uint32_t i=stream_published;i<next;i++) {
            stream_memory[12U+i]=uint8_t(i*11U+31U);
            dma_memory[12U+i]=stream_memory[12U+i];
        }
    }
    *available=next;stream_published=next;return 0;
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
    std::vector<uint8_t> bytes(65U*512U+3U);
    uint8_t *unaligned=bytes.data()+1;
    for(uint32_t i=0;i<65U*512U;++i) unaligned[i]=uint8_t(i*7U+3U);

    { auto c=reset_model();
      unsigned hook_before=sd_hook_calls;
      assert(sd_write_blocks(&c,10,unaligned,2)==SD_OK);
      assert(number_of(25)==1 && stop_count==1 && c.written_sectors==2);
      assert(fifo_resets==0);
      assert(output.size()==256 && c.media_idle);
      assert(tx_started && tx_start_words==256 && tx_sent==256);
      assert(tx_max_occupancy==256);
      for(uint32_t i=0;i<256;++i) assert(output[i]==load_word(unaligned+i*4));
      assert(sd_hook_calls>hook_before && sd_hook_calls-hook_before<32);
    }
    { auto c=reset_model();
      assert(sd_write_blocks(&c,10,unaligned,1)==SD_OK);
      assert(number_of(24)==1 && stop_count==0 && c.written_sectors==1);
      assert(tx_started && tx_start_words==128 && tx_sent==128);
    }
    { auto c=reset_model();
      assert(sd_read_blocks(&c,19,unaligned,2)==SD_OK);
      assert(number_of(18)==1 && stop_count==1 && c.read_sectors==2);
      for(uint32_t i=0;i<256;++i) assert(load_word(unaligned+i*4)==data_word(19,i));
    }
    { auto c=reset_model();
      assert(sd_read_blocks(&c,1,unaligned,1)==SD_OK);
      assert(stop_count==0 && c.transfer_sta==SDMMC_STA_DATAEND);
    }
    { auto c=reset_model();
      assert(sd_write_blocks(&c,100,unaligned,65)==SD_OK);
      assert(number_of(25)==1 && number_of(24)==1 && stop_count==1);
      assert(c.written_sectors==65 && output.size()==65U*128U);
    }
    { auto c=reset_model(); c.clock_hz=100000;
      assert(sd_read_blocks(&c,100,unaligned,64)==SD_OK);
      assert(number_of(18)==4 && stop_count==4 && c.read_sectors==64);
    }
    { auto c=reset_model(); data_error_at=32;
      assert(sd_write_blocks(&c,10,unaligned,2)==SD_ERR_DATA);
      assert(c.error==SD_ERR_DATA && c.error_stage==SD_STAGE_WRITE);
      assert(stop_count==1 && c.media_idle && !c.written_sectors);
      assert(fifo_resets==1);
      auto before=commands.size();
      assert(sd_write_blocks(&c,20,unaligned,1)==SD_ERR_DATA);
      assert(before==commands.size());
    }
    { auto c=reset_model(); command_error=25;
      assert(sd_write_blocks(&c,10,unaligned,2)==SD_ERR_COMMAND_TIMEOUT);
      assert(stop_count==1 && c.media_idle && !c.written_sectors);
    }
    { auto c=reset_model(); data_error_at=32;
      assert(sd_read_blocks(&c,10,unaligned,2)==SD_ERR_DATA);
      assert(stop_count==1 && fifo_resets==1 && words==48 && c.media_idle);
      assert(!c.read_sectors);
    }
    { auto c=reset_model(); data_error_at=32; command_error=12;
      assert(sd_write_blocks(&c,10,unaligned,2)==SD_ERR_DATA);
      assert(!c.media_idle && !c.written_sectors && !fifo_resets);
      assert(c.cleanup_error==SD_ERR_NOT_READY);
    }
    { auto c=reset_model(); late_card_error=1;
      assert(sd_write_blocks(&c,10,unaligned,1)==SD_ERR_CARD);
      assert(!c.media_idle && !c.written_sectors);
    }
    { auto c=reset_model(); permanent_busy=true;
      assert(sd_sync(&c)==SD_ERR_NOT_READY && !c.media_idle);
      assert(number_of(13)>1 && number_of(13)<2000);
    }
    { auto c=reset_model();
      assert(sd_write_blocks(&c,0xFFFFFFFFU,unaligned,2)==SD_ERR_CAPACITY);
      assert(commands.empty());
      assert(sd_write_blocks(nullptr,0,unaligned,1)==SD_ERR_ARGUMENT);
      auto d=reset_model(); d.initialized=0;
      assert(sd_read_blocks(&d,0,unaligned,1)==SD_ERR_STATE);
    }
    { auto c=reset_model();
      (void)c;
      test_sd.DLEN.value=4096;
      command_write(25|SDMMC_CMD_CPSMEN|SDMMC_CMD_CMDTRANS);
      /* Reproduce the original 16-word/HALF-empty policy, independently of
       * production transfer(): exactly144 words queued, none transmitted. */
      for(unsigned poll=0;poll<100;++poll) {
          if (uint32_t(test_sd.STA)&SDMMC_STA_TXFIFOHE)
              for(unsigned n=0;n<16;++n) test_sd.FIFO=0x11223344;
      }
      uint32_t sta=test_sd.STA;
      assert(words==144 && tx_sent==0 && !tx_started);
      assert((sta&SDMMC_STA_DPSMACT) && !(sta&SDMMC_STA_TXFIFOHE));
      assert(!(sta&(SDMMC_STA_TXFIFOF|SDMMC_STA_DATAEND)));
    }
    { auto c=reset_model();
      assert(sd_write_blocks(&c,10,unaligned,8)==SD_OK);
      assert(c.written_sectors==8 && tx_sent==1024 && tx_start_words==256);
      assert(tx_max_occupancy==256 && c.media_idle && stop_count==1);
    }
    const void *dma_buffer=reinterpret_cast<const void *>(uintptr_t(0x34000000U));
    { auto c=reset_model();
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_OK);
      assert(number_of(25)==1 && stop_count==1 && c.written_sectors==2);
      assert(c.media_idle && !test_sd.IDMACTRL.value && !dma_fifo_accesses && !fifo_resets);
      for(unsigned n=0;n<output.size();++n) assert(output[n]==load_word(dma_memory.data()+4*n));
    }
    { auto c=reset_model();
      assert(sd_write_blocks_dma(&c,10,dma_buffer,1)==SD_OK);
      assert(number_of(24)==1 && !stop_count && c.transfer_words==128);
    }
    { auto c=reset_model();
      assert(sd_write_blocks_dma(&c,10,dma_buffer,1025)==SD_OK);
      assert(number_of(25)==1 && number_of(24)==1 && c.written_sectors==1025);
      assert(stop_count==1 && output.size()==1025U*128U && c.media_idle);
      for(unsigned n=0;n<output.size();++n) assert(output[n]==load_word(dma_memory.data()+4*n));
    }
    { auto c=reset_model(); c.clock_hz=100000;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,32)==SD_OK);
      assert(number_of(25)==2 && stop_count==2 && c.written_sectors==32);
    }
    { auto c=reset_model();
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==SD_OK);
      const std::vector<uint32_t> wanted={13,55,23,25,12,13};
      const std::vector<uint32_t> args={c.rca,c.rca,3730,100,0,c.rca};
      assert(commands==wanted && arguments==args);
      assert(c.command_count==6 && stop_count==1 && !number_of(24));
      assert(c.written_sectors==3730 && c.transfer_words==3730U*128U);
      assert(c.media_idle && !test_sd.IDMACTRL.value && !dma_fifo_accesses && !fifo_resets);
      assert(output.size()==3730U*128U && test_sd.DLEN.value==3730U*512U);
      for(unsigned n=0;n<output.size();++n) assert(output[n]==load_word(dma_memory.data()+4*n));
    }
    { auto c=reset_model(); c.clock_hz=12500000;
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,4096)==SD_OK);
      assert(c.written_sectors==4096 && stop_count==1 && number_of(25)==1);
      assert(number_of(23)==1 && arguments[2]==4096 && c.media_idle);
    }
    for(unsigned scenario=0;scenario<9;++scenario) {
      auto c=reset_model(); const void *source=dma_buffer; uint32_t count=3730;
      const int expected[]={SD_ERR_ARGUMENT,SD_ERR_ARGUMENT,SD_ERR_CLOCK,
        SD_ERR_CACHE,SD_ERR_SECURITY,SD_ERR_SECURITY,SD_ERR_SECURITY,
        SD_ERR_ARGUMENT,SD_ERR_CAPACITY};
      switch(scenario) {
      case 0: count=1; break;
      case 1: count=4097; break;
      case 2: c.clock_hz=100000; break;
      case 3: test_scb.CCR.value=SCB_CCR_DC_Msk; break;
      case 4: test_rif.RIMC_ATTRx[3].value=0; break;
      case 5: test_rif.RISC_SECCFGRx[1].value=0; break;
      case 6: test_rcc.AHB3ENR.value=0; break;
      case 7: source=reinterpret_cast<void *>(uintptr_t(0x34300000U)); break;
      case 8: c.sector_count=100; break;
      }
      assert(sd_write_blocks_dma_preerase(&c,100,source,count)==expected[scenario]);
      assert(commands.empty() && output.empty() && !test_sd.IDMACTRL.value);
    }
    for(unsigned scenario=0;scenario<6;++scenario) {
      auto c=reset_model();
      const int expected[]={SD_ERR_UNSUPPORTED,SD_ERR_UNSUPPORTED,SD_ERR_CARD,
        SD_ERR_CARD,SD_ERR_COMMAND_TIMEOUT,SD_ERR_COMMAND_TIMEOUT};
      switch(scenario) {
      case 0: app_prefix_r1=0x900; break;
      case 1: app_preerase_r1=0x900; break;
      case 2: app_prefix_r1=0x920|(1U<<22); break;
      case 3: app_preerase_r1=0x920|(1U<<22); break;
      case 4: command_error=55; break;
      case 5: command_error=23; break;
      }
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==expected[scenario]);
      assert(c.error==uint32_t(expected[scenario]) && !c.media_idle);
      assert(!number_of(25) && !number_of(24) && !stop_count);
      assert(!c.written_sectors && output.empty() && !test_sd.IDMACTRL.value);
      assert(c.error_command==((scenario==0 || scenario==2 || scenario==4)?55U:23U));
      auto before=commands.size();
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==expected[scenario]);
      assert(commands.size()==before); /* first error remains latched */
    }
    { auto c=reset_model(); dma_error_at=256;
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==SD_ERR_DMA);
      assert(number_of(55)==1 && number_of(23)==1 && number_of(25)==1 && stop_count==1);
      assert(c.media_idle && !c.written_sectors && !test_sd.IDMACTRL.value);
      assert(!dma_fifo_accesses && !fifo_resets);
    }
    { auto c=reset_model(); command_error=25;
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==SD_ERR_COMMAND_TIMEOUT);
      assert(number_of(55)==1 && number_of(23)==1 && stop_count==1);
      assert(c.media_idle && !c.written_sectors && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model(); late_card_error=1;
      assert(sd_write_blocks_dma_preerase(&c,100,dma_buffer,3730)==SD_ERR_CARD);
      assert(stop_count==1 && !c.media_idle && !c.written_sectors);
      assert(!test_sd.IDMACTRL.value && output.size()==3730U*128U);
    }
    { auto c=reset_model(); dma_error_at=256;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,8)==SD_ERR_DMA);
      assert(c.media_idle && !c.written_sectors && !test_sd.IDMACTRL.value);
      assert(!dma_fifo_accesses && !fifo_resets && stop_count==1);
      auto before=commands.size();
      assert(sd_write_blocks_dma(&c,10,dma_buffer,1)==SD_ERR_DMA);
      assert(before==commands.size());
    }
    { auto c=reset_model(); dma_final_error=SDMMC_STA_IDMATE;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_DMA);
      assert(!c.written_sectors && c.media_idle && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model(); dma_stalled=true;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_DATA_TIMEOUT);
      assert(c.media_idle && !test_sd.IDMACTRL.value && !fifo_resets);
    }
    { auto c=reset_model(); dma_error_at=0; dma_abort_stuck=true;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_DMA);
      assert(!c.media_idle && !c.written_sectors && test_sd.IDMACTRL.value);
      assert(c.cleanup_error==SD_ERR_NOT_READY && !fifo_resets);
    }
    { auto c=reset_model(); command_error=25;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_COMMAND_TIMEOUT);
      assert(c.media_idle && !test_sd.IDMACTRL.value && !c.written_sectors);
    }
    { auto c=reset_model(); dma_residual=4;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_LENGTH);
      assert(c.media_idle && !c.written_sectors);
    }
    { auto c=reset_model(); test_scb.CCR.value=SCB_CCR_DC_Msk;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_CACHE);
      assert(commands.empty());
    }
    { auto c=reset_model(); test_rif.RIMC_ATTRx[3].value=0;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_SECURITY);
      assert(commands.empty());
      c=reset_model(); test_rcc.AHB3ENR.value=0;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_SECURITY);
      assert(commands.empty());
    }
    { auto c=reset_model(); test_rif.RISC_SECCFGRx[1].value=0;
      /* RIMC still requests secure CID1, but the peripheral's nonsecure
       * configuration port overrides that request. Refuse before CMD24/25. */
      assert(test_rif.RIMC_ATTRx[3].value==0x310);
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_SECURITY);
      assert(commands.empty() && output.empty() && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model();
      assert(sd_write_blocks_dma(&c,10,reinterpret_cast<void *>(uintptr_t(0x34000001U)),2)==SD_ERR_ARGUMENT);
      assert(commands.empty());
      c=reset_model();
      assert(sd_write_blocks_dma(&c,10,reinterpret_cast<void *>(uintptr_t(0x343FFF00U)),2)==SD_ERR_ARGUMENT);
      assert(commands.empty());
      c=reset_model();
      assert(sd_write_blocks_dma(&c,10,reinterpret_cast<void *>(uintptr_t(0x24000000U)),2)==SD_ERR_ARGUMENT);
      assert(commands.empty());
    }
    { auto c=reset_model(); c.sector_count=11;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_ERR_CAPACITY);
      assert(commands.empty());
    }
    { auto c=reset_model(); test_dwt.CYCCNT.value=0xFFF00000U;
      assert(sd_write_blocks_dma(&c,10,dma_buffer,2)==SD_OK);
      assert(c.media_idle && c.written_sectors==2);
    }
    { auto c=reset_model(); sleep_model=true;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,8,&wait)==SD_OK);
      assert(wait.wait_calls>0 && wait.wait_calls==wfi_calls);
      assert(wait.wall_ms==wait.wait_calls && wait.active_cycles<400000U);
      assert(!wait.immediate_wakes && !wait.context_faults && c.media_idle && !test_sd.IDMACTRL.value);
      auto previous=wait.wait_calls;
      assert(sd_write_blocks_dma_wait(&c,20,dma_buffer,8,&wait)==SD_OK);
      assert(wait.wait_calls>previous && wait.wall_ms==wait.wait_calls);
    }
    { auto c=reset_model(); sleep_model=true; dma_stalled=true;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,8,&wait)==SD_ERR_DATA_TIMEOUT);
      assert(wait.wall_ms==5000 && wait.wait_calls==5000);
      assert(wait.active_cycles<2000000000U && c.media_idle && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model(); sleep_model=true; dma_error_at=512;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,8,&wait)==SD_ERR_DMA);
      assert(wait.wait_calls && c.media_idle && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model(); sleep_model=true; milliseconds=0xFFFFFFFEU;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,16,&wait)==SD_OK);
      assert(wait.wall_ms==wait.wait_calls && milliseconds<0xFFFFFFFEU);
    }
    { auto c=reset_model(); sleep_model=true; wfi_immediate=true;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,8,&wait)==SD_OK);
      assert(wait.wait_calls && wait.immediate_wakes==wait.wait_calls && !wait.wall_ms);
    }
    { auto c=reset_model(); sleep_model=true; wfi_change_context=true;
      sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,32,&wait)==SD_ERR_WAIT);
      assert(wait.wait_calls==1 && wait.context_faults==SD_WAIT_PRIMASK && c.media_idle && !test_sd.IDMACTRL.value);
    }
    for(unsigned scenario=0;scenario<15;++scenario) {
      auto c=reset_model(); sd_dma_wait_t wait{}; wait.milliseconds=test_milliseconds;
      const uint32_t expected[]={SD_WAIT_PRIMASK,SD_WAIT_BASEPRI,SD_WAIT_FAULTMASK,
        SD_WAIT_DEEP_SLEEP,SD_WAIT_SLEEP_ON_EXIT,SD_WAIT_SYSTICK_CTRL,SD_WAIT_SYSTICK_LOAD,
        SD_WAIT_RAM_CLOCKS,SD_WAIT_SD_CLOCK,SD_WAIT_RIF_CLOCKS,SD_WAIT_BUS_CLOCKS,
        SD_WAIT_BUS_CLOCKS,SD_WAIT_DEBUG_ACCESS,SD_WAIT_DEBUG_ACCESS,SD_WAIT_DEBUG_SLEEP};
      switch(scenario) {
      case 0: test_primask=1; break;
      case 1: test_basepri=1; break;
      case 2: test_faultmask=1; break;
      case 3: test_scb.SCR.value=SCB_SCR_SLEEPDEEP_Msk; break;
      case 4: test_scb.SCR.value=SCB_SCR_SLEEPONEXIT_Msk; break;
      case 5: test_systick.CTRL.value=1; break;
      case 6: test_systick.LOAD.value=199999; break;
      case 7: test_rcc.MEMLPENR.value=0; break;
      case 8: test_rcc.AHB5LPENR.value=0; break;
      case 9: test_rcc.AHB3LPENR.value=0; break;
      case 10: test_rcc.BUSLPENR.value=1; break;
      case 11: test_rcc.BUSLPENR.value=2; break;
      case 12: test_rcc.MISCENR.value=0; break;
      case 13: test_rcc.MISCRSTR.value=RCC_MISCRSTR_DBGRST; break;
      case 14: test_dbgmcu.CR.value=DBGMCU_CR_DBG_SLEEP; break;
      }
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,2,&wait)==SD_ERR_WAIT);
      assert(commands.empty() && !wait.wait_calls && wait.context_faults==expected[scenario]);
    }
    { auto c=reset_model(); sd_dma_wait_t wait{};
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,2,&wait)==SD_ERR_WAIT);
      assert(commands.empty() && wait.context_faults==SD_WAIT_NO_CLOCK);
      assert(sd_write_blocks_dma_wait(&c,10,dma_buffer,2,nullptr)==SD_ERR_ARGUMENT);
    }
    { auto c=reset_model();sd_scr_t scr{};
      assert(sd_read_scr(&c,&scr)==SD_OK);
      const std::vector<uint32_t> expected={13,55,51,13};
      assert(commands==expected && !stop_count && scr.valid && scr.erased_byte==255);
      assert(memcmp(scr.bytes,scr_bytes,8)==0 && c.media_idle && !c.read_sectors);
      assert(test_sd.DLEN.value==8 && !test_sd.DCTRL.value);
    }
    { auto c=reset_model();sd_scr_t scr{};scr_bytes[1]=5;
      assert(sd_read_scr(&c,&scr)==SD_OK && scr.valid && !scr.erased_byte);
    }
    { auto c=reset_model();sd_scr_t scr{};scr_bytes[0]=0x12;
      assert(sd_read_scr(&c,&scr)==SD_ERR_UNSUPPORTED && !scr.valid);
    }
    { auto c=reset_model();sd_scr_t scr{};data_error_at=1;
      assert(sd_read_scr(&c,&scr)==SD_ERR_DATA && !scr.valid && !c.read_sectors);
    }
    { auto c=reset_model();sd_erase_t proof{};erase_busy_polls=5;
      test_sd.DTIMER.value=50000000U;
      assert(sd_erase_all(&c,10000,&proof)==SD_OK);
      assert(commands[0]==13 && commands[1]==32 && commands[2]==33 && commands[3]==38);
      assert(arguments[1]==0 && arguments[2]==c.sector_count-1 && arguments[3]==0);
      assert(proof.started && proof.completed && c.media_idle && proof.last_lba==c.sector_count-1);
      assert(!number_of(12) && !number_of(24) && !number_of(25) && !c.written_sectors);
      assert(erase_hz==100000U && erase_timer==1100000U && !erase_host_timeout);
      assert(c.clock_hz==25000000U && test_sd.CLKCR.value==(SDMMC_CLKCR_HWFC_EN|3U));
      assert(test_sd.DTIMER.value==50000000U && test_sd.DLEN.value==0);
    }
    { auto c=reset_model();sd_erase_t proof{};c.ocr=0;c.sector_count=4096;
      assert(sd_erase_all(&c,10000,&proof)==SD_OK && arguments[2]==4095U*512U);
    }
    { auto c=reset_model();sd_erase_t proof{};erase_busy_polls=4000;test_dwt.CYCCNT.value=0xFFF00000U;
      assert(sd_erase_all(&c,120000,&proof)==SD_OK && proof.elapsed_ms>11000 && proof.completed);
      assert(erase_hz==100000U && erase_timer==12100000U && !erase_host_timeout);
    }
    { auto c=reset_model();sd_erase_t proof{};erase_busy_polls=140000;
      assert(sd_erase_all(&c,600000,&proof)==SD_OK && proof.elapsed_ms>500000);
      assert(erase_timer==60100000U && proof.elapsed_ms<600000 && !erase_host_timeout);
      assert(c.clock_hz==25000000U && c.media_idle);
    }
    { auto c=reset_model();sd_erase_t proof{};erase_busy_polls=100000;
      assert(sd_erase_all(&c,1000,&proof)==SD_ERR_NOT_READY);
      assert(proof.started && !proof.completed && !c.media_idle && proof.elapsed_ms>=1000);
      assert(!number_of(12)); /* Do not abort/reset an uncertain erase. */
      assert(c.clock_hz==100000U && test_sd.CLKCR.value==(SDMMC_CLKCR_HWFC_EN|750U));
      assert(test_sd.DTIMER.value==200000U); /* no restore while busy */
    }
    { auto c=reset_model();sd_erase_t proof{};command_error=38;
      assert(sd_erase_all(&c,10000,&proof)==SD_ERR_COMMAND_TIMEOUT);
      assert(proof.started && !proof.completed && !c.media_idle && !number_of(12));
      assert(c.clock_hz==100000U); /* lost response may hide active erase */
    }
    { auto c=reset_model();sd_erase_t proof{};
      assert(sd_erase_all(&c,600001,&proof)==SD_ERR_ARGUMENT && commands.empty());
    }
    { auto c=reset_model();sd_erase_t proof{};test_sd.CLKCR.value|=SDMMC_CLKCR_DDR;
      assert(sd_erase_all(&c,600000,&proof)==SD_ERR_CLOCK);
      assert(!proof.started && !number_of(38) && c.clock_hz==25000000U);
    }
    { auto c=reset_model();erase_busy_polls=1000;test_sd.DTIMER.value=50000000U;
      assert(command(&c,38,0,RESP_R1,0)==SD_OK);
      modeled_cycles+=1200000000ULL; /* old inherited 2 s busy timer expires */
      assert(uint32_t(test_sd.STA)&SDMMC_STA_DTIMEOUT);
      busy_polls=0;
      assert(command(&c,13,c.rca,RESP_R1,0)==SD_OK && c.last_r1==0x900);
      assert(test_gpio_c.IDR.value&(1U<<4));
      assert((uint32_t(test_sd.STA)&(SDMMC_STA_DPSMACT|SDMMC_STA_DTIMEOUT))==
             (SDMMC_STA_DPSMACT|SDMMC_STA_DTIMEOUT));
    }
    { auto c=reset_model();stream_time=stream_check=true;
      StreamSource source{3730U*512U,512U,80U,220U,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      memset(stream_memory+12U,0xA5,source.total);
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,3730,&stream)==SD_OK);
      assert(stream.mode==SD_STREAM_PIO && stream.initial_available_bytes==512U);
      assert(stream.queued_bytes==source.total && stream.published_bytes==source.total);
      assert(stream.starved_polls && stream.max_wait_cycles && stream_modeled_gap);
      assert(number_of(25)==1 && number_of(23)==1 && arguments[2]==3730 && stop_count==1);
      assert(c.written_sectors==3730 && c.media_idle && !test_sd.IDMACTRL.value);
      assert(output.size()==3730U*128U);
      for(unsigned n=0;n<output.size();n++) assert(output[n]==load_word(stream_memory+12U+4U*n));
    }
    { auto c=reset_model();stream_time=true;
      StreamSource source{2048U,2048U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_OK);
      assert(stream.mode==SD_STREAM_IDMA && stream.initial_available_bytes==2048 && stream.queued_bytes==2048);
      assert(!dma_fifo_accesses && c.media_idle);
      for(unsigned n=0;n<output.size();n++) assert(output[n]==load_word(stream_memory+12U+4U*n));
    }
    { auto c=reset_model();stream_time=stream_check=true;
      StreamSource source{2048U,513U,100U,200U,30U,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_PRODUCER);
      assert(stream.producer_error==0x62 && stream.queued_bytes==512U);
      assert(c.media_idle && !c.written_sectors && stop_count==1 && !test_sd.IDMACTRL.value);
    }
    { auto c=reset_model();stream_time=true;
      StreamSource source{2048U,512U,100U,200U,0xFFFFFFFFU,true};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_PRODUCER);
      assert(stream.producer_error==0xFFFFFFFFU && c.media_idle && !c.written_sectors);
    }
    { auto c=reset_model();
      StreamSource source{2048U,0U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_DATA_TIMEOUT);
      assert(commands.empty() && !c.written_sectors && !stream.queued_bytes);
    }
    { auto c=reset_model();
      StreamSource source{2048U,512U,0xFFFFFFFFU,0xFFFFFFFFU,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_DATA_TIMEOUT);
      assert(number_of(25)==1 && stop_count==1 && !c.written_sectors && c.media_idle);
    }
    { auto c=reset_model();test_sd.CLKCR.value=3U;
      StreamSource source{2048U,512U,10U,20U,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_CLOCK);
      assert(commands.empty() && !stream.publication_calls);
    }
    for(uint32_t slow_at: {1U,2U,4U}) {
      auto c=reset_model();stream_time=stream_check=true;stream_slow_at=slow_at;
      StreamSource source{2048U,slow_at==2U?0U:512U,0xFFFFFFFFU,slow_at,0xFFFFFFFFU,false};
      sd_stream_t stream{};stream.publish=publish_stream;stream.context=&source;
      assert(sd_write_blocks_stream_preerase(&c,100,stream_memory+12U,4,&stream)==SD_ERR_DATA_TIMEOUT);
      /* A callback can publish a full buffer after spending >3 seconds in a
       * peripheral timeout. Its late tail must not enter the SD FIFO/IDMA. */
      assert(output.size()==stream_words_before_slow && !c.written_sectors);
      assert(stream.published_bytes<source.total && !test_sd.IDMACTRL.value);
      assert(c.media_idle);
      if(slow_at<=2U) assert(commands.empty() && !stop_count);
      else assert(number_of(25)==1 && stop_count==1);
    }
#ifdef _WIN32
    assert(VirtualFree(stream_memory,0,MEM_RELEASE));
#else
    assert(!munmap(stream_memory,4U*1024U*1024U));
#endif
    std::puts("protocol cases passed");
}
