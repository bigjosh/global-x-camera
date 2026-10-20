#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include "stm32n657xx.h"

extern "C" unsigned sd_hook_calls;
SDMMC_TypeDef test_sd{};
MockRcc test_rcc{};
MockGpio test_gpio_c{},test_gpio_e{};
MockPwr test_pwr{};
MockDwt test_dwt{};
MockDebug test_debug{};

static std::vector<uint32_t> commands, arguments, output;
static uint32_t words, expected_words, current_lba, operation, stop_count, fifo_resets;
static uint32_t data_error_at, busy_polls, command_error, late_card_error;
static uint32_t abort_tail_end;
static uint32_t tx_sent, tx_start_words, tx_max_occupancy;
static bool tx_started;
static bool waiting_for_stop, permanent_busy, abort_pending;

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
    if (index==17 || index==18 || index==24 || index==25) {
        assert(value&SDMMC_CMD_CMDTRANS);
        assert(!(value&SDMMC_CMD_CMDSTOP));
        operation=index; words=0; expected_words=test_sd.DLEN.value/4;
        tx_sent=0; tx_started=false; tx_start_words=0; tx_max_occupancy=0;
        current_lba=test_sd.ARG.value;
        waiting_for_stop=index==18 || index==25;
    } else if (index==12) {
        assert(value&SDMMC_CMD_CMDSTOP);
        assert(!(value&SDMMC_CMD_CMDTRANS));
        ++stop_count; waiting_for_stop=false;
        if (operation && words<expected_words) {
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
        } else if (late_card_error && !output.empty())
            test_sd.RESP1.value=0x900|(1U<<19);
    }
}

MockReg::operator uint32_t() const
{
    if (this==&test_dwt.CYCCNT) {
        test_dwt.CYCCNT.value+=400000; /* deterministic 1ms model steps */
        return value;
    }
    if (this==&test_sd.STA) {
        uint32_t state=value;
        if (operation) {
            if (abort_pending) {
                state|=SDMMC_STA_DPSMACT;
                if ((operation==17 || operation==18) && words>=abort_tail_end)
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
        assert(operation==17 || operation==18);
        assert(words<expected_words); /* catches any read after DATAEND */
        uint32_t v=data_word(current_lba,words);
        ++words;
        return v;
    }
    return value;
}

MockReg& MockReg::operator=(uint32_t input)
{
    value=input;
    if (this==&test_sd.ICR) test_sd.STA.value&=~input;
    else if (this==&test_sd.CMD) {
        command_write(input);
        value&=~SDMMC_CMD_CPSMEN;
    } else if (this==&test_sd.FIFO) {
        assert(operation==24 || operation==25);
        assert(words<expected_words);
        assert(words-tx_sent<256);
        output.push_back(input); ++words;
        if (words-tx_sent>tx_max_occupancy) tx_max_occupancy=words-tx_sent;
    } else if (this==&test_sd.DCTRL && (input&SDMMC_DCTRL_FIFORST)) {
        assert(uint32_t(test_sd.STA)&SDMMC_STA_DPSMACT);
        assert(!test_sd.IDMACTRL.value);
        ++fifo_resets; operation=0; abort_pending=false;
        test_sd.STA.value|=SDMMC_STA_DABORT;
        value&=~SDMMC_DCTRL_FIFORST;
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
    test_pwr={}; test_dwt={}; test_debug={};
    commands.clear(); arguments.clear(); output.clear();
    words=0; expected_words=0; current_lba=0; operation=0; stop_count=0; fifo_resets=0;
    data_error_at=0xFFFFFFFFU; busy_polls=0; command_error=0xFFFFFFFFU;
    late_card_error=0; waiting_for_stop=false; permanent_busy=false;
    abort_pending=false; abort_tail_end=0;
    tx_sent=0; tx_started=false; tx_start_words=0; tx_max_occupancy=0;
    test_gpio_c.IDR.value=1U<<4;
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

int main()
{
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
    std::puts("15 protocol cases passed");
}
