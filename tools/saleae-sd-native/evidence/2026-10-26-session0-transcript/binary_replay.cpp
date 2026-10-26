#include "SdNativeDecoder.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static constexpr uint64_t rate=500000000;
template<class T> T read(std::ifstream& in){T x{};in.read(reinterpret_cast<char*>(&x),sizeof(x));if(!in)throw std::runtime_error("short binary input");return x;}
struct Channel{bool initial;double begin,end;std::vector<uint64_t> edges;size_t index=0;bool level;};
static Channel load(const std::string& path){
 std::ifstream f(path,std::ios::binary);char magic[8];f.read(magic,8);if(std::string(magic,8)!="<SALEAE>")throw std::runtime_error("bad magic");
 if(read<int32_t>(f)!=0||read<int32_t>(f)!=0)throw std::runtime_error("unsupported export format");
 Channel c;c.initial=read<int32_t>(f)!=0;c.level=c.initial;c.begin=read<double>(f);c.end=read<double>(f);uint64_t n=read<uint64_t>(f);
 c.edges.reserve(n);for(uint64_t i=0;i<n;++i){double t=read<double>(f);c.edges.push_back(uint64_t(std::llround((t-c.begin)*rate)));}return c;
}
static std::string quote(const std::string& s){std::ostringstream o;o<<'"';for(unsigned char c:s){switch(c){case '"':o<<"\\\"";break;case '\\':o<<"\\\\";break;case '\n':o<<"\\n";break;case '\r':o<<"\\r";break;case '\t':o<<"\\t";break;default:if(c<32)o<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<unsigned(c)<<std::dec;else o<<c;}}return o.str()+'"';}
int main(int argc,char**argv){try{
 if(argc!=4)throw std::runtime_error("binary_replay binary-directory offset-acquisition-samples output.jsonl");
 uint64_t offset=std::stoull(argv[2]);std::array<Channel,6> channels;
 for(int i=0;i<6;++i)channels[i]=load(std::string(argv[1])+"/digital_"+std::to_string(i)+".bin");
 for(auto&c:channels)if(c.begin!=channels[0].begin||c.end!=channels[0].end)throw std::runtime_error("channel time bounds differ");
 std::ofstream out(argv[3]);if(!out)throw std::runtime_error("cannot open output");sd::Config config;uint64_t events=0,errors=0,clocks=0;
 sd::Decoder decoder(config,[&](const sd::Event&e){++events;if(e.error)++errors;
 out<<"{\"start\":"<<e.start<<",\"end\":"<<e.end<<",\"start_s\":"<<std::setprecision(17)<<double(e.start)/rate<<",\"end_s\":"<<double(e.end)/rate<<",\"display_start_s\":"<<double(e.start)/rate+channels[0].begin<<",\"display_end_s\":"<<double(e.end)/rate+channels[0].begin<<",\"duration_us\":"<<double(e.end-e.start)*1e6/rate<<",\"type\":"<<quote(e.type)<<",\"text\":"<<quote(e.text)<<",\"track\":"<<e.track<<",\"error\":"<<(e.error?"true":"false")<<",\"fields\":{";
 bool first=true;for(auto&kv:e.fields){if(!first)out<<',';first=false;out<<quote(kv.first)<<':'<<quote(kv.second);}out<<"}}\n";
 });
 auto& clk=channels[1];decoder.dat0_edge(0,channels[2].initial);
 uint64_t finish=uint64_t(std::llround((channels[0].end-channels[0].begin)*rate));
 for(uint64_t edge:clk.edges){clk.level=!clk.level;if(!clk.level)continue;uint64_t sample=edge+offset;if(sample>finish)break;
   for(int i=0;i<6;++i){if(i==1)continue;auto&c=channels[i];while(c.index<c.edges.size()&&c.edges[c.index]<=sample){uint64_t t=c.edges[c.index++];c.level=!c.level;if(i==2)decoder.dat0_edge(t,c.level);}}
   uint8_t dat=0;for(int i=2;i<6;++i)dat|=uint8_t(channels[i].level<<(i-2));decoder.clock(sample,channels[0].level,dat);++clocks;
 }
 auto&d0=channels[2];while(d0.index<d0.edges.size()){uint64_t t=d0.edges[d0.index++];d0.level=!d0.level;decoder.dat0_edge(t,d0.level);}decoder.finish(finish);
 std::cerr<<"{\"rate\":"<<rate<<",\"offset_samples\":"<<offset<<",\"display_origin_s\":"<<std::setprecision(17)<<channels[0].begin<<",\"duration_s\":"<<channels[0].end-channels[0].begin<<",\"clocks\":"<<clocks<<",\"events\":"<<events<<",\"errors\":"<<errors<<"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
