#include "SdNativeAnalyzer.h"

#include <AnalyzerChannelData.h>
#include <AnalyzerHelpers.h>
#include <algorithm>
#include <deque>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>

namespace {
constexpr const char* kName = "Global X Native SD";
constexpr const char* kChannels[] = {"CLK", "CMD", "DAT0", "DAT1", "DAT2", "DAT3"};

bool Defined(const Channel& channel) { return channel != UNDEFINED_CHANNEL; }

std::string Csv(const std::string& text) {
    std::string result = "\"";
    for (char c : text) {
        if (c == '"') result += '"';
        result += c;
    }
    return result + '"';
}

double RelativeSeconds(U64 sample, U64 trigger, U32 rate) {
    return sample >= trigger ? double(sample - trigger) / rate : -double(trigger - sample) / rate;
}

bool TimelineType(const sd::Event& event) {
    // Transfer summaries span their children. Width notices are zero-length
    // annotations already described by the associated response.
    return event.type != "transfer" && event.type != "bus_width";
}
} // namespace

SdNativeAnalyzerSettings::SdNativeAnalyzerSettings() {
    for (size_t i = 0; i < channels.size(); ++i) {
        channels[i] = UNDEFINED_CHANNEL;
        channel_interfaces_[i].reset(new AnalyzerSettingInterfaceChannel());
        channel_interfaces_[i]->SetTitleAndTooltip(kChannels[i],
            i == 0 ? "Native SD clock (not SPI chip select)." :
            i == 1 ? "Native bidirectional command/response signal; optional only in explicit data-only mode." :
            i == 2 ? "DAT0 data, CRC status and card busy. Required in every mode." :
                     "Additional native SD data lane; required for automatic or four-bit decoding.");
        channel_interfaces_[i]->SetSelectionOfNoneIsAllowed(i != 0 && i != 2);
        AddInterface(channel_interfaces_[i].get());
    }

    width_interface_.reset(new AnalyzerSettingInterfaceNumberList());
    width_interface_->SetTitleAndTooltip("Bus width", "Auto starts in one-bit mode and follows valid ACMD6 responses.");
    width_interface_->AddNumber(0, "Auto (start 1-bit)", "Use for a capture containing initialization and bus-width negotiation.");
    width_interface_->AddNumber(1, "1-bit", "Force native SD one-bit data mode.");
    width_interface_->AddNumber(4, "4-bit", "Force native SD four-bit data mode; useful when initialization was not captured.");
    AddInterface(width_interface_.get());

    edge_interface_.reset(new AnalyzerSettingInterfaceNumberList());
    edge_interface_->SetTitleAndTooltip("Clock edge", "Clock edge at which CMD and DAT are sampled.");
    edge_interface_->AddNumber(0, "Rising", "Normal native SD SDR sampling edge.");
    edge_interface_->AddNumber(1, "Falling", "Diagnostic alternative; select only when appropriate for the recording.");
    AddInterface(edge_interface_.get());

    offset_interface_.reset(new AnalyzerSettingInterfaceInteger());
    offset_interface_->SetTitleAndTooltip("Sample offset", "Nonnegative acquisition-sample delay after the selected clock edge. Default 0; does not move raw DAT0 busy edges.");
    offset_interface_->SetMin(0);
    offset_interface_->SetMax(1000);
    AddInterface(offset_interface_.get());

    block_interface_.reset(new AnalyzerSettingInterfaceInteger());
    block_interface_->SetTitleAndTooltip("Initial block bytes", "Initial data block length; normal SDHC/SDXC memory blocks are 512 bytes. Valid CMD16 can change the decoder state.");
    block_interface_->SetMin(1);
    block_interface_->SetMax(65536);
    AddInterface(block_interface_.get());

    data_only_interface_.reset(new AnalyzerSettingInterfaceNumberList());
    data_only_interface_->SetTitleAndTooltip("Data-only mode", "Explicit inference mode for a missing CMD probe. Commands and block addresses cannot be reconstructed in this mode.");
    data_only_interface_->AddNumber(0, "Off (decode CMD)", "Decode commands and derive transfer direction and length from them.");
    data_only_interface_->AddNumber(1, "Read blocks (CMD missing)", "Infer consecutive read blocks; requires forced bus width.");
    data_only_interface_->AddNumber(2, "Write blocks (CMD missing)", "Infer consecutive write blocks and DAT0 status/busy; requires forced bus width.");
    AddInterface(data_only_interface_.get());

    track_interface_.reset(new AnalyzerSettingInterfaceNumberList());
    track_interface_->SetTitleAndTooltip("Waveform view", "Add two analyzer instances for simultaneous CMD and DAT0 bubbles. Each instance's CSV export includes all events with their actual overlapping intervals.");
    track_interface_->AddNumber(0, "Commands", "CMD commands and responses, with card-state fields in the table.");
    track_interface_->AddNumber(1, "Data and busy", "DAT blocks, write acceptance and actual DAT0-low busy intervals.");
    AddInterface(track_interface_.get());

    capture_interface_.reset(new AnalyzerSettingInterfaceNumberList());
    capture_interface_->SetTitleAndTooltip("Capture mode", "Live mode waits for future data. Complete mode is only for a recording that has finished processing; trailing incomplete intervals end at the last observed CLK/DAT0 edge, not the capture boundary.");
    capture_interface_->AddNumber(0, "Live capture", "Safe when adding the analyzer before recording starts.");
    capture_interface_->AddNumber(1, "Complete capture", "For loaded/stopped captures; finalize truncated packets at the last observed edge.");
    AddInterface(capture_interface_.get());

    AddExportOption(0, "All SD events (CSV; parallel intervals preserved)");
    AddExportExtension(0, "CSV", "csv");
    UpdateInterfaces();
    RegisterChannels();
}

void SdNativeAnalyzerSettings::RegisterChannels() {
    ClearChannels();
    for (size_t i = 0; i < channels.size(); ++i)
        AddChannel(channels[i], kChannels[i], Defined(channels[i]));
}

void SdNativeAnalyzerSettings::UpdateInterfaces() {
    for (size_t i = 0; i < channels.size(); ++i) channel_interfaces_[i]->SetChannel(channels[i]);
    width_interface_->SetNumber(config.width);
    edge_interface_->SetNumber(falling_edge ? 1 : 0);
    offset_interface_->SetInteger(int(sample_offset));
    block_interface_->SetInteger(int(config.initial_block_bytes));
    data_only_interface_->SetNumber(config.data_only);
    track_interface_->SetNumber(waveform_track);
    capture_interface_->SetNumber(complete_capture ? 1 : 0);
}

bool SdNativeAnalyzerSettings::SetSettingsFromInterfaces() {
    std::array<Channel, 6> selected;
    for (size_t i = 0; i < selected.size(); ++i) selected[i] = channel_interfaces_[i]->GetChannel();
    const int width = int(width_interface_->GetNumber());
    const int data_only = int(data_only_interface_->GetNumber());
    const int track = int(track_interface_->GetNumber());
    const int edge = int(edge_interface_->GetNumber());
    const int offset = offset_interface_->GetInteger();
    const int bytes = block_interface_->GetInteger();
    const int complete = int(capture_interface_->GetNumber());
    if (!Defined(selected[0]) || !Defined(selected[2])) {
        SetErrorText("CLK and DAT0 are required."); return false;
    }
    if (width != 0 && width != 1 && width != 4) {
        SetErrorText("Choose automatic, one-bit or four-bit bus width."); return false;
    }
    if (data_only < 0 || data_only > 2 || track < 0 || track > 1 || edge < 0 || edge > 1 ||
        complete < 0 || complete > 1 || offset < 0 || offset > 1000 || bytes < 1 || bytes > 65536) {
        SetErrorText("Invalid analyzer setting."); return false;
    }
    if (data_only == 0 && !Defined(selected[1])) {
        SetErrorText("Select CMD, or explicitly enable a data-only mode."); return false;
    }
    if (data_only != 0 && width == 0) {
        SetErrorText("Data-only mode needs an explicit 1-bit or 4-bit width."); return false;
    }
    if (data_only != 0 && track == 0) {
        SetErrorText("Select Data and busy waveform view for data-only mode."); return false;
    }
    if (width != 1 && (!Defined(selected[3]) || !Defined(selected[4]) || !Defined(selected[5]))) {
        SetErrorText("Automatic and four-bit modes require all four data lanes."); return false;
    }
    for (size_t i = 0; i < selected.size(); ++i)
        for (size_t j = i + 1; j < selected.size(); ++j)
            if (Defined(selected[i]) && selected[i] == selected[j]) {
                SetErrorText("Every selected signal must use a different digital channel."); return false;
            }
    channels = selected;
    config.width = static_cast<sd::Config::Width>(width);
    config.data_only = static_cast<sd::Config::DataOnly>(data_only);
    config.initial_block_bytes = unsigned(bytes);
    falling_edge = edge != 0;
    sample_offset = unsigned(offset);
    waveform_track = track;
    complete_capture = complete != 0;
    RegisterChannels();
    return true;
}

void SdNativeAnalyzerSettings::LoadSettings(const char* settings) {
    // Logic 2 normally serializes interfaces itself; retain the SDK legacy
    // round trip for external harnesses and older saved analyzer records.
    SimpleArchive archive;
    archive.SetString(settings);
    U32 version = 0;
    if (!(archive >> version) || version != 1) return;
    for (auto& channel : channels) if (!(archive >> channel)) return;
    U32 width = 0, data_only = 0, offset = 0, bytes = 512, track = 0;
    bool edge = false, complete = false;
    if (!(archive >> width) || !(archive >> data_only) || !(archive >> edge) ||
        !(archive >> offset) || !(archive >> bytes) || !(archive >> track) || !(archive >> complete)) return;
    if ((width != 0 && width != 1 && width != 4) || data_only > 2 || offset > 1000 ||
        bytes < 1 || bytes > 65536 || track > 1) return;
    config.width = static_cast<sd::Config::Width>(width);
    config.data_only = static_cast<sd::Config::DataOnly>(data_only);
    config.initial_block_bytes = bytes;
    falling_edge = edge;
    sample_offset = offset;
    waveform_track = int(track);
    complete_capture = complete;
    UpdateInterfaces();
    RegisterChannels();
}

const char* SdNativeAnalyzerSettings::SaveSettings() {
    SimpleArchive archive;
    archive << U32(1);
    for (auto& channel : channels) archive << channel;
    archive << U32(config.width); archive << U32(config.data_only); archive << falling_edge;
    archive << U32(sample_offset); archive << U32(config.initial_block_bytes);
    archive << U32(waveform_track); archive << complete_capture;
    return SetReturnString(archive.GetString());
}

SdNativeAnalyzerResults::SdNativeAnalyzerResults(SdNativeAnalyzer* analyzer, SdNativeAnalyzerSettings* settings)
    : analyzer_(analyzer), settings_(settings) {}

void SdNativeAnalyzerResults::Record(const sd::Event& event) {
    U64 index;
    {
        std::lock_guard<std::mutex> lock(events_mutex_);
        index = events_.size();
        events_.push_back(event);
    }
    if (event.track != settings_->waveform_track || !TimelineType(event) || event.end <= event.start)
        return;
    // Never move or shorten a real BUSY interval to accommodate a concurrent
    // CMD response. Separate analyzer instances solve that SDK limitation.
    // Same-track malformed/diagnostic overlaps remain in the all-events CSV.
    if (have_frame_ && event.start <= last_frame_end_) return;

    Frame frame;
    frame.mStartingSampleInclusive = event.start;
    frame.mEndingSampleInclusive = event.end;
    frame.mData1 = index;
    frame.mData2 = 0;
    frame.mType = 0;
    frame.mFlags = event.error ? DISPLAY_AS_ERROR_FLAG : 0;
    AddFrame(frame);

    const U32 rate = std::max<U32>(1, analyzer_->GetSampleRate());
    const U64 trigger = analyzer_->GetTriggerSample();
    FrameV2 table;
    table.AddString("description", event.text.c_str());
    table.AddString("signal", event.track == 0 ? "CMD" : "DAT");
    table.AddBoolean("error", event.error);
    table.AddInteger("start_sample", S64(event.start));
    table.AddInteger("end_sample", S64(event.end));
    table.AddDouble("start_s", RelativeSeconds(event.start, trigger, rate));
    table.AddDouble("end_s", RelativeSeconds(event.end, trigger, rate));
    table.AddDouble("duration_us", double(event.end - event.start) * 1e6 / rate);
    for (const auto& field : event.fields) table.AddString(field.first.c_str(), field.second.c_str());
    AddFrameV2(table, event.type.c_str(), event.start, event.end);
    last_frame_end_ = event.end;
    have_frame_ = true;
    CommitResults();
}

std::string SdNativeAnalyzerResults::FrameText(U64 frame_index) {
    const U64 event_index = GetFrame(frame_index).mData1;
    std::lock_guard<std::mutex> lock(events_mutex_);
    if (event_index >= events_.size()) return "SD event unavailable";
    const auto& event = events_[size_t(event_index)];
    std::ostringstream text;
    text << event.text;
    if (event.type == "busy")
        text << " [" << std::fixed << std::setprecision(3)
             << double(event.end - event.start) * 1e6 / std::max<U32>(1, analyzer_->GetSampleRate()) << " us]";
    return text.str();
}

void SdNativeAnalyzerResults::GenerateBubbleText(U64 frame_index, Channel&, DisplayBase) {
    ClearResultStrings();
    const auto text = FrameText(frame_index);
    AddResultString(text.c_str());
}

void SdNativeAnalyzerResults::GenerateFrameTabularText(U64 frame_index, DisplayBase) {
    ClearTabularText();
    const auto text = FrameText(frame_index);
    AddTabularText(text.c_str());
}

void SdNativeAnalyzerResults::GeneratePacketTabularText(U64, DisplayBase) { ClearTabularText(); }
void SdNativeAnalyzerResults::GenerateTransactionTabularText(U64, DisplayBase) { ClearTabularText(); }

void SdNativeAnalyzerResults::GenerateExportFile(const char* file, DisplayBase, U32) {
    std::vector<sd::Event> events;
    {
        std::lock_guard<std::mutex> lock(events_mutex_);
        events = events_;
    }
    std::stable_sort(events.begin(), events.end(), [](const sd::Event& a, const sd::Event& b) {
        return a.start == b.start ? a.end < b.end : a.start < b.start;
    });
    const U32 rate = std::max<U32>(1, analyzer_->GetSampleRate());
    const U64 trigger = analyzer_->GetTriggerSample();
    std::ofstream output(file, std::ios::binary);
    output << "start_sample,end_sample,start_s,end_s,duration_us,signal,type,error,description,fields\n";
    output << std::setprecision(15);
    for (size_t i = 0; i < events.size(); ++i) {
        const auto& event = events[i];
        std::string fields;
        for (const auto& field : event.fields) {
            if (!fields.empty()) fields += "; ";
            fields += field.first + "=" + field.second;
        }
        output << event.start << ',' << event.end << ','
               << RelativeSeconds(event.start, trigger, rate) << ','
               << RelativeSeconds(event.end, trigger, rate) << ','
               << double(event.end - event.start) * 1e6 / rate << ','
               << (event.track == 0 ? "CMD" : "DAT") << ',' << Csv(event.type) << ','
               << (event.error ? "true" : "false") << ',' << Csv(event.text) << ',' << Csv(fields) << '\n';
        if (UpdateExportProgressAndCheckForCancel(i + 1, events.size())) return;
    }
}

SdNativeAnalyzer::SdNativeAnalyzer() : settings_(new SdNativeAnalyzerSettings()) {
    SetAnalyzerSettings(settings_.get());
    UseFrameV2();
}

SdNativeAnalyzer::~SdNativeAnalyzer() { KillThread(); }

void SdNativeAnalyzer::SetupResults() {
    results_.reset(new SdNativeAnalyzerResults(this, settings_.get()));
    SetAnalyzerResults(results_.get());
    const size_t channel = settings_->waveform_track == 0 ? 1 : 2;
    if (Defined(settings_->channels[channel])) results_->AddChannelBubblesWillAppearOn(settings_->channels[channel]);
}

void SdNativeAnalyzer::WorkerThread() {
    std::array<AnalyzerChannelData*, 6> input{};
    for (size_t i = 0; i < input.size(); ++i)
        if (Defined(settings_->channels[i])) input[i] = GetAnalyzerChannelData(settings_->channels[i]);
    auto* clock = input[0];
    auto* dat0 = input[2];
    if (!clock || !dat0) return;
    sd::Decoder decoder(settings_->config, [this](const sd::Event& event) { results_->Record(event); });
    decoder.dat0_edge(0, dat0->GetBitState() == BIT_HIGH);
    std::deque<U64> samples;
    U64 last_observed = 0;
    U64 iterations = 0;
    bool clock_exhausted = false;
    bool dat0_exhausted = false;
    constexpr U64 never = std::numeric_limits<U64>::max();

    for (;;) {
        const bool have_clock = !clock_exhausted && clock->DoMoreTransitionsExistInCurrentData();
        if (!have_clock && settings_->complete_capture) clock_exhausted = true;
        const U64 clock_edge = have_clock ? clock->GetSampleOfNextEdge() : never;
        const U64 delayed_sample = samples.empty() ? never : samples.front();
        const U64 boundary = std::min(clock_edge, delayed_sample);
        U64 data_edge = never;

        if (boundary != never) {
            // A known clock/sample provides a bounded look-ahead. Calling
            // DoMoreTransitions... on a quiet DAT0 every clock can wait 250 ms
            // per bit; WouldAdvancing... avoids that pathological slowdown.
            if (!have_clock && !clock_exhausted && clock->GetSampleNumber() < boundary &&
                clock->WouldAdvancingToAbsPositionCauseTransition(boundary)) continue;
            if (!dat0_exhausted && dat0->GetSampleNumber() < boundary &&
                dat0->WouldAdvancingToAbsPositionCauseTransition(boundary))
                data_edge = dat0->GetSampleOfNextEdge();
        } else {
            // CLK has no visible edge. Look for raw DAT0 independently so a
            // card releasing BUSY after the last clock is still decoded.
            const bool have_dat0 = !dat0_exhausted && dat0->DoMoreTransitionsExistInCurrentData();
            if (!have_dat0 && settings_->complete_capture) dat0_exhausted = true;
            if (have_dat0) {
                data_edge = dat0->GetSampleOfNextEdge();
                // Channels may be processed asynchronously during acquisition.
                // Wait for CLK to catch up before declaring DAT0 the next edge.
                if (!clock_exhausted && clock->GetSampleNumber() < data_edge &&
                    clock->WouldAdvancingToAbsPositionCauseTransition(data_edge)) continue;
            }
        }
        const U64 next = std::min(boundary, data_edge);

        if (next == never) {
            results_->CommitResults();
            ReportProgress(last_observed);
            CheckIfThreadShouldExit();
            if (settings_->complete_capture) {
                // The user asserted complete input. The SDK has no final
                // capture-sample API: only claim this observed lower bound.
                decoder.finish(last_observed);
                results_->CommitResults();
                return;
            }
            // DoMoreTransitions... waits up to 250 ms. False only describes
            // currently processed data, so it must not terminate live input.
            continue;
        }

        if (data_edge == next) {
            dat0->AdvanceToNextEdge();
            decoder.dat0_edge(next, dat0->GetBitState() == BIT_HIGH);
        }
        if (clock_edge == next) {
            clock->AdvanceToNextEdge();
            const bool selected = (clock->GetBitState() == BIT_HIGH) != settings_->falling_edge;
            if (selected && next <= never - settings_->sample_offset)
                samples.push_back(next + settings_->sample_offset);
        }
        // DAT0 raw edges are always delivered before a coincident sampled bit.
        // A delayed sample is queued rather than advancing other cursors past
        // intervening clock/DAT0 edges.
        if (!samples.empty() && samples.front() == next) {
            samples.pop_front();
            if (input[1]) input[1]->AdvanceToAbsPosition(next);
            uint8_t dat = 0;
            for (size_t lane = 0; lane < 4; ++lane) {
                auto* channel = input[2 + lane];
                if (channel) {
                    channel->AdvanceToAbsPosition(next);
                    if (channel->GetBitState() == BIT_HIGH) dat |= uint8_t(1u << lane);
                } else dat |= uint8_t(1u << lane);
            }
            decoder.clock(next, !input[1] || input[1]->GetBitState() == BIT_HIGH, dat);
        }
        last_observed = std::max(last_observed, next);
        if ((++iterations & 4095u) == 0) {
            results_->CommitResults();
            ReportProgress(last_observed);
            CheckIfThreadShouldExit();
        }
    }
}

U32 SdNativeAnalyzer::GenerateSimulationData(U64, U32, SimulationChannelDescriptor** simulation_channels) {
    *simulation_channels = nullptr;
    return 0; // Deterministic protocol fixtures are supplied by the test suite.
}

U32 SdNativeAnalyzer::GetMinimumSampleRateHz() { return 1000000; }
const char* SdNativeAnalyzer::GetAnalyzerName() const { return kName; }
bool SdNativeAnalyzer::NeedsRerun() { return false; }

extern "C" {
const char* __cdecl GetAnalyzerName() { return kName; }
Analyzer* __cdecl CreateAnalyzer() { return new SdNativeAnalyzer(); }
void __cdecl DestroyAnalyzer(Analyzer* analyzer) { delete analyzer; }
}
