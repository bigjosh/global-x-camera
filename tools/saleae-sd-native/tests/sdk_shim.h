#pragma once
#include <AnalyzerResults.h>
#include <map>
#include <string>
#include <vector>
namespace sdtest {
struct TableFrame { U64 start, end; std::string type; std::map<std::string,std::string> fields; };
const std::vector<TableFrame>& tables(AnalyzerResults* results);
void reset();
U64 availability_calls();
}
