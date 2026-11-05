#pragma once
#include "frame.h"

namespace display_service {
void begin();
bool refresh(const epaper::Frame& frame);
}
