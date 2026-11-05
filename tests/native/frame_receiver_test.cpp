#include <cassert>
#include <limits>
#include "frame_receiver.h"

struct Clock {
    uint32_t value = 0;
    uint32_t now() const { return value; }
    void pause() { ++value; }
};

struct Source {
    Clock& clock;
    size_t capacity;
    size_t offset = 0;
    size_t calls = 0;
    size_t maximum = 1436;
    bool closed = false;
    bool trickle = false;
    bool broken = false;

    Source(Clock& timer, size_t size) : clock(timer), capacity(size) {}
    int available() const {
        if (trickle && clock.now() % 100) return 0;
        return static_cast<int>(std::min(capacity - offset, trickle ? size_t{1} : size_t{1436}));
    }
    int read(uint8_t* destination, size_t wanted) {
        ++calls;
        if (broken) return -1;
        const size_t count = std::min(wanted, maximum);
        for (size_t index = 0; index < count; ++index) destination[index] = static_cast<uint8_t>((offset + index) % 251);
        offset += count;
        return static_cast<int>(count);
    }
    bool connected() const { return !closed || offset < capacity; }
};

int main()
{
    epaper::Frame frame;
    Clock clock;
    Source complete(clock, frame.size());
    auto result = frame_receiver::receive(complete, frame, clock);
    assert(result.status == frame_receiver::Status::Complete && result.received == frame.size());
    assert(complete.calls == 30);
    for (size_t index = 0; index < frame.size(); ++index) assert(frame[index] == index % 251);

    clock.value = 0;
    Source fragments(clock, frame.size());
    fragments.maximum = 29;
    result = frame_receiver::receive(fragments, frame, clock);
    assert(result.status == frame_receiver::Status::Complete && result.received == frame.size());

    clock.value = 0;
    Source truncated(clock, 1000);
    truncated.closed = true;
    result = frame_receiver::receive(truncated, frame, clock);
    assert(result.status == frame_receiver::Status::Disconnected && result.received == 1000);

    clock.value = 0;
    Source stalled(clock, 0);
    result = frame_receiver::receive(stalled, frame, clock);
    assert(result.status == frame_receiver::Status::Timeout && clock.now() == 5000);

    clock.value = 0;
    Source trickle(clock, frame.size());
    trickle.trickle = true;
    result = frame_receiver::receive(trickle, frame, clock);
    assert(result.status == frame_receiver::Status::Timeout && result.received == 50 && clock.now() == 5000);

    clock.value = std::numeric_limits<uint32_t>::max() - 100;
    const uint32_t started = clock.now();
    Source rollover(clock, 0);
    result = frame_receiver::receive(rollover, frame, clock);
    assert(result.status == frame_receiver::Status::Timeout && clock.now() - started == 5000);

    Source broken(clock, 1000);
    broken.broken = true;
    result = frame_receiver::receive(broken, frame, clock);
    assert(result.status == frame_receiver::Status::ReadError && result.received == 0);
}
