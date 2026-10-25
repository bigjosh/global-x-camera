#include "SdNativeDecoder.h"

#include <algorithm>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace sd {
namespace {
std::string hex(uint64_t value, unsigned digits = 0) {
    std::ostringstream out; out << "0x" << std::hex << std::uppercase << std::setw(digits) << std::setfill('0') << value; return out.str();
}
std::string number(uint64_t value) { return std::to_string(value); }
uint32_t bits(const std::vector<uint8_t>& b, unsigned at, unsigned n) {
    uint32_t v = 0; while (n--) v = (v << 1) | b.at(at++); return v;
}
uint8_t crc7(const std::vector<uint8_t>& b, unsigned at, unsigned n) {
    uint8_t c = 0;
    while (n--) { const bool x = ((c >> 6) ^ b.at(at++)) & 1; c = uint8_t((c << 1) & 0x7f); if (x) c ^= 0x09; }
    return c;
}
uint16_t crc16(uint16_t c, bool bit) {
    const bool x = ((c >> 15) ^ unsigned(bit)) & 1; c = uint16_t(c << 1); if (x) c ^= 0x1021; return c;
}
std::string command_name(int c, bool app) {
    if (app) { switch(c) { case 6:return "SET_BUS_WIDTH"; case 13:return "SD_STATUS"; case 22:return "SEND_NUM_WR_BLOCKS"; case 23:return "SET_WR_BLK_ERASE_COUNT"; case 41:return "SD_SEND_OP_COND"; case 42:return "SET_CLR_CARD_DETECT"; case 51:return "SEND_SCR"; default:return "application command"; } }
    switch(c) { case 0:return "GO_IDLE_STATE"; case 2:return "ALL_SEND_CID"; case 3:return "SEND_RELATIVE_ADDR"; case 6:return "SWITCH_FUNC"; case 7:return "SELECT_DESELECT_CARD"; case 8:return "SEND_IF_COND"; case 9:return "SEND_CSD"; case 10:return "SEND_CID"; case 12:return "STOP_TRANSMISSION"; case 13:return "SEND_STATUS"; case 16:return "SET_BLOCKLEN"; case 17:return "READ_SINGLE_BLOCK"; case 18:return "READ_MULTIPLE_BLOCK"; case 23:return "SET_BLOCK_COUNT"; case 24:return "WRITE_BLOCK"; case 25:return "WRITE_MULTIPLE_BLOCK"; case 32:return "ERASE_WR_BLK_START"; case 33:return "ERASE_WR_BLK_END"; case 38:return "ERASE"; case 55:return "APP_CMD"; default:return "command"; }
}
std::string response_name(int c, bool app) {
    if (app && c == 41) return "R3";
    if (!app && (c == 2 || c == 9 || c == 10)) return "R2";
    if (!app && c == 3) return "R6";
    if (!app && c == 8) return "R7";
    if (!app && (c == 7 || c == 12 || c == 28 || c == 29 || c == 38)) return "R1b";
    return "R1";
}
std::string state_name(unsigned n) {
    static const char* names[] = {"idle","ready","ident","standby","transfer","sending-data","receive-data","programming","disconnect"};
    return n < 9 ? names[n] : "reserved";
}
} // namespace

Decoder::Decoder(Config config, Callback callback):config_(config),callback_(std::move(callback)) {
    if (!callback_ || !config.initial_block_bytes || config.initial_block_bytes > 65536 ||
        (config.width != Config::Auto && config.width != Config::One && config.width != Config::Four))
        throw std::invalid_argument("invalid SD decoder configuration");
    if (config.data_only != Config::None && config.width == Config::Auto)
        throw std::invalid_argument("data-only mode requires explicit bus width");
    width_ = config.width == Config::Four ? 4 : 1; block_bytes_ = config.initial_block_bytes;
    if (config.data_only != Config::None)
        begin_transfer(0, config.data_only == Config::Write ? 25 : 18, 0, block_bytes_, config.data_only == Config::Write, true, true);
}
void Decoder::emit(Event e) { if (e.end < e.start) e.end = e.start; callback_(e); }
void Decoder::diagnostic(uint64_t start, uint64_t end, int track, const std::string& text) {
    emit({start,end,"error",text,track,true,{}});
}

void Decoder::clock(uint64_t sample, bool cmd, uint8_t dat) {
    last_sample_ = sample;
    // Fallback when a caller supplies clock samples without raw DAT0 edges.
    if (bool(dat & 1) != dat0_high_) dat0_edge(sample, bool(dat & 1));
    if (config_.data_only == Config::None) command_clock(sample, cmd);
    data_clock(sample, dat);
    if (r1b_armed_ && r1b_responded_ && !busy_active_ && ++r1b_grace_ > 8) {
        r1b_armed_ = false;
        if (stop_requested_) finish_transfer(sample, false);
    }
}

void Decoder::command_clock(uint64_t sample, bool bit) {
    if (cmd_bits_.empty()) { if (bit) return; cmd_start_ = sample; cmd_length_ = 48; }
    cmd_bits_.push_back(bit);
    if (cmd_bits_.size() == 2 && !cmd_bits_[1] && pending_.valid && response_name(pending_.cmd,pending_.app) == "R2") cmd_length_ = 136;
    if (cmd_bits_.size() == cmd_length_) { command_complete(sample); cmd_bits_.clear(); }
}

void Decoder::command_complete(uint64_t sample) {
    const bool host = cmd_bits_[1] != 0;
    const unsigned index = bits(cmd_bits_,2,6);
    const bool end_ok = cmd_bits_.back() == 1;
    const bool is_r2 = cmd_bits_.size() == 136;
    const std::string response = !host && pending_.valid ? response_name(pending_.cmd,pending_.app) : "unknown";
    const bool crc_present = host || (response != "R3" && response != "unknown");
    const uint8_t received = uint8_t(bits(cmd_bits_, unsigned(cmd_bits_.size()-8),7));
    const uint8_t calculated = crc7(cmd_bits_,is_r2 ? 8 : 0,is_r2 ? 120 : 40);
    const bool crc_ok = !crc_present || calculated == received;
    const bool echo_ok = host || response == "unknown" || response == "R2" || response == "R3" || index == unsigned(pending_.cmd);
    const bool framing_ok = end_ok && echo_ok && (!is_r2 || index == 63) && (response != "R3" || index == 63);
    const uint32_t arg = is_r2 ? 0 : bits(cmd_bits_,8,32);
    const bool accepted_frame = framing_ok && (crc_ok || !config_.require_cmd_crc);
    const bool app = host ? app_next_ : pending_.app;
    std::string name = (app ? "ACMD" : "CMD") + number(host ? index : unsigned(std::max(0,pending_.cmd)));
    Event e{cmd_start_,sample,host ? "command" : "response","",0,!framing_ok || !crc_ok,{}};
    e.text = host ? name + " " + command_name(index,app) + " " + hex(arg,8) : response + " to " + (pending_.valid ? name : "unassociated command");
    e.fields = {{"command",host ? number(index) : number(unsigned(std::max(0,pending_.cmd)))},{"application",app ? "yes" : "no"},{"response_type",host ? "" : response},{"crc",crc_present ? (crc_ok ? "OK" : "BAD") : "not present / unknown"},{"end_bit",end_ok ? "1" : "BAD"}};
    if (!is_r2) e.fields.emplace_back(host ? "argument" : "value",hex(arg,8));
    if (crc_present) { e.fields.emplace_back("crc_received",hex(received,2)); e.fields.emplace_back("crc_calculated",hex(calculated,2)); }
    if (!host && (response == "R1" || response == "R1b")) {
        e.fields.emplace_back("card_state",state_name((arg >> 9) & 15));
        e.fields.emplace_back("ready_for_data",arg & 0x100 ? "yes" : "no");
        e.fields.emplace_back("status_errors",hex(arg & 0xFDFFE008u,8));
        if (arg & 0xFDFFE008u) { e.error = true; e.text += " ERROR"; }
    }
    if (!host && response == "R3") { e.fields.emplace_back("power_up_complete",arg & 0x80000000u ? "yes" : "no"); e.fields.emplace_back("CCS",arg & 0x40000000u ? "1 (block addressing)" : "0 (byte addressing)"); }
    if (!host && response == "R6") e.fields.emplace_back("RCA",hex(arg >> 16,4));
    if (!host && response == "R7") e.fields.emplace_back("echo_pattern",hex(arg & 255,2));
    if (is_r2) { std::string s; for (unsigned i=8;i<128;i+=8) { auto h=hex(bits(cmd_bits_,i,8),2); s+=h.substr(2); } e.fields.emplace_back("CID_CSD_120_bits",s); }
    if (!crc_ok) e.text += " CRC BAD";
    if (!framing_ok) e.text += " FRAMING BAD";
    emit(std::move(e));

    if (host) {
        app_next_ = false;
        pending_ = {int(index),app,accepted_frame,arg,cmd_start_,sample};
        if (!accepted_frame) return;
        if (!app && index == 0) {
            if (busy_active_) end_busy(sample,true);
            if (transfer_active_) finish_transfer(sample,true);
            width_ = config_.width == Config::Four ? 4 : 1; block_bytes_ = config_.initial_block_bytes;
            preerase_ = explicit_count_ = 0; address_known_ = false; r1b_armed_ = false; pending_.valid = false;
        }
        if (!app && index == 12) {
            stop_requested_ = true;
            if (state_ == DataState::Start) state_ = DataState::Idle;
            // A stop arriving during payload is observable truncation, never a CRC-valid full block.
            if (state_ == DataState::Payload || state_ == DataState::Crc || state_ == DataState::End) {
                diagnostic(block_start_,sample,1,"Data block interrupted by CMD12; incomplete block");
                ++bad_blocks_; state_ = DataState::Idle;
            }
        }
        if (!app && (index == 12 || index == 28 || index == 29 || index == 38 || (index == 7 && arg))) arm_r1b(sample,index);
        return;
    }
    const Pending p = pending_; pending_.valid = false;
    if (!p.valid || !accepted_frame) return;
    const bool r1_good = (response != "R1" && response != "R1b") || !(arg & 0xFDFFE008u);
    if (!r1_good) return;
    if (!p.app && p.cmd == 55) { app_next_ = (arg & 0x20u) != 0; }
    if (p.app && p.cmd == 6 && config_.width == Config::Auto) {
        if ((p.arg & 3) == 0 || (p.arg & 3) == 2) {
            width_ = (p.arg & 3) == 2 ? 4 : 1;
            emit({sample,sample,"bus_width","Bus width = " + number(width_),0,false,{{"width",number(width_)}}});
        } else diagnostic(sample,sample,0,"Reserved ACMD6 bus width; decoder width unchanged");
    }
    if (p.app && p.cmd == 23) preerase_ = p.arg & 0x7fffffu;
    if (!p.app && p.cmd == 23) explicit_count_ = p.arg;
    if (!p.app && p.cmd == 16) { if (p.arg && p.arg <= 65536) block_bytes_ = p.arg; else diagnostic(sample,sample,0,"Unsupported block length"); }
    if (response == "R3" && (arg & 0x80000000u)) { address_known_=true; block_addressed_=(arg & 0x40000000u)!=0; if (block_addressed_) block_bytes_=512; }
    if (response == "R1b") {
        r1b_responded_ = true; r1b_grace_ = 0;
        if (r1b_armed_ && !dat0_high_ && !busy_active_ && state_ != DataState::Payload && state_ != DataState::Crc)
            begin_busy(last_low_,true);
    }
    if (!p.app && (p.cmd == 17 || p.cmd == 18 || p.cmd == 24 || p.cmd == 25))
        begin_transfer(sample,p.cmd,p.arg,block_bytes_,p.cmd>=24,p.cmd==18 || p.cmd==25,false);
    if (p.app && p.cmd == 51) begin_transfer(sample,51,0,8,false,false,false);
    if (p.app && p.cmd == 13) begin_transfer(sample,13,0,64,false,false,false);
    if (p.app && p.cmd == 22) begin_transfer(sample,22,0,4,false,false,false);
    if (!p.app && p.cmd == 6) begin_transfer(sample,6,0,64,false,false,false);
}

void Decoder::begin_transfer(uint64_t sample, int cmd, uint32_t arg, unsigned bytes, bool write, bool multi, bool inferred) {
    if (transfer_active_) finish_transfer(sample,true);
    transfer_active_=true; transfer_start_=sample; data_command_=cmd; data_arg_=arg;
    data_write_=write; data_multi_=multi; inferred_=inferred; payload_clocks_=bytes*8/width_;
    blocks_=bad_blocks_=rejected_blocks_=0; transfer_busy_samples_=0;
    transfer_preerase_=write ? preerase_ : 0; preerase_=write ? 0 : preerase_;
    transfer_count_=multi ? explicit_count_ : 1; explicit_count_=0;
    stop_requested_=false; state_=DataState::Start;
}

void Decoder::data_clock(uint64_t sample, uint8_t dat) {
    const uint8_t mask = width_ == 4 ? 15 : 1;
    switch (state_) {
    case DataState::Idle: break;
    case DataState::Start:
        if ((dat & mask) != 0 || stop_requested_) break;
        if (inferred_ && !blocks_) transfer_start_=sample;
        block_start_=sample; payload_seen_=crc_seen_=0; crc_calc_.fill(0); crc_rx_.fill(0);
        preview_.clear(); byte_=0; byte_bits_=0; block_bad_=false; state_=DataState::Payload;
        break;
    case DataState::Payload:
        for (unsigned lane=0;lane<width_;++lane) crc_calc_[lane]=crc16(crc_calc_[lane],(dat>>lane)&1);
        byte_=uint8_t((byte_<<width_)|(dat&mask)); byte_bits_+=width_;
        if (byte_bits_==8) { if (preview_.size()<16) preview_.push_back(byte_); byte_=0; byte_bits_=0; }
        if (++payload_seen_==payload_clocks_) state_=DataState::Crc;
        break;
    case DataState::Crc:
        for (unsigned lane=0;lane<width_;++lane) crc_rx_[lane]=uint16_t((crc_rx_[lane]<<1)|((dat>>lane)&1));
        if (++crc_seen_==16) state_=DataState::End;
        break;
    case DataState::End: {
        ++blocks_; bool framing=(dat&mask)==mask;
        std::string crc,preview;
        for (unsigned lane=0;lane<width_;++lane) { if (lane) crc+="; "; const bool ok=crc_rx_[lane]==crc_calc_[lane]; block_bad_|=!ok; crc+="D"+number(lane)+":"+(ok ? "OK" : "BAD")+" "+hex(crc_rx_[lane],4)+"/"+hex(crc_calc_[lane],4); }
        block_bad_|=!framing; if (block_bad_) ++bad_blocks_;
        for (auto b:preview_) { if (!preview.empty()) preview+=' '; preview+=hex(b,2).substr(2); }
        Event e{block_start_,sample,"data_block",(data_write_ ? "Write" : "Read")+std::string(" block ")+number(blocks_)+(block_bad_ ? " CRC/framing BAD" : " CRC OK"),1,block_bad_,
            {{"block",number(blocks_)},{"bytes",number(payload_clocks_*width_/8)},{"width",number(width_)},{"payload_clocks",number(payload_clocks_)},{"packet_clocks",number(payload_clocks_+18)},{"CRC16 received/calculated",crc},{"end_bits",framing ? "OK" : "BAD"},{"preview",preview},{"mode",inferred_ ? "INFERRED data-only; command unobserved" : "command-associated"}}};
        if (!inferred_ && address_known_ && (data_command_==17 || data_command_==18 || data_command_==24 || data_command_==25)) e.fields.emplace_back("address",number(uint64_t(data_arg_)+(blocks_-1)*(block_addressed_ ? 1 : payload_clocks_*width_/8))+(block_addressed_ ? " LBA" : " bytes"));
        emit(std::move(e));
        if (data_write_) { state_=DataState::StatusWait; status_wait_=0; status_start_=sample; }
        else if (!data_multi_ || (transfer_count_ && blocks_>=transfer_count_)) { state_=DataState::Idle; finish_transfer(sample,false); }
        else state_=DataState::Start;
        break;
    }
    case DataState::StatusWait:
        // Native status lives on DAT0 only; DAT1..3 are explicitly don't-care.
        if (!(dat&1)) { status_start_=sample; status_seen_=0; status_value_=0; state_=DataState::StatusBits; }
        else if (++status_wait_>16) { diagnostic(sample,sample,1,"Missing write CRC status; data framing suspended"); ++rejected_blocks_; state_=DataState::Idle; }
        break;
    case DataState::StatusBits:
        if (status_seen_<3) { status_value_=(status_value_<<1)|(dat&1); ++status_seen_; }
        else {
            const bool ok=(dat&1) && status_value_==2;
            std::string result=status_value_==2 ? "accepted" : status_value_==5 ? "rejected: CRC error" : "reserved/unrecognized native status";
            if (!(dat&1)) result+="; bad end bit";
            emit({status_start_,sample,"write_status","Block "+number(blocks_)+" "+result,1,!ok,{{"block",number(blocks_)},{"status",number(status_value_)},{"token_end",dat&1 ? "1" : "BAD"}}});
            if (!ok) ++rejected_blocks_;
            if (!(dat&1)) { state_=DataState::Idle; } else state_=DataState::AfterStatus;
        }
        break;
    case DataState::AfterStatus:
        if (!(dat&1)) begin_busy(last_low_,false);
        else if (stop_requested_) state_=DataState::Idle;
        else if (!data_multi_ || (transfer_count_ && blocks_>=transfer_count_)) { state_=DataState::Idle; finish_transfer(sample,false); }
        else state_=DataState::Start;
        break;
    case DataState::Busy: break;
    }
}

void Decoder::arm_r1b(uint64_t sample, int cmd) {
    r1b_armed_=true; r1b_responded_=false; r1b_command_=cmd; r1b_start_=sample; r1b_grace_=0;
    if (busy_active_) { busy_r1b_=true; return; }
    if (!dat0_high_ && state_!=DataState::Payload && state_!=DataState::Crc && state_!=DataState::End && state_!=DataState::StatusBits)
        begin_busy(last_low_,true);
}
void Decoder::dat0_edge(uint64_t sample, bool high) {
    if (raw_seen_ && high==dat0_high_) return;
    raw_seen_=true; dat0_high_=high;
    if (!high) {
        last_low_=sample;
        if (state_==DataState::AfterStatus) begin_busy(sample,false);
        else if (r1b_armed_ && state_!=DataState::Payload && state_!=DataState::Crc && state_!=DataState::End && state_!=DataState::StatusBits && state_!=DataState::StatusWait) begin_busy(sample,true);
    } else if (busy_active_) end_busy(sample,false);
}
void Decoder::begin_busy(uint64_t sample, bool r1b) {
    if (busy_active_) { busy_r1b_|=r1b; return; }
    busy_active_=true; busy_start_=sample; busy_r1b_=r1b || r1b_armed_; state_=DataState::Busy;
}
void Decoder::end_busy(uint64_t sample, bool truncated) {
    if (!busy_active_) return;
    const std::string owner=busy_r1b_ ? "CMD"+number(unsigned(r1b_command_))+" R1b / DAT0 busy" : "Block "+number(blocks_)+" DAT0 busy";
    emit({busy_start_,sample,"busy",owner+(truncated ? " (truncated)" : " → released"),1,truncated,
        {{"block",number(blocks_)},{"sample_duration",number(sample-busy_start_)},{"boundary",raw_seen_ ? "raw DAT0 transitions" : "clock sampled"},{"complete",truncated ? "no" : "yes"}}});
    if (transfer_active_) transfer_busy_samples_+=sample-busy_start_;
    busy_active_=false;
    if (truncated) { state_=DataState::Idle; return; }
    if (r1b_armed_) { r1b_armed_=false; state_=DataState::Idle; if (stop_requested_) finish_transfer(sample,false); }
    else if (!data_multi_ || (transfer_count_ && blocks_>=transfer_count_)) { state_=DataState::Idle; finish_transfer(sample,false); }
    else state_=DataState::Start;
}
void Decoder::finish_transfer(uint64_t sample, bool truncated) {
    if (!transfer_active_) return;
    const bool bad=truncated || bad_blocks_ || rejected_blocks_;
    emit({transfer_start_,sample,"transfer",(inferred_ ? "Inferred " : "")+std::string(data_write_ ? "write" : "read")+" transfer: "+number(blocks_)+" blocks"+(truncated ? " (incomplete)" : ""),1,bad,
        {{"blocks",number(blocks_)},{"bad_data_blocks",number(bad_blocks_)},{"rejected_or_missing_status",number(rejected_blocks_)},{"DAT0_busy_samples",number(transfer_busy_samples_)},{"preerase_hint",number(transfer_preerase_)},{"explicit_CMD23_count",number(transfer_count_)},{"completion",truncated ? "capture/transaction incomplete" : "observed bus transfer end; not media persistence proof"}}});
    transfer_active_=false; state_=DataState::Idle;
}
void Decoder::finish(uint64_t sample) {
    if (!cmd_bits_.empty()) diagnostic(cmd_start_,sample,0,"Truncated CMD/response token ("+number(cmd_bits_.size())+" bits)");
    if (busy_active_) end_busy(sample,true);
    else if (state_==DataState::Payload || state_==DataState::Crc || state_==DataState::End) diagnostic(block_start_,sample,1,"Truncated data block");
    else if (state_==DataState::StatusWait || state_==DataState::StatusBits) diagnostic(status_start_,sample,1,"Truncated/missing write CRC status");
    finish_transfer(sample,true); cmd_bits_.clear(); state_=DataState::Idle; r1b_armed_=false;
}
} // namespace sd
