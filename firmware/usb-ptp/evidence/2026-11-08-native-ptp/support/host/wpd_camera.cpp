// Native Windows Portable Devices client. Uses the installed PTP class driver.
// No libusb/WinUSB driver replacement and no direct USB endpoint access.
#define NOMINMAX
#include <windows.h>
#include <PortableDeviceApi.h>
#include <PortableDevice.h>
#include <PortableDeviceTypes.h>
#include <propvarutil.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using Microsoft::WRL::ComPtr;

struct Failure : std::runtime_error {
    HRESULT hr;
    Failure(const std::string& where, HRESULT h) : std::runtime_error(where), hr(h) {}
};
void check(HRESULT h, const char* where) { if (FAILED(h)) throw Failure(where, h); }
std::string utf8(const std::wstring& s) {
    if (s.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), (int)s.size(), nullptr, 0, nullptr, nullptr);
    if (!n) throw Failure("UTF-16 conversion", HRESULT_FROM_WIN32(GetLastError()));
    std::string r(n, '\0');
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, s.data(), (int)s.size(), r.data(), n, nullptr, nullptr);
    return r;
}
std::string json(const std::string& s) {
    std::ostringstream o; o << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') o << '\\' << c;
        else if (c < 32) o << "\\u" << std::hex << std::setw(4) << std::setfill('0') << (unsigned)c << std::dec;
        else o << c;
    }
    o << '"'; return o.str();
}
std::string json(const std::wstring& s) { return json(utf8(s)); }
std::string hexhr(HRESULT h) {
    std::ostringstream o; o << "0x" << std::hex << std::setw(8) << std::setfill('0') << (uint32_t)h; return o.str();
}
std::wstring guidstr(REFGUID g) { wchar_t b[40]{}; StringFromGUID2(g,b,40); return b; }
uint64_t monotonic_us() {
    static const auto epoch=std::chrono::steady_clock::now();
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-epoch).count());
}
void emit(const std::string& s) {
    static std::mutex output_mutex;
    std::lock_guard<std::mutex> lock(output_mutex);
    // Serialize complete JSON records across the reader and cancellation thread.
    if(!s.empty() && s.back()=='}') std::cout << s.substr(0,s.size()-1) << ",\"mono_us\":" << monotonic_us() << ",\"thread_id\":" << GetCurrentThreadId() << "}" << std::endl;
    else std::cout << s << std::endl;
}
struct ComInit {
    ComInit() { check(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "CoInitializeEx"); }
    ~ComInit() { CoUninitialize(); }
};

// One timer per download. The callback captures the SAME free-threaded WPD
// instance as the pending GetStream/Read; opening a second device would cancel
// a different session. The injected callback also permits hardware-free tests.
class AsyncCancel {
    using Clock=std::chrono::steady_clock;
    std::function<HRESULT()> cancel_;
    uint32_t delay_ms_,join_ms_;
    std::thread worker_;
    std::mutex mutex_;
    std::condition_variable changed_;
    bool stopping_=false,started_=false,active_=false,attempted_=false,finished_=false;
    uint64_t phase_=0;
    std::string operation_;
    Clock::time_point began_;
    HRESULT cancel_hr_=S_FALSE,worker_hr_=S_OK;

    void run() noexcept {
        try {
            ComInit com;
            std::unique_lock<std::mutex> lock(mutex_);
            changed_.wait(lock,[&]{return stopping_||started_;});
            if(stopping_) return;
            if(changed_.wait_until(lock,began_+std::chrono::milliseconds(delay_ms_),[&]{return stopping_;})) return;
            // If the timer expires between calls, wait for the next actual API
            // scope. Never call Cancel solely because a prior read completed.
            changed_.wait(lock,[&]{return stopping_||active_;});
            if(stopping_) return;
            attempted_=true;
            auto phase=phase_; auto name=operation_;
            lock.unlock();
            emit("{\"event\":\"async_cancel_begin\",\"phase\":"+std::to_string(phase)+",\"operation_observed\":"+json(name)+",\"api_scope_active_observed\":true}");
            const HRESULT result=cancel_();
            lock.lock(); cancel_hr_=result;
            bool same_scope_active=active_&&phase_==phase;
            lock.unlock();
            emit("{\"event\":\"async_cancel_end\",\"phase\":"+std::to_string(phase)+",\"hresult\":"+json(hexhr(result))+",\"same_scope_active_at_return\":"+(same_scope_active?"true":"false")+"}");
        } catch(const Failure& e) {
            std::lock_guard<std::mutex> lock(mutex_); worker_hr_=e.hr;
        } catch(...) {
            std::lock_guard<std::mutex> lock(mutex_); worker_hr_=E_FAIL;
        }
    }
public:
    AsyncCancel(std::function<HRESULT()> cancel,uint32_t delay_ms,uint32_t join_ms=5000)
      :cancel_(std::move(cancel)),delay_ms_(delay_ms),join_ms_(join_ms) {
        if(delay_ms_) worker_=std::thread([this]{run();});
    }
    AsyncCancel(const AsyncCancel&)=delete;
    AsyncCancel& operator=(const AsyncCancel&)=delete;
    ~AsyncCancel() noexcept { finish(); }

    void begin(const char* operation) {
        uint64_t phase;
        { std::lock_guard<std::mutex> lock(mutex_);
          operation_=operation; active_=true; phase=++phase_;
          if(!started_) { started_=true; began_=Clock::now(); }
        }
        emit("{\"event\":\"wpd_api_begin\",\"phase\":"+std::to_string(phase)+",\"operation\":"+json(std::string(operation))+"}");
        changed_.notify_all();
    }
    void end(HRESULT h,uint64_t bytes=0) {
        uint64_t phase; std::string name;
        { std::lock_guard<std::mutex> lock(mutex_); active_=false; phase=phase_; name=operation_; }
        emit("{\"event\":\"wpd_api_end\",\"phase\":"+std::to_string(phase)+",\"operation\":"+json(name)+",\"hresult\":"+json(hexhr(h))+",\"bytes\":"+std::to_string(bytes)+"}");
        changed_.notify_all();
    }
    bool attempted() { std::lock_guard<std::mutex> lock(mutex_); return attempted_; }
    HRESULT result() { std::lock_guard<std::mutex> lock(mutex_); return FAILED(worker_hr_)?worker_hr_:cancel_hr_; }
    void finish() noexcept {
        if(finished_) return;
        finished_=true;
        { std::lock_guard<std::mutex> lock(mutex_); stopping_=true; }
        changed_.notify_all();
        if(worker_.joinable()) {
            // A COM Cancel call itself can hang. Never leave a detached worker
            // referencing released interfaces or wait unboundedly in cleanup.
            DWORD wait=WaitForSingleObject(worker_.native_handle(),join_ms_);
            if(wait!=WAIT_OBJECT_0) {
                emit("{\"event\":\"async_cancel_worker_timeout\",\"join_timeout_ms\":"+std::to_string(join_ms_)+",\"wait_result\":"+std::to_string(wait)+",\"device_idle_proven\":false}");
                // Terminate this verification client only; no device reset or
                // power operation. The outer runner preserves the JSON log.
                std::quick_exit(124);
            }
            worker_.join();
        }
        if(delay_ms_) emit("{\"event\":\"async_cancel_summary\",\"attempted\":"+std::string(attempted_?"true":"false")+",\"cancel_hresult\":"+json(hexhr(cancel_hr_))+",\"worker_hresult\":"+json(hexhr(worker_hr_))+",\"worker_joined\":true,\"wire_cancel_proven\":false}");
    }
};

void async_cancel_selftest(bool stall=false) {
    std::atomic<unsigned> calls{0};
    HANDLE called=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    if(!called) throw Failure("test event",HRESULT_FROM_WIN32(GetLastError()));
    {
        AsyncCancel timer([&]{++calls; SetEvent(called); if(stall) Sleep(10000); return S_OK;},5,stall?30:1000);
        timer.begin("fake pending read");
        DWORD wait=WaitForSingleObject(called,1000);
        timer.end(HRESULT_FROM_WIN32(ERROR_OPERATION_ABORTED));
        timer.finish();
        if(wait!=WAIT_OBJECT_0||calls.load()!=1||timer.result()!=S_OK) throw Failure("async selftest overlap",E_FAIL);
    }
    CloseHandle(called);
    {
        AsyncCancel timer([&]{++calls; return S_OK;},10000,1000);
        timer.begin("fake fast read"); timer.end(S_OK,32); timer.finish();
        if(timer.attempted()||calls.load()!=1) throw Failure("async selftest disarm",E_FAIL);
    }
    emit("{\"event\":\"async_selftest\",\"success\":true,\"hardware_access\":false}");
}
template<class T> ComPtr<T> create(REFCLSID cls) {
    ComPtr<T> p; check(CoCreateInstance(cls,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&p)),"CoCreateInstance"); return p;
}
struct Device {
    ComPtr<IPortableDevice> p;
    ComPtr<IPortableDeviceContent> content;
    ComPtr<IPortableDeviceProperties> props;
    Device(const std::wstring& id, bool writing) {
        p = create<IPortableDevice>(CLSID_PortableDeviceFTM);
        auto client = create<IPortableDeviceValues>(CLSID_PortableDeviceValues);
        check(client->SetStringValue(WPD_CLIENT_NAME,L"Global X Camera qualification"),"client name");
        check(client->SetUnsignedIntegerValue(WPD_CLIENT_MAJOR_VERSION,1),"client version");
        check(client->SetUnsignedIntegerValue(WPD_CLIENT_MINOR_VERSION,0),"client version");
        check(client->SetUnsignedIntegerValue(WPD_CLIENT_REVISION,0),"client version");
        check(client->SetUnsignedIntegerValue(WPD_CLIENT_DESIRED_ACCESS,GENERIC_READ | (writing?GENERIC_WRITE:0)),"client access");
        check(p->Open(id.c_str(),client.Get()),"IPortableDevice::Open");
        check(p->Content(&content),"IPortableDevice::Content");
        check(content->Properties(&props),"IPortableDeviceContent::Properties");
    }
    ~Device() { props.Reset(); content.Reset(); if (p) p->Close(); }
};
std::wstring value_string(IPortableDeviceValues* v, REFPROPERTYKEY k) {
    PWSTR p=nullptr; if (FAILED(v->GetStringValue(k,&p))) return L"";
    std::wstring s = p?p:L""; CoTaskMemFree(p); return s;
}
struct Object {
    std::wstring id,name,filename,parent;
    GUID type{},format{};
    ULONGLONG size=0;
    BOOL deletable=FALSE;
    bool has_size=false,has_delete=false,has_type=false,has_format=false;
};
Object object(Device& d,const std::wstring& id) {
    auto keys=create<IPortableDeviceKeyCollection>(CLSID_PortableDeviceKeyCollection);
    const PROPERTYKEY wanted[]={WPD_OBJECT_NAME,WPD_OBJECT_ORIGINAL_FILE_NAME,WPD_OBJECT_PARENT_ID,WPD_OBJECT_CONTENT_TYPE,WPD_OBJECT_FORMAT,WPD_OBJECT_SIZE,WPD_OBJECT_CAN_DELETE};
    for (auto& k:wanted) check(keys->Add(k),"property key");
    ComPtr<IPortableDeviceValues> v; check(d.props->GetValues(id.c_str(),keys.Get(),&v),"GetValues");
    Object o; o.id=id; o.name=value_string(v.Get(),WPD_OBJECT_NAME); o.filename=value_string(v.Get(),WPD_OBJECT_ORIGINAL_FILE_NAME); o.parent=value_string(v.Get(),WPD_OBJECT_PARENT_ID);
    o.has_type=SUCCEEDED(v->GetGuidValue(WPD_OBJECT_CONTENT_TYPE,&o.type));
    o.has_format=SUCCEEDED(v->GetGuidValue(WPD_OBJECT_FORMAT,&o.format));
    o.has_size=SUCCEEDED(v->GetUnsignedLargeIntegerValue(WPD_OBJECT_SIZE,&o.size));
    o.has_delete=SUCCEEDED(v->GetBoolValue(WPD_OBJECT_CAN_DELETE,&o.deletable));
    return o;
}
void print_object(const Object& o) {
    std::ostringstream s; s << "{\"event\":\"object\",\"id\":" << json(o.id) << ",\"name\":" << json(o.name) << ",\"filename\":" << json(o.filename) << ",\"parent\":" << json(o.parent)
      << ",\"content_type\":" << (o.has_type?json(guidstr(o.type)):"null") << ",\"format\":" << (o.has_format?json(guidstr(o.format)):"null")
      << ",\"size\":" << (o.has_size?std::to_string(o.size):"null") << ",\"can_delete\":" << (o.has_delete?(o.deletable?"true":"false"):"null") << "}"; emit(s.str());
}
std::vector<std::wstring> children(Device& d,const std::wstring& parent) {
    ComPtr<IEnumPortableDeviceObjectIDs> en; check(d.content->EnumObjects(0,parent.c_str(),nullptr,&en),"EnumObjects");
    std::vector<std::wstring> out;
    for (;;) {
        PWSTR ids[32]{}; DWORD n=0; HRESULT h=en->Next(32,ids,&n);
        for (DWORD i=0;i<n;++i) { if(ids[i]) out.emplace_back(ids[i]); }
        for(auto id:ids) CoTaskMemFree(id);
        check(h,"IEnumPortableDeviceObjectIDs::Next");
        if (h==S_FALSE || n==0) break;
        if(out.size()>1000000) throw Failure("object count bound",E_UNEXPECTED);
    }
    return out;
}
void list_objects(Device& d,const std::wstring& parent,bool recursive) {
    std::vector<std::wstring> queue{parent}; std::set<std::wstring> seen;
    for(size_t i=0;i<queue.size();++i) {
        if(!seen.insert(queue[i]).second) continue;
        for(auto& id:children(d,queue[i])) {
            auto o=object(d,id); print_object(o);
            if(recursive && o.has_type && (IsEqualGUID(o.type,WPD_CONTENT_TYPE_FUNCTIONAL_OBJECT)||IsEqualGUID(o.type,WPD_CONTENT_TYPE_FOLDER))) queue.push_back(id);
        }
        if(!recursive) break;
        if(queue.size()>100000) throw Failure("container count bound",E_UNEXPECTED);
    }
}
void devices() {
    auto m=create<IPortableDeviceManager>(CLSID_PortableDeviceManager);
    check(m->RefreshDeviceList(),"RefreshDeviceList"); DWORD n=0;
    check(m->GetDevices(nullptr,&n),"GetDevices count");
    if(n>10000) throw Failure("device count bound",E_UNEXPECTED);
    std::vector<PWSTR> ids(n,nullptr);
    HRESULT h=n?m->GetDevices(ids.data(),&n):S_OK;
    if(FAILED(h)) { for(auto id:ids) CoTaskMemFree(id); check(h,"GetDevices"); }
    for(DWORD i=0;i<n;++i) {
        std::wstring id=ids[i]?ids[i]:L""; DWORD len=0;
        m->GetDeviceFriendlyName(id.c_str(),nullptr,&len);
        std::vector<wchar_t> name(std::max<DWORD>(len,1),0);
        if(len) m->GetDeviceFriendlyName(id.c_str(),name.data(),&len);
        emit("{\"event\":\"device\",\"id\":"+json(id)+",\"name\":"+json(std::wstring(name.data()))+"}");
    }
    for(auto id:ids) CoTaskMemFree(id);
}
struct File {
    HANDLE h=INVALID_HANDLE_VALUE;
    explicit File(const std::wstring& path) { h=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr); if(h==INVALID_HANDLE_VALUE) throw Failure("create new partial file",HRESULT_FROM_WIN32(GetLastError())); }
    ~File() { if(h!=INVALID_HANDLE_VALUE) CloseHandle(h); }
    void close() { if(h!=INVALID_HANDLE_VALUE) { check(FlushFileBuffers(h)?S_OK:HRESULT_FROM_WIN32(GetLastError()),"flush file"); CloseHandle(h); h=INVALID_HANDLE_VALUE; } }
};
void download(Device& d,const std::wstring& id,const std::wstring& path,bool thumb,uint64_t cancel_after,uint32_t cancel_ms) {
    Object o=object(d,id); print_object(o);
    if(GetFileAttributesW(path.c_str())!=INVALID_FILE_ATTRIBUTES) throw Failure("destination already exists",HRESULT_FROM_WIN32(ERROR_FILE_EXISTS));
    const auto partial=path+L".partial"; File f(partial);
    ComPtr<IPortableDeviceResources> resources; check(d.content->Transfer(&resources),"Transfer resources");
    ComPtr<IStream> stream; DWORD optimal=0;
    ComPtr<IPortableDevice> same_device=d.p;
    AsyncCancel timer([same_device]{return same_device->Cancel();},cancel_ms);
    auto finish_cancel=[&](HRESULT api_hr,uint64_t bytes) {
        timer.finish();
        stream.Reset(); f.close();
        const bool aborted=api_hr==E_ABORT||api_hr==HRESULT_FROM_WIN32(ERROR_OPERATION_ABORTED)||api_hr==HRESULT_FROM_WIN32(ERROR_CANCELLED);
        emit("{\"event\":\"download_async_cancel_observation\",\"bytes\":"+std::to_string(bytes)+",\"pending_api_hresult\":"+json(hexhr(api_hr))+",\"api_reported_cancellation\":"+(aborted?"true":"false")+",\"partial\":"+json(partial)+",\"wire_cancel_proven\":false}");
        check(timer.result(),"asynchronous Cancel worker");
    };
    timer.begin("GetStream");
    HRESULT stream_hr=resources->GetStream(id.c_str(),thumb?WPD_RESOURCE_THUMBNAIL:WPD_RESOURCE_DEFAULT,STGM_READ,&optimal,&stream);
    timer.end(stream_hr);
    if(timer.attempted()) { finish_cancel(stream_hr,0); return; }
    check(stream_hr,"GetStream");
    // Bound untrusted driver advice while retaining its normal preferred transfer size.
    DWORD chunk=optimal?std::min<DWORD>(optimal,1024*1024):65536;
    std::vector<uint8_t> buf(chunk); uint64_t total=0;
    emit("{\"event\":\"download_begin\",\"object\":"+json(id)+",\"partial\":"+json(partial)+",\"chunk_bytes\":"+std::to_string(chunk)+"}");
    for(;;) {
        ULONG got=0;
        timer.begin("Read");
        HRESULT h=stream->Read(buf.data(),chunk,&got);
        timer.end(h,got);
        // Preserve bytes even if a failing read reports usable partial data.
        if(got>chunk) throw Failure("IStream invalid length",E_UNEXPECTED);
        DWORD wrote=0;
        if(got && (!WriteFile(f.h,buf.data(),got,&wrote,nullptr)||wrote!=got)) throw Failure("WriteFile",HRESULT_FROM_WIN32(GetLastError()?GetLastError():ERROR_WRITE_FAULT));
        total+=got;
        emit("{\"event\":\"download_progress\",\"bytes\":"+std::to_string(total)+",\"read_hresult\":"+json(hexhr(h))+"}");
        if(timer.attempted()) { finish_cancel(h,total); return; }
        check(h,"IStream::Read (partial preserved)");
        if(cancel_after && total>=cancel_after) {
            HRESULT c=d.p->Cancel(); stream.Reset(); f.close();
            emit("{\"event\":\"download_cancelled\",\"bytes\":"+std::to_string(total)+",\"hresult\":"+json(hexhr(c))+",\"partial\":"+json(partial)+"}");
            check(c,"Cancel"); return;
        }
        if(h==S_FALSE || got==0) break;
        if(total>UINT64_C(8)*1024*1024*1024) throw Failure("download safety length bound",E_UNEXPECTED);
    }
    timer.finish();
    stream.Reset(); f.close();
    if(!thumb && o.has_size && total!=o.size) throw Failure("download size differs from ObjectInfo (partial preserved)",HRESULT_FROM_WIN32(ERROR_BAD_LENGTH));
    if(!MoveFileExW(partial.c_str(),path.c_str(),MOVEFILE_WRITE_THROUGH)) throw Failure("publish complete download",HRESULT_FROM_WIN32(GetLastError()));
    emit("{\"event\":\"download_complete\",\"bytes\":"+std::to_string(total)+",\"path\":"+json(path)+",\"size_checked\":"+std::string(!thumb&&o.has_size?"true":"false")+"}");
    if(cancel_ms && !timer.attempted()) {
        emit("{\"event\":\"async_cancel_window_missed\",\"download_complete\":true,\"wire_cancel_proven\":false}");
        check(timer.result(),"asynchronous Cancel worker");
        throw Failure("download completed before asynchronous cancellation",HRESULT_FROM_WIN32(ERROR_TIMEOUT));
    }
}
void remove_photo(Device& d,const std::wstring& id) {
    auto o=object(d,id); print_object(o);
    if(!o.has_type || !IsEqualGUID(o.type,WPD_CONTENT_TYPE_IMAGE)) throw Failure("refuse deletion of non-image object",E_INVALIDARG);
    if(o.has_delete && !o.deletable) throw Failure("object reports delete prohibited",E_ACCESSDENIED);
    auto ids=create<IPortableDevicePropVariantCollection>(CLSID_PortableDevicePropVariantCollection);
    PROPVARIANT v{}; check(InitPropVariantFromString(id.c_str(),&v),"object id");
    HRESULT add=ids->Add(&v); PropVariantClear(&v); check(add,"delete collection");
    ComPtr<IPortableDevicePropVariantCollection> results;
    HRESULT h=d.content->Delete(PORTABLE_DEVICE_DELETE_NO_RECURSION,ids.Get(),&results);
    DWORD n=0; if(results) check(results->GetCount(&n),"delete result count");
    bool failed=(h!=S_OK); bool result_ok=(n==0 && h==S_OK);
    for(DWORD i=0;i<n;++i) {
        PROPVARIANT r{}; check(results->GetAt(i,&r),"delete result");
        HRESULT per=(r.vt==VT_ERROR)?r.scode:E_UNEXPECTED;
        emit("{\"event\":\"delete_result\",\"index\":"+std::to_string(i)+",\"hresult\":"+json(hexhr(per))+"}");
        failed=failed||per!=S_OK; result_ok=result_ok||per==S_OK; PropVariantClear(&r);
    }
    emit("{\"event\":\"delete_complete\",\"object\":"+json(id)+",\"hresult\":"+json(hexhr(h))+",\"success\":"+(failed||!result_ok?"false":"true")+"}");
    if(failed||!result_ok) throw Failure("Delete did not report complete success",FAILED(h)?h:E_FAIL);
}
void decode_image(const std::wstring& path) {
    auto f=create<IWICImagingFactory>(CLSID_WICImagingFactory);
    ComPtr<IWICBitmapDecoder> dec; check(f->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,WICDecodeMetadataCacheOnLoad,&dec),"WIC CreateDecoderFromFilename");
    ComPtr<IWICBitmapFrameDecode> frame; check(dec->GetFrame(0,&frame),"WIC GetFrame");
    UINT w=0,h=0; GUID format{}; check(frame->GetSize(&w,&h),"WIC GetSize"); check(frame->GetPixelFormat(&format),"WIC GetPixelFormat");
    bool gray16=IsEqualGUID(format,GUID_WICPixelFormat16bppGray);
    ComPtr<IWICFormatConverter> conv; check(f->CreateFormatConverter(&conv),"WIC converter");
    check(conv->Initialize(frame.Get(),GUID_WICPixelFormat16bppGray,WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom),"WIC convert gray16");
    if(w>100000 || h>100000 || !w || !h) throw Failure("image dimensions out of bound",E_INVALIDARG);
    std::vector<uint16_t> row(w); uint16_t low=65535,high=0; uint64_t sum=0,nonzero=0,lowbits=0;
    for(UINT y=0;y<h;++y) { WICRect r{0,(INT)y,(INT)w,1}; check(conv->CopyPixels(&r,w*2,w*2,reinterpret_cast<BYTE*>(row.data())),"WIC decode pixels"); for(auto p:row) { low=std::min(low,p); high=std::max(high,p); sum+=p; nonzero+=(p!=0); lowbits+=(p&63)!=0; } }
    emit("{\"event\":\"image_decoded\",\"path\":"+json(path)+",\"width\":"+std::to_string(w)+",\"height\":"+std::to_string(h)+",\"native_format\":"+json(guidstr(format))+",\"native_gray16\":"+(gray16?"true":"false")+",\"min\":"+std::to_string(low)+",\"max\":"+std::to_string(high)+",\"sum\":"+std::to_string(sum)+",\"nonzero_pixels\":"+std::to_string(nonzero)+",\"nonzero_low6_pixels\":"+std::to_string(lowbits)+"}");
}
void help() {
    std::cout << "wpd_camera devices\nwpd_camera list --device ID [--parent ID] [--recursive]\nwpd_camera info --device ID --object ID\nwpd_camera get|thumbnail --device ID --object ID --out FILE [--cancel-after BYTES | --cancel-ms MS]\nwpd_camera delete --device ID --object ID --confirm-object SAME_ID\nwpd_camera decode --file FILE\nwpd_camera selftest|async-selftest|async-stall-selftest\nAll results are UTF-8 JSON lines. Device operations use native WPD.\n";
}
int wmain(int argc,wchar_t** argv) {
    try {
        if(argc<2 || std::wstring(argv[1])==L"--help") { help(); return 0; }
        std::wstring cmd=argv[1]; std::map<std::wstring,std::wstring> args;
        bool recursive=false;
        for(int i=2;i<argc;++i) {
            std::wstring k=argv[i]; if(k==L"--recursive") { recursive=true; continue; }
            const std::set<std::wstring> allowed={L"--device",L"--object",L"--parent",L"--out",L"--file",L"--confirm-object",L"--cancel-after",L"--cancel-ms"};
            if(!allowed.count(k)||i+1>=argc||args.count(k)) throw Failure("invalid/duplicate argument",E_INVALIDARG);
            args[k]=argv[++i];
        }
        auto need=[&](const wchar_t* k) { auto v=args.find(k); if(v==args.end()||v->second.empty()) throw Failure("missing required argument",E_INVALIDARG); return v->second; };
        if(cmd==L"selftest") {
            if(json(std::string("a\n\"\\"))!="\"a\\u000a\\\"\\\\\"" || hexhr(E_FAIL)!="0x80004005" || utf8(L"\u03b1")!="\xce\xb1") throw Failure("selftest",E_FAIL);
            emit("{\"event\":\"selftest\",\"success\":true,\"hardware_access\":false}"); return 0;
        }
        if(cmd==L"async-selftest"||cmd==L"async-stall-selftest") { async_cancel_selftest(cmd==L"async-stall-selftest"); return 0; }
        if(cmd!=L"devices"&&cmd!=L"list"&&cmd!=L"info"&&cmd!=L"get"&&cmd!=L"thumbnail"&&cmd!=L"delete"&&cmd!=L"decode") throw Failure("unknown command",E_INVALIDARG);
        // Validate destructive argument identity before opening anything.
        if(cmd==L"delete" && need(L"--object")!=need(L"--confirm-object")) throw Failure("delete object confirmation differs",E_INVALIDARG);
        if(cmd==L"get"||cmd==L"thumbnail") { need(L"--object"); need(L"--out"); }
        if(cmd==L"info") need(L"--object");
        uint64_t cancel_after=0; uint32_t cancel_ms=0;
        const auto positive=[&](const wchar_t* key,uint64_t maximum) {
            const auto& s=args.at(key);
            if(s.empty()||s.find_first_not_of(L"0123456789")!=std::wstring::npos) throw Failure("invalid cancellation threshold",E_INVALIDARG);
            size_t used=0; uint64_t v=0;
            try { v=std::stoull(s,&used); } catch(...) { throw Failure("invalid cancellation threshold",E_INVALIDARG); }
            if(used!=s.size()||v==0||v>maximum) throw Failure("invalid cancellation threshold",E_INVALIDARG);
            return v;
        };
        if(args.count(L"--cancel-after")||args.count(L"--cancel-ms")) {
            if(cmd!=L"get"&&cmd!=L"thumbnail") throw Failure("cancellation applies only to downloads",E_INVALIDARG);
            if(args.count(L"--cancel-after")&&args.count(L"--cancel-ms")) throw Failure("choose one cancellation mode",E_INVALIDARG);
        }
        if(args.count(L"--cancel-after")) cancel_after=positive(L"--cancel-after",UINT64_MAX);
        if(args.count(L"--cancel-ms")) cancel_ms=static_cast<uint32_t>(positive(L"--cancel-ms",60000));
        ComInit com;
        if(cmd==L"devices") { devices(); return 0; }
        if(cmd==L"decode") { decode_image(need(L"--file")); return 0; }
        Device d(need(L"--device"),cmd==L"delete");
        if(cmd==L"list") list_objects(d,args.count(L"--parent")?args[L"--parent"]:WPD_DEVICE_OBJECT_ID,recursive);
        else if(cmd==L"info") print_object(object(d,need(L"--object")));
        else if(cmd==L"get"||cmd==L"thumbnail") download(d,need(L"--object"),need(L"--out"),cmd==L"thumbnail",cancel_after,cancel_ms);
        else if(cmd==L"delete") remove_photo(d,need(L"--object"));
        return 0;
    } catch(const Failure& e) { emit("{\"event\":\"error\",\"where\":"+json(std::string(e.what()))+",\"hresult\":"+json(hexhr(e.hr))+"}"); return 1;
    } catch(const std::exception& e) { emit("{\"event\":\"error\",\"where\":"+json(std::string(e.what()))+"}"); return 1; }
}
