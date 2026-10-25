// Test-only compatibility additions to the pinned upstream AnalyzerSDK testlib.
// These shims do not implement a live Logic backend and are never in the DLL.
#include "sdk_shim.h"
#include <Analyzer.h>
#include <AnalyzerChannelData.h>
#include <MockChannelData.h>
#include <algorithm>
#include <sstream>

class FrameV2Data { public: std::map<std::string,std::string> values; };
namespace {
std::map<AnalyzerResults*,std::vector<sdtest::TableFrame>> table_results;
U64 probes=0;
}
namespace sdtest {
const std::vector<TableFrame>& tables(AnalyzerResults* r) { return table_results[r]; }
void reset() {table_results.clear();probes=0;}
U64 availability_calls() {return probes;}
}
void Analyzer::UseFrameV2() {}
bool AnalyzerChannelData::DoMoreTransitionsExistInCurrentData() {
    ++probes;
    const auto* d=reinterpret_cast<const AnalyzerTest::MockChannelData*>(this);
    return std::upper_bound(d->mTransitions.begin(),d->mTransitions.end(),d->mCurrentSample)!=d->mTransitions.end();
}
FrameV2::FrameV2():mInternals(new FrameV2Data){}
FrameV2::~FrameV2(){delete mInternals;}
void FrameV2::AddString(const char*k,const char*v){mInternals->values[k]=v;}
void FrameV2::AddDouble(const char*k,double v){std::ostringstream s;s.precision(17);s<<v;mInternals->values[k]=s.str();}
void FrameV2::AddInteger(const char*k,S64 v){mInternals->values[k]=std::to_string(v);}
void FrameV2::AddBoolean(const char*k,bool v){mInternals->values[k]=v?"true":"false";}
void FrameV2::AddByte(const char*k,U8 v){mInternals->values[k]=std::to_string(v);}
void FrameV2::AddByteArray(const char*k,const U8*,U64 n){mInternals->values[k]="bytes="+std::to_string(n);}
void AnalyzerResults::AddFrameV2(const FrameV2& f,const char*t,U64 start,U64 end){table_results[this].push_back({start,end,t,f.mInternals->values});}
