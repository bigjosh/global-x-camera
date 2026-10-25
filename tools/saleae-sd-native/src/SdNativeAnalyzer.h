#pragma once

#include <Analyzer.h>
#include <AnalyzerResults.h>
#include <AnalyzerSettings.h>
#include <array>
#include <memory>
#include <mutex>
#include <vector>

#include "SdNativeDecoder.h"

// One DLL, two independent instances: select Commands for CMD bubbles and
// Data and busy for DAT0 bubbles. Saleae's result streams cannot overlap.
class SdNativeAnalyzerSettings final : public AnalyzerSettings {
public:
    SdNativeAnalyzerSettings();
    bool SetSettingsFromInterfaces() override;
    void LoadSettings(const char* settings) override;
    const char* SaveSettings() override;

    std::array<Channel, 6> channels; // CLK, CMD, DAT0, DAT1, DAT2, DAT3
    sd::Config config;
    bool falling_edge = false;
    unsigned sample_offset = 0;
    int waveform_track = 0;
    bool complete_capture = false;

private:
    void UpdateInterfaces();
    void RegisterChannels();
    std::array<std::unique_ptr<AnalyzerSettingInterfaceChannel>, 6> channel_interfaces_;
    std::unique_ptr<AnalyzerSettingInterfaceNumberList> width_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceNumberList> edge_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceNumberList> track_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceNumberList> data_only_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceNumberList> capture_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceInteger> offset_interface_;
    std::unique_ptr<AnalyzerSettingInterfaceInteger> block_interface_;
};

class SdNativeAnalyzer;

class SdNativeAnalyzerResults final : public AnalyzerResults {
public:
    SdNativeAnalyzerResults(SdNativeAnalyzer* analyzer, SdNativeAnalyzerSettings* settings);
    void Record(const sd::Event& event);
    void GenerateBubbleText(U64 frame_index, Channel& channel, DisplayBase display_base) override;
    void GenerateExportFile(const char* file, DisplayBase display_base, U32 export_type_user_id) override;
    void GenerateFrameTabularText(U64 frame_index, DisplayBase display_base) override;
    void GeneratePacketTabularText(U64 packet_id, DisplayBase display_base) override;
    void GenerateTransactionTabularText(U64 transaction_id, DisplayBase display_base) override;

private:
    std::string FrameText(U64 frame_index);
    SdNativeAnalyzer* analyzer_;
    SdNativeAnalyzerSettings* settings_;
    std::mutex events_mutex_;
    std::vector<sd::Event> events_;
    U64 last_frame_end_ = 0;
    bool have_frame_ = false;
};

class SdNativeAnalyzer final : public Analyzer2 {
public:
    SdNativeAnalyzer();
    ~SdNativeAnalyzer() override;
    void SetupResults() override;
    void WorkerThread() override;
    U32 GenerateSimulationData(U64 newest_sample_requested, U32 sample_rate,
                              SimulationChannelDescriptor** simulation_channels) override;
    U32 GetMinimumSampleRateHz() override;
    const char* GetAnalyzerName() const override;
    bool NeedsRerun() override;

private:
    std::unique_ptr<SdNativeAnalyzerSettings> settings_;
    std::unique_ptr<SdNativeAnalyzerResults> results_;
};

extern "C" {
ANALYZER_EXPORT const char* __cdecl GetAnalyzerName();
ANALYZER_EXPORT Analyzer* __cdecl CreateAnalyzer();
ANALYZER_EXPORT void __cdecl DestroyAnalyzer(Analyzer* analyzer);
}
