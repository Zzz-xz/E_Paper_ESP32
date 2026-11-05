#pragma once
#include <algorithm>
#include "frame.h"

namespace frame_receiver {
constexpr uint32_t timeout_ms = 5000;
enum class Status { Complete, Timeout, Disconnected, ReadError };
struct Result { Status status; size_t received; };

/** @brief 仅读取已到达的数据，总期限不随零碎数据重置；每轮让出 CPU，不调用阻塞 readBytes。 */
template<class Stream, class Clock>
Result receive(Stream& stream, epaper::Frame& frame, Clock& clock)
{
    const uint32_t started = clock.now();
    size_t offset = 0;
    while (clock.now() - started < timeout_ms) {
        const int available = stream.available();
        if (available < 0) return {Status::ReadError, offset};
        if (available > 0) {
            const size_t wanted = std::min(static_cast<size_t>(available),
                                          std::min(size_t{1024}, frame.size() - offset));
            const int received = stream.read(frame.data() + offset, wanted);
            if (received < 0) return {Status::ReadError, offset};
            offset += static_cast<size_t>(received);
            if (offset == frame.size()) return {Status::Complete, offset};
        } else if (!stream.connected()) return {Status::Disconnected, offset};
        clock.pause();
    }
    return {Status::Timeout, offset};
}
}
