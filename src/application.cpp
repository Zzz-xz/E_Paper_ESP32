#include <Arduino.h>
#include "application.h"
#include "device_client.h"
#include "display_service.h"
#include "network_config.h"

namespace {
epaper::Frame frame;
device_client::Job job;
uint64_t setup_id = 0;
uint32_t last_poll = 0;
uint32_t last_refresh = 0;
bool has_refreshed = false;
uint8_t failed_polls = 0;
void execute_job(uint32_t now);
void fail_job(const char* message);
void configure_network();
}

void application::begin()
{
    display_service::begin();
    network_config::begin();
}

/** @brief 串行编排取图与显示，帧缓冲由此模块独占，不跨模块暴露可变全局状态。 */
void application::tick(uint32_t now)
{
    network_config::tick();
    if (!network_config::connected() || now - last_poll < 2000) return;
    last_poll = now;
    const device_client::Poll result = device_client::poll(job, setup_id);
    if (result == device_client::Poll::Error) {
        if (failed_polls < 3) ++failed_polls;
        if (failed_polls == 3 && network_config::recover_connection()) failed_polls = 0;
        return;
    }
    failed_polls = 0;
    if (result == device_client::Poll::Available) execute_job(now);
    else if (result == device_client::Poll::Setup) configure_network();
}

namespace {
void configure_network()
{
    const String url = network_config::open_remote_portal();
    const String error = url.isEmpty() ? "Cannot open network configuration page." : "";
    if (!device_client::report_setup(setup_id, url, error))
        Serial.println("[network] Setup page acknowledgement was not received.");
}

void execute_job(uint32_t now)
{
    if (has_refreshed && now - last_refresh < epaper::cooldown_ms) {
        fail_job("Device is cooling down; wait 30 seconds between refreshes.");
        return;
    }
    const uint32_t started = millis();
    String error;
    if (!device_client::download(job, frame, error)) { fail_job(error.c_str()); return; }
    Serial.printf("[epaper] Frame ready in %lu ms; requesting refresh.\n", static_cast<unsigned long>(millis() - started));
    if (!device_client::report(job.id, "refreshing")) return;
    has_refreshed = true;
    last_refresh = millis();
    Serial.println("[epaper] Refresh started.");
    const bool complete = display_service::refresh(frame);
    Serial.printf("[epaper] Panel refresh took %lu ms.\n", static_cast<unsigned long>(millis() - last_refresh));
    if (!complete) { fail_job("Display BUSY did not clear."); return; }
    if (device_client::report(job.id, "completed"))
        Serial.println("[epaper] Refresh sequence finished; display sleeping.");
    else Serial.println("[epaper] Refresh finished, but server acknowledgement failed.");
}

void fail_job(const char* message)
{
    Serial.println(String("[epaper] ") + message);
    device_client::report(job.id, "failed", message);
}
}
