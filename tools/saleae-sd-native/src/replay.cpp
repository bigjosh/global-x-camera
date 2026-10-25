// Offline CSV replay of the exact core used by the Logic 2 plugin.
#include "SdNativeDecoder.h"
#include <array>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>

static std::string quote(const std::string& s) {
    std::ostringstream o; o << '"';
    for (unsigned char c : s) {
        switch (c) {
        case '"': o << "\\\""; break;
        case '\\': o << "\\\\"; break;
        case '\n': o << "\\n"; break;
        case '\r': o << "\\r"; break;
        case '\t': o << "\\t"; break;
        default:
            if (c < 32) o << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c) << std::dec;
            else o << c;
        }
    }
    return o.str() + '"';
}

int main(int argc, char** argv) {
    try {
        sd::Config config;
        uint64_t rate = 250000000;
        std::string input, output;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            auto value = [&]() -> std::string {
                if (++i >= argc) throw std::runtime_error("Missing value for " + arg);
                return argv[i];
            };
            if (arg == "--width") {
                auto v = value();
                if (v == "auto") config.width = sd::Config::Auto;
                else if (v == "1") config.width = sd::Config::One;
                else if (v == "4") config.width = sd::Config::Four;
                else throw std::runtime_error("Width must be auto, 1 or 4");
            } else if (arg == "--data-only") {
                auto v = value();
                if (v == "read") config.data_only = sd::Config::Read;
                else if (v == "write") config.data_only = sd::Config::Write;
                else throw std::runtime_error("Data-only must be read or write");
            } else if (arg == "--rate") rate = std::stoull(value());
            else if (arg == "--output") output = value();
            else if (arg == "--help") {
                std::cout << "sd_native_replay [--width auto|1|4] [--rate Hz] [--data-only read|write] [--output events.jsonl] edges.csv\n"
                             "CSV header: sample,clk,cmd,d0,d1,d2,d3. Rows give levels AFTER simultaneous edges.\n";
                return 0;
            } else if (!arg.empty() && arg[0] == '-') throw std::runtime_error("Unknown option " + arg);
            else if (!input.empty()) throw std::runtime_error("Only one input CSV is accepted");
            else input = arg;
        }
        if (input.empty() || !rate) throw std::runtime_error("A CSV input and nonzero sample rate are required");
        std::ifstream in(input);
        if (!in) throw std::runtime_error("Cannot open " + input);
        std::ofstream file;
        if (!output.empty()) { file.open(output); if (!file) throw std::runtime_error("Cannot open output"); }
        std::ostream& out = output.empty() ? std::cout : file;
        sd::Decoder decoder(config, [&](const sd::Event& e) {
            out << "{\"start\":" << e.start << ",\"end\":" << e.end
                << ",\"duration_us\":" << std::setprecision(15) << (double(e.end-e.start)*1000000.0/double(rate))
                << ",\"type\":" << quote(e.type) << ",\"text\":" << quote(e.text)
                << ",\"track\":" << e.track << ",\"error\":" << (e.error ? "true" : "false")
                << ",\"fields\":{";
            bool first = true;
            for (const auto& kv : e.fields) { if (!first) out << ','; first = false; out << quote(kv.first) << ':' << quote(kv.second); }
            out << "}}\n";
        });
        std::string line;
        if (!std::getline(in,line)) throw std::runtime_error("Empty CSV");
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line != "sample,clk,cmd,d0,d1,d2,d3") throw std::runtime_error("Unexpected CSV header");
        std::array<int,6> previous{};
        uint64_t last = 0, rows = 0;
        while (std::getline(in,line)) {
            if (line.empty()) continue;
            std::istringstream row(line);
            uint64_t sample; char comma;
            std::array<int,6> level{};
            if (!(row >> sample)) throw std::runtime_error("Invalid sample index");
            for (auto& b : level) {
                if (!(row >> comma >> b) || comma != ',' || (b != 0 && b != 1)) throw std::runtime_error("Invalid CSV levels");
            }
            row >> std::ws;
            if (!row.eof()) throw std::runtime_error("Extra CSV columns");
            if (rows && sample <= last) throw std::runtime_error("CSV samples must increase strictly");
            if (!rows || level[2] != previous[2]) decoder.dat0_edge(sample,level[2] != 0);
            if (rows && !previous[0] && level[0]) {
                const uint8_t dat = uint8_t(level[2] | (level[3]<<1) | (level[4]<<2) | (level[5]<<3));
                decoder.clock(sample, level[1] != 0, dat);
            }
            previous = level; last = sample; ++rows;
        }
        if (!rows) throw std::runtime_error("No CSV samples");
        decoder.finish(last);
        if (!out) throw std::runtime_error("Output write failed");
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "sd_native_replay: " << e.what() << '\n';
        return 1;
    }
}
