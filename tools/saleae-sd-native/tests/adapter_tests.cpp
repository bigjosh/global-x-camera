#include "SdNativeAnalyzer.h"
#include "sdk_shim.h"
#include <MockChannelData.h>
#include <MockResults.h>
#include <TestAnalyzerData.h>
#include <TestInstance.h>
#include <algorithm>
#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void check(bool pass,const std::string& reason){if(!pass)throw std::runtime_error(reason);}
struct Row {U64 sample;std::array<int,6> levels;};
std::vector<Row> load(const char*path){
    std::ifstream f(path);check(bool(f),"fixture open");std::string line;std::getline(f,line);std::vector<Row> rows;
    while(std::getline(f,line)){std::replace(line.begin(),line.end(),',',' ');std::istringstream s(line);Row r{};s>>r.sample;for(auto&v:r.levels)s>>v;check(bool(s),"fixture row");rows.push_back(r);}
    check(rows.size()>1,"fixture empty");return rows;
}
void run(const std::vector<Row>&rows,int track,unsigned offset,U64 busy_begin,U64 busy_end,unsigned expected_commands,unsigned expected_blocks){
    sdtest::reset();
    AnalyzerTest::Instance backend;
    SdNativeAnalyzer analyzer;
    auto*d=AnalyzerTest::GetDataFromAnalyzer(&analyzer);
    auto*settings=static_cast<SdNativeAnalyzerSettings*>(d->settings);
    d->sampleRateHz=250000000;settings->config.width=sd::Config::Four;settings->waveform_track=track;settings->sample_offset=offset;settings->complete_capture=true;
    std::array<std::unique_ptr<AnalyzerTest::MockChannelData>,6> input;
    for(unsigned lane=0;lane<6;++lane){
        settings->channels[lane]=Channel(1,lane,DIGITAL_CHANNEL);
        input[lane].reset(new AnalyzerTest::MockChannelData(&backend));
        input[lane]->TestSetInitialBitState(rows.front().levels[lane]?BIT_HIGH:BIT_LOW);
        int old=rows.front().levels[lane];
        for(size_t i=1;i<rows.size();++i)if(rows[i].levels[lane]!=old){input[lane]->TestAppendTransitionAtSamples(rows[i].sample);old=rows[i].levels[lane];}
        input[lane]->ResetCurrentSample();d->channelData[settings->channels[lane]]=input[lane].get();
    }
    analyzer.SetupResults();analyzer.WorkerThread(); // Must return normally in complete-capture mode.
    const auto&frames=sdtest::tables(d->results);unsigned commands=0,blocks=0,busy=0;U64 previous=0;bool first=true;
    for(const auto&f:frames){
        check(first||f.start>previous,"adapter produced overlapping table frames");first=false;previous=f.end;
        if(f.type=="command")++commands;
        if(f.type=="data_block"){++blocks;check(f.fields.at("error")=="false","recorded data CRC failed");}
        if(f.type=="busy"){++busy;check(f.start==busy_begin&&f.end==busy_end,"adapter changed exact busy edges");}
    }
    if(track==0)check(commands==expected_commands,"CMD count mismatch");
    else {check(blocks==expected_blocks,"data block count mismatch");check(busy==1,"missing/doubled busy interval");}
    auto*legacy=AnalyzerTest::MockResultData::MockFromResults(d->results);
    check(legacy->TotalFrameCount()==frames.size(),"V1/V2 selected tracks differ");
    // Caching should never ask for availability on every fixed CLK transition.
    check(sdtest::availability_calls()<rows.size()*2,"pathological availability polling");
    std::cout<<"adapter track="<<track<<" offset="<<offset<<" frames="<<frames.size()<<" availability="<<sdtest::availability_calls()<<'\n';
}
}
int main(int argc,char**argv){
    try{
        check(argc==3,"usage: adapter_tests first-write.csv final-stop.csv");
        const auto first=load(argv[1]),last=load(argv[2]);
        run(first,0,0,105704624,105765650,4,1);
        run(first,1,0,105704624,105765650,4,1);
        run(last,0,0,159918394,160132045,3,0);
        run(last,1,0,159918394,160132045,3,0);
        run(last,1,1,159918394,160132045,3,0); // Raw busy unchanged by sampled-bit offset.
        // Synthetic continuation of the recorded CMD12: stop CLK after its
        // response, then release DAT0 with no later clock transition. This
        // specifically exercises WorkerThread's independently merged cursors.
        std::vector<Row> stopped;
        for(const auto&r:last)if(r.sample<=159919000)stopped.push_back(r);
        Row release=stopped.back();release.sample=160132045;release.levels[2]=1;stopped.push_back(release);
        release.sample=160200000;stopped.push_back(release);
        run(stopped,1,0,159918394,160132045,1,0);
    }catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return EXIT_FAILURE;}
    std::cout<<"Actual Saleae adapter mock tests passed\n";return EXIT_SUCCESS;
}
