#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <inttypes.h>
#include "device_client.h"
#include "frame_receiver.h"
#include "network_config.h"

namespace {
constexpr uint8_t kAttempts = 3;
constexpr int32_t kConnectTimeoutMs = 2000;
constexpr uint16_t kRequestTimeoutMs = 3000;
struct ReceiverClock {
    uint32_t now() const { return millis(); }
    void pause() const { delay(1); }
};
bool post_once(const String& path, const String& payload, String& response, int& status);
device_client::Poll poll_once(device_client::Job& job, uint64_t& setup_id);
bool download_once(const device_client::Job& job, epaper::Frame& frame, String& error);
bool valid_frame(const epaper::Frame& frame, uint32_t expected, String& error);
String job_path(uint64_t id);
}

device_client::Poll device_client::poll(Job& job, uint64_t& setup_id)
{
    for (uint8_t attempt = 0; attempt < kAttempts; ++attempt) {
        const Poll result = poll_once(job, setup_id);
        if (result != Poll::Error) return result;
        delay(300);
    }
    Serial.println("[http] Poll failed after 3 attempts.");
    return Poll::Error;
}

bool device_client::download(const Job& job, epaper::Frame& frame, String& error)
{
    for (uint8_t attempt = 0; attempt < kAttempts; ++attempt) {
        const uint32_t started = millis();
        const bool complete = download_once(job, frame, error);
        Serial.printf("[http] Frame attempt %u: %s, %lu ms, RSSI %d dBm\n",
                      static_cast<unsigned>(attempt + 1), complete ? "complete" : error.c_str(),
                      static_cast<unsigned long>(millis() - started), WiFi.RSSI());
        if (complete) return true;
        if (attempt + 1 < kAttempts) delay(300);
    }
    Serial.println("[http] Frame download or validation failed.");
    return false;
}

bool device_client::report(uint64_t id, const char* state, const char* error)
{
    JsonDocument document;
    document["status"] = state;
    document["error"] = error;
    String payload, response;
    serializeJson(document, payload);
    int status = 0;
    for (uint8_t attempt = 0; attempt < kAttempts; ++attempt) {
        if (post_once(job_path(id) + "/result", payload, response, status) && status == 200) return true;
        delay(300);
    }
    Serial.println("[http] Result reporting failed.");
    return false;
}

/** @brief 配网页地址为运行时获取，不上传家庭 Wi-Fi 名称或密码。 */
bool device_client::report_setup(uint64_t id, const String& url, const String& error)
{
    JsonDocument document;
    document["url"] = url;
    document["error"] = error;
    document["token"] = network_config::setup_token();
    String payload, response;
    serializeJson(document, payload);
    char path[80];
    snprintf(path, sizeof(path), "/api/device/setup/%" PRIu64 "/result", id);
    int status = 0;
    for (uint8_t attempt = 0; attempt < kAttempts; ++attempt) {
        if (post_once(path, payload, response, status) && status == 200) return true;
        delay(300);
    }
    Serial.println("[http] Setup result reporting failed.");
    return false;
}

namespace {
String job_path(uint64_t id)
{
    char path[64];
    snprintf(path, sizeof(path), "/api/device/jobs/%" PRIu64, id);
    return path;
}

bool post_once(const String& path, const String& payload, String& response, int& status)
{
    const uint32_t started = millis();
    WiFiClient client;
    HTTPClient http;
    if (!http.begin(client, network_config::server_url() + path)) return false;
    http.setConnectTimeout(kConnectTimeoutMs);
    http.setTimeout(kRequestTimeoutMs);
    http.setReuse(false);
    http.addHeader("Content-Type", "application/json");
    status = http.POST(payload);
    const int length = http.getSize();
    const bool readable = status == 204 || (status > 0 && length >= 0 && length <= 1024);
    if (readable && status != 204) response = http.getString();
    http.end();
    if (!readable || status >= 400)
        Serial.printf("[http] Request failed: status %d, %lu ms, Wi-Fi %d, RSSI %d dBm, heap %u\n",
                      status, static_cast<unsigned long>(millis() - started),
                      static_cast<int>(WiFi.status()), WiFi.RSSI(), ESP.getFreeHeap());
    return readable;
}

device_client::Poll poll_once(device_client::Job& job, uint64_t& setup_id)
{
    String response, payload;
    JsonDocument heartbeat;
    heartbeat["setup_supported"] = true;
    heartbeat["setup_url"] = network_config::setup_url();
    serializeJson(heartbeat, payload);
    int status = 0;
    if (!post_once("/api/device/poll", payload, response, status)) return device_client::Poll::Error;
    if (status == 204) return device_client::Poll::Empty;
    if (status != 200) return device_client::Poll::Error;
    JsonDocument document;
    if (deserializeJson(document, response)) return device_client::Poll::Error;
    if (document["command"].is<const char*>()) {
        if (document["command"].as<String>() != "setup" || !document["command_id"].is<uint64_t>() || document["command_id"].as<uint64_t>() == 0)
            return device_client::Poll::Error;
        setup_id = document["command_id"].as<uint64_t>();
        return device_client::Poll::Setup;
    }
    if (!document["job_id"].is<uint64_t>() ||
        !document["crc32"].is<uint32_t>() || !document["size"].is<uint32_t>() || document["size"].as<size_t>() != epaper::frame_bytes ||
        document["job_id"].as<uint64_t>() == 0) return device_client::Poll::Error;
    job = {document["job_id"].as<uint64_t>(), document["crc32"].as<uint32_t>()};
    return device_client::Poll::Available;
}

bool download_once(const device_client::Job& job, epaper::Frame& frame, String& error)
{
    WiFiClient client;
    HTTPClient http;
    if (!http.begin(client, network_config::server_url() + job_path(job.id) + "/frame")) {
        error = "无法创建图片下载连接。";
        return false;
    }
    http.setConnectTimeout(kConnectTimeoutMs);
    http.setTimeout(kRequestTimeoutMs);
    http.setReuse(false);
    const int status = http.GET();
    const int length = http.getSize();
    if (status != 200 || length != static_cast<int>(frame.size())) {
        error = status != 200 ? "图片下载连接失败，HTTP " + String(status)
                              : "图片长度错误：" + String(length) + "/30000 字节。";
        http.end();
        return false;
    }
    ReceiverClock clock;
    const frame_receiver::Result result = frame_receiver::receive(http.getStream(), frame, clock);
    http.end();
    if (result.status != frame_receiver::Status::Complete) {
        error = String(result.status == frame_receiver::Status::Timeout ? "图片下载超时：" : "图片下载中断：") +
                String(result.received) + "/30000 字节。";
        return false;
    }
    return valid_frame(frame, job.crc32, error);
}

/** @brief 网络模块边界一次性校验长度、位面互斥和校验码，显示层直接消费合法帧。 */
bool valid_frame(const epaper::Frame& frame, uint32_t expected, String& error)
{
    uint32_t crc = 0xffffffffU;
    for (size_t index = 0; index < frame.size(); ++index) {
        crc ^= frame[index];
        for (uint8_t bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    if (~crc != expected) { error = "图片 CRC32 校验失败，请重新发送。"; return false; }
    for (size_t index = 0; index < epaper::plane_bytes; ++index)
        if (frame[index] & frame[index + epaper::plane_bytes]) {
            error = "图片黑色与红色位面重叠，请重新生成预览。";
            return false;
        }
    return true;
}
}
