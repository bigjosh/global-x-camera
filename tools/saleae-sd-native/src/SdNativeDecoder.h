#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace sd {

struct Event {
    uint64_t start = 0, end = 0;
    std::string type, text;
    int track = 0; // 0: CMD, 1: DAT
    bool error = false;
    std::vector<std::pair<std::string, std::string>> fields;
};

struct Config {
    enum Width { Auto = 0, One = 1, Four = 4 };
    Width width = Auto;
    uint32_t initial_block_bytes = 512;
    enum DataOnly { None, Read, Write };
    DataOnly data_only = None;
    bool require_cmd_crc = true;
};

// Passive native SD SDR decoder. No instrument, target, or filesystem access.
// Feed every raw DAT0 transition <= a clock sample before calling clock().
// Events complete in observation order; intervals on CMD and DAT can overlap.
class Decoder {
public:
    using Callback = std::function<void(const Event&)>;
    Decoder(Config config, Callback callback);
    void clock(uint64_t sample, bool cmd, uint8_t dat);
    void dat0_edge(uint64_t sample, bool high);
    void finish(uint64_t sample);

private:
    enum class DataState { Idle, Start, Payload, Crc, End, StatusWait, StatusBits, AfterStatus, Busy };
    struct Pending {
        int cmd = -1;
        bool app = false, valid = false;
        uint32_t arg = 0;
        uint64_t start = 0, end = 0;
    } pending_;
    Config config_;
    Callback callback_;
    unsigned width_ = 1, block_bytes_ = 512;
    bool app_next_ = false, block_addressed_ = false, address_known_ = false;
    std::vector<uint8_t> cmd_bits_;
    uint64_t cmd_start_ = 0;
    unsigned cmd_length_ = 48;
    DataState state_ = DataState::Idle;
    bool data_write_ = false, data_multi_ = false, inferred_ = false;
    int data_command_ = -1;
    uint64_t transfer_start_ = 0, block_start_ = 0, status_start_ = 0;
    uint32_t data_arg_ = 0, payload_clocks_ = 0, payload_seen_ = 0;
    uint32_t blocks_ = 0, bad_blocks_ = 0, rejected_blocks_ = 0;
    uint32_t preerase_ = 0, transfer_preerase_ = 0, explicit_count_ = 0, transfer_count_ = 0;
    uint64_t transfer_busy_samples_ = 0;
    bool transfer_active_ = false, stop_requested_ = false;
    unsigned crc_seen_ = 0, status_seen_ = 0, status_wait_ = 0, status_value_ = 0;
    std::array<uint16_t, 4> crc_calc_{}, crc_rx_{};
    std::vector<uint8_t> preview_;
    uint8_t byte_ = 0;
    unsigned byte_bits_ = 0;
    bool block_bad_ = false;
    bool dat0_high_ = true, raw_seen_ = false;
    uint64_t last_low_ = 0, last_sample_ = 0;
    bool busy_active_ = false, busy_r1b_ = false;
    uint64_t busy_start_ = 0;
    bool r1b_armed_ = false, r1b_responded_ = false;
    int r1b_command_ = -1;
    unsigned r1b_grace_ = 0;
    uint64_t r1b_start_ = 0;

    void emit(Event event);
    void command_clock(uint64_t sample, bool bit);
    void command_complete(uint64_t sample);
    void data_clock(uint64_t sample, uint8_t dat);
    void begin_transfer(uint64_t sample, int cmd, uint32_t arg, unsigned bytes, bool write, bool multi, bool inferred);
    void begin_busy(uint64_t sample, bool r1b);
    void end_busy(uint64_t sample, bool truncated);
    void finish_transfer(uint64_t sample, bool truncated);
    void arm_r1b(uint64_t sample, int cmd);
    void diagnostic(uint64_t start, uint64_t end, int track, const std::string& text);
};

} // namespace sd
