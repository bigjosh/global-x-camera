#include "SdNativeDecoder.h"
#include <array>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value,const std::string& text) { if (!value) throw std::runtime_error(text); }
uint8_t crc7(const std::vector<int>& bits,unsigned begin,unsigned size) {
    uint8_t crc=0; for(unsigned i=begin;i<begin+size;++i) {bool feedback=((crc>>6)^bits[i])&1;crc=uint8_t((crc<<1)&127);if(feedback)crc^=9;}return crc;
}
uint16_t crc16(uint16_t crc,int bit) {bool feedback=((crc>>15)^bit)&1;crc=uint16_t(crc<<1);if(feedback)crc^=0x1021;return crc;}
void append(std::vector<int>& b,uint64_t value,unsigned count) {while(count--)b.push_back(int((value>>count)&1));}
std::vector<int> frame(bool host,unsigned command,uint32_t arg,bool bad=false) {
    std::vector<int> b{0,host?1:0};append(b,command,6);append(b,arg,32);uint8_t crc=crc7(b,0,40);append(b,crc^(bad?1:0),7);b.push_back(1);return b;
}
struct Fixture {
    sd::Config config;
    std::vector<sd::Event> events;
    sd::Decoder decoder;
    uint64_t sample=100;
    bool dat0=true;
    explicit Fixture(sd::Config c={}):config(c),decoder(c,[this](const sd::Event& e){events.push_back(e);}){}
    void edge(uint64_t at,bool high) {decoder.dat0_edge(at,high);dat0=high;}
    void tick(bool cmd=true,uint8_t dat=15) {if(bool(dat&1)!=dat0)edge(sample-2,bool(dat&1));decoder.clock(sample,cmd,dat);sample+=10;}
    void idle(unsigned n=10,uint8_t dat=15) {while(n--)tick(true,dat);}
    void token(const std::vector<int>& b,uint8_t dat=15) {for(auto bit:b)tick(bit,dat);}
    void command(unsigned c,uint32_t a=0,bool bad=false) {token(frame(true,c,a,bad));}
    void response(unsigned c,uint32_t a=0x900,bool bad=false,uint8_t dat=15) {idle(2,dat);token(frame(false,c,a,bad),dat);}
    void write_command(bool multi=true) {command(multi?25:24);response(multi?25:24);}
    void data(unsigned width=4,unsigned bytes=512,int corrupt_lane=-1,bool bad_end=false) {
        std::array<uint16_t,4> crc{};
        tick(true,0);
        for(unsigned i=0;i<bytes*8/width;++i) {
            unsigned v=(i*7+3)&((1u<<width)-1); // deterministic varied bits on every lane
            for(unsigned lane=0;lane<width;++lane)crc[lane]=crc16(crc[lane],(v>>lane)&1);
            tick(true,uint8_t(v));
        }
        if(corrupt_lane>=0)crc[unsigned(corrupt_lane)]^=1;
        for(int bit=15;bit>=0;--bit) {unsigned v=0;for(unsigned lane=0;lane<width;++lane)v|=((crc[lane]>>bit)&1)<<lane;tick(true,uint8_t(v));}
        tick(true,bad_end?0:uint8_t((1u<<width)-1));
    }
    void status(unsigned value=2,uint8_t upper=14,bool bad_end=false) {
        idle(2); tick(true,upper); for(int bit=2;bit>=0;--bit)tick(true,uint8_t(upper|((value>>bit)&1)));tick(true,uint8_t(upper|(bad_end?0:1)));
    }
    void stop(bool busy=false) {
        command(12);
        if(busy) {edge(sample-1,false);response(12,0x900,false,14);sample+=123;edge(sample,true);sample+=10;}
        else {response(12);idle(10);}
    }
    std::vector<sd::Event> of(const std::string& type)const {std::vector<sd::Event> out;for(const auto&e:events)if(e.type==type)out.push_back(e);return out;}
    bool has_error(const std::string& needle) const {for(const auto&e:events)if(e.error&&e.text.find(needle)!=std::string::npos)return true;return false;}
};
sd::Config four() {sd::Config c;c.width=sd::Config::Four;return c;}
std::string field(const sd::Event& e,const std::string& name) {for(const auto&p:e.fields)if(p.first==name)return p.second;throw std::runtime_error("missing field "+name);}

void commands_and_responses() {
    Fixture f;
    f.command(0);f.idle();f.command(8,0x1aa);f.response(8,0x1aa);
    f.command(55);f.response(55,0x120);f.command(41,0x40ff8000);f.response(63,0xc0ff8000,true);
    auto response=f.of("response");require(response.size()==3,"boot response count");
    require(!response.back().error&&field(response.back(),"response_type")=="R3","R3 must not validate CRC");
    f.command(55);f.response(55,0x920);f.command(6,2);f.response(6);
    require(f.of("bus_width").size()==1,"ACMD6 width transition");
    f.write_command();f.data();f.status();f.idle();f.stop();
    require(f.of("data_block").size()==1&&!f.of("data_block")[0].error,"auto negotiated four-bit block");
    f.command(13,0,true);require(f.of("command").back().error,"bad host CRC exposed");
    f.command(13);f.response(13,0x900,true);require(f.of("response").back().error,"bad response CRC exposed");
    f.command(13);f.response(12);require(f.of("response").back().error,"wrong response index rejected");
}
void r2_crc() {
    Fixture f;
    for(bool corrupt:{false,true}) {
        f.command(2);std::vector<int>b{0,0};append(b,63,6);for(unsigned i=0;i<15;++i)append(b,i*13+7,8);append(b,crc7(b,8,120)^(corrupt?1:0),7);b.push_back(1);f.token(b);
    }
    auto r=f.of("response");require(r.size()==2&&!r[0].error&&r[1].error,"R2 CRC only CID/CSD120 bits");
}
void rejected_commands_do_not_change_data_state() {
    Fixture f;
    f.command(55);f.response(55,0x920);f.command(6,2);f.response(6,0x00400900);
    require(f.of("bus_width").empty(),"rejected ACMD6 must not change width");
    f.command(17);f.response(17);f.data(1,512);
    require(!f.of("data_block")[0].error&&field(f.of("data_block")[0],"width")=="1","failed width retains one-bit");
    Fixture bad(four());bad.command(25,0,true);bad.response(25);bad.data();bad.status();
    require(bad.of("data_block").empty(),"bad command CRC cannot arm data");
    Fixture denied(four());denied.command(25);denied.response(25,0x00400900);denied.data();denied.status();
    require(denied.of("data_block").empty(),"card command error cannot arm data");
}
void busy_and_no_busy() {
    Fixture f(four());f.write_command();f.data();f.status(2,0); // upper lanes LOW are legal don't-care
    uint64_t start=f.sample-1;f.edge(start,false);f.idle(2,0);f.sample+=12345;
    uint64_t end=f.sample;f.edge(end,true);f.sample+=10;f.idle(2);f.data();f.status();f.idle();f.stop();
    auto busy=f.of("busy");require(busy.size()==1,"one busy despite arbitrary upper lanes");
    require(busy[0].start==start&&busy[0].end==end,"busy exact DAT0 edges with stopped clock");
    require(f.of("data_block").size()==2,"busy/status not misparsed as data start");
    require(!f.of("transfer").back().error,"clean transfer summary");
}
void errors() {
    for(int lane=0;lane<4;++lane) {
        Fixture f(four());f.write_command();f.data(4,512,lane);f.status(5);f.idle();f.stop();
        require(f.of("data_block")[0].error,"detect each lane CRC failure");
        require(f.of("write_status")[0].error&&f.of("transfer").back().error,"rejection propagated");
    }
    for(unsigned reserved:{0u,1u,3u,4u,6u,7u}) {
        Fixture f(four());f.write_command();f.data();f.status(reserved);f.idle();f.stop();
        require(f.of("write_status")[0].error,"native reserved status never accepted");
    }
    Fixture missing(four());missing.write_command();missing.data();missing.idle(20);missing.stop();
    require(missing.has_error("Missing write CRC status"),"missing status exposed");
    Fixture badend(four());badend.write_command();badend.data(4,512,-1,true);badend.status();badend.idle();badend.stop();
    require(badend.of("data_block")[0].error,"bad packet end exposed");
}
void stop_busy_before_response() {
    Fixture f(four());f.write_command();f.data();f.status();f.idle();f.command(12);
    const auto begin=f.sample-1;f.edge(begin,false);f.response(12,0x900,false,0);f.sample+=111;
    const auto end=f.sample;f.edge(end,true);f.sample+=10;
    auto busy=f.of("busy");require(busy.size()==1&&busy[0].start==begin&&busy[0].end==end,"CMD12 busy begins before response end");
    require(busy[0].text.find("CMD12")!=std::string::npos,"CMD12 busy association");
    require(f.of("data_block").size()==1,"R1b upper lanes don't-care cannot create false block");
}
void truncated() {
    Fixture f(four());f.write_command();f.tick(true,0);f.idle(100,0);f.decoder.finish(f.sample);
    require(f.has_error("Truncated data block")&&f.of("transfer").back().error,"truncated block fail closed");
    Fixture b(four());b.write_command();b.data();b.status();b.edge(b.sample,false);b.decoder.finish(b.sample+999);
    require(b.of("busy").size()==1&&b.of("busy")[0].error,"unterminated BUSY truncated");
    Fixture c;c.tick(false);c.decoder.finish(c.sample);require(c.has_error("Truncated CMD"),"truncated command");
}
void read_and_small_register() {
    Fixture f;f.command(55);f.response(55,0x920);f.command(51);f.response(51);f.data(1,8);
    require(f.of("data_block").size()==1&&field(f.of("data_block")[0],"bytes")=="8","SCR size not512");
    require(f.of("write_status").empty(),"read has no write status");
    f.command(17);f.response(17);f.data(1,512);require(f.of("transfer").size()==2,"single read completion");
}
void count_and_hint() {
    Fixture f(four());f.command(55);f.response(55,0x920);f.command(23,1);f.response(23);
    f.write_command();f.data();f.status();f.idle();f.data();f.status();f.idle();f.stop();
    require(f.of("data_block").size()==2,"ACMD23 hint must not truncate multiblock");
    require(field(f.of("transfer").back(),"preerase_hint")=="1","preerase hint retained");
    Fixture g(four());g.command(23,1);g.response(23);g.write_command();g.data();g.status();g.idle();
    require(g.of("transfer").size()==1&&!g.of("transfer")[0].error,"CMD23 actual count ends transfer");
}
void data_only() {
    auto c=four();c.data_only=sd::Config::Write;Fixture f(c);f.data();f.status();f.idle();f.decoder.finish(f.sample);
    require(f.of("command").empty()&&f.of("data_block").size()==1,"data-only parsing");
    require(field(f.of("data_block")[0],"mode").find("INFERRED")!=std::string::npos,"inference explicit");
    require(f.of("transfer").back().error,"data-only cannot claim CMD12 completion");
}
} // namespace

int main() {
    try {commands_and_responses();r2_crc();rejected_commands_do_not_change_data_state();busy_and_no_busy();errors();stop_busy_before_response();truncated();read_and_small_register();count_and_hint();data_only();}
    catch(const std::exception&e) {std::cerr<<"FAIL: "<<e.what()<<'\n';return EXIT_FAILURE;}
    std::cout<<"SD native decoder tests passed\n";return EXIT_SUCCESS;
}
