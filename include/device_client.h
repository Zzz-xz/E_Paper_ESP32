#pragma once
#include "frame.h"

namespace device_client {
struct Job { uint64_t id; uint32_t crc32; };
enum class Poll { Empty, Available, Setup, Error };
Poll poll(Job& job, uint64_t& setup_id);
bool report_setup(uint64_t id, const String& url, const String& error);
bool download(const Job& job, epaper::Frame& frame);
bool report(uint64_t id, const char* state, const char* error = "");
}
