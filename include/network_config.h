#pragma once
#include <Arduino.h>

namespace network_config {
void begin();
void tick();
bool connected();
const String& server_url();
String open_remote_portal();
String setup_url();
const String& setup_token();
}
