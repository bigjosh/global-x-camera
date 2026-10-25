cmake_minimum_required(VERSION 3.20)
project(GlobalXNativeSD VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  add_compile_options(/utf-8)
endif()
option(SD_BUILD_PLUGIN "Build the Saleae Logic 2 native analyzer" ON)
set(SALEAE_SDK_ROOT "" CACHE PATH "Existing Saleae AnalyzerSDK checkout; otherwise fetch pinned revision")

add_library(sd_native_core STATIC src/SdNativeDecoder.cpp)
target_include_directories(sd_native_core PUBLIC src)
if(MSVC)
  target_compile_options(sd_native_core PRIVATE /W4 /permissive-)
else()
  target_compile_options(sd_native_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

include(CTest)
if(BUILD_TESTING)
  add_executable(sd_native_tests tests/decoder_tests.cpp)
  target_link_libraries(sd_native_tests PRIVATE sd_native_core)
  add_test(NAME native_sd_decoder COMMAND sd_native_tests)
endif()

add_executable(sd_native_replay src/replay.cpp)
target_link_libraries(sd_native_replay PRIVATE sd_native_core)

if(BUILD_TESTING)
  find_package(Python3 COMPONENTS Interpreter QUIET)
  if(Python3_FOUND)
    add_test(NAME recorded_sd_waveforms
      COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_recordings.py"
        --replay "$<TARGET_FILE:sd_native_replay>")
  endif()
endif()

if(SD_BUILD_PLUGIN)
  if(NOT SALEAE_SDK_ROOT)
    include(FetchContent)
    FetchContent_Declare(saleae_sdk
      GIT_REPOSITORY https://github.com/saleae/AnalyzerSDK.git
      GIT_TAG e3c4b4ffda1c162c024a5913520aed17c6edb238)
    FetchContent_MakeAvailable(saleae_sdk)
    set(SALEAE_SDK_ROOT "${saleae_sdk_SOURCE_DIR}")
  endif()
  include("${SALEAE_SDK_ROOT}/AnalyzerSDKConfig.cmake")
  add_library(GlobalXNativeSD MODULE src/SdNativeAnalyzer.cpp)
  target_compile_definitions(GlobalXNativeSD PRIVATE LOGIC2 NOMINMAX)
  target_link_libraries(GlobalXNativeSD PRIVATE sd_native_core Saleae::AnalyzerSDK)
  set_target_properties(GlobalXNativeSD PROPERTIES
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/Analyzers"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/Analyzers")
  install(TARGETS GlobalXNativeSD RUNTIME DESTINATION Analyzers LIBRARY DESTINATION Analyzers)

  if(BUILD_TESTING AND Python3_FOUND)
    set(sdk_test_sources
      AnalyzerStubs.cpp HelperStubs.cpp MockChannelData.cpp MockResults.cpp
      MockSimulatedChannelDescriptor.cpp SettingsStubs.cpp StreamHelpers.cpp TestInstance.cpp)
    list(TRANSFORM sdk_test_sources PREPEND "${SALEAE_SDK_ROOT}/testlib/")
    add_executable(sd_adapter_tests src/SdNativeAnalyzer.cpp tests/adapter_tests.cpp
      tests/sdk_shim.cpp ${sdk_test_sources})
    target_compile_definitions(sd_adapter_tests PRIVATE LOGIC2 NOMINMAX)
    # Upstream SettingsStubs.cpp uses runtime_error without including it.
    # Supply the header in this test target without patching the pinned SDK.
    target_precompile_headers(sd_adapter_tests PRIVATE <stdexcept>)
    target_include_directories(sd_adapter_tests PRIVATE src tests
      "${SALEAE_SDK_ROOT}/include" "${SALEAE_SDK_ROOT}/testlib")
    target_link_libraries(sd_adapter_tests PRIVATE sd_native_core)
    add_test(NAME native_sd_adapter
      COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_adapter.py"
        --adapter "$<TARGET_FILE:sd_adapter_tests>")
  endif()
endif()
