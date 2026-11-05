#include <ArduinoJson.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>
#include "network_config.h"
#include "provisioning_page.h"

namespace {
struct Settings { String ssid; String password; String server; };
enum class Phase { Portal, Connecting, Ready };
Settings saved, candidate;
WebServer portal(80);
Phase phase = Phase::Portal;
String hotspot_password;
String error_message;
String serial_command;
String remote_token;
bool portal_active = false;
bool submission = false;
bool remote_portal = false;
bool connection_queued = false;
uint32_t connect_due = 0;
bool scan_active = false;
uint32_t scan_started = 0;
uint32_t connect_started = 0;
uint32_t portal_close_at = 0;
uint8_t attempts = 0;

bool read_settings();
bool save_settings();
bool authorize_portal();
void start_portal(bool announce = true);
void start_connection(uint32_t now);
void configure();
void reply_status();
void reply_scan();
String validate_form();
void service_serial();
void connection_succeeded(uint32_t now);
void connection_failed(uint32_t now);
}

void network_config::begin()
{
    read_settings();
    const char* headers[] = {"Authorization"};
    portal.collectHeaders(headers, 1);
    portal.on("/", HTTP_GET, [] { portal.send_P(200, "text/html; charset=utf-8", provisioning_page); });
    portal.on("/configure", HTTP_POST, configure);
    portal.on("/status", HTTP_GET, reply_status);
    portal.on("/scan", HTTP_GET, reply_scan);
    portal.on("/cancel", HTTP_POST, [] {
        if (!authorize_portal()) return;
        if (!remote_portal || scan_active) {
            portal.send(409, "application/json; charset=utf-8", "{\"error\":\"请等待扫描结束后退出远程配网。\"}");
            return;
        }
        portal.send(202, "application/json", "{\"accepted\":true}");
        portal_close_at = millis() + 300;
    });
    portal.on("/settings", HTTP_GET, [] {
        if (!authorize_portal()) return;
        JsonDocument document;
        document["ssid"] = saved.ssid;
        document["server"] = saved.server;
        String body;
        serializeJson(document, body);
        portal.send(200, "application/json; charset=utf-8", body);
    });
    if (saved.ssid.isEmpty()) start_portal();
    else start_connection(millis());
}

void network_config::tick()
{
    service_serial();
    if (portal_active) portal.handleClient();
    /** 处理表单可能刚刚启动连接，计时必须晚于连接开始时间，避免无符号减法下溢。 */
    const uint32_t now = millis();
    if (scan_active && now - scan_started >= 15000) {
        WiFi.scanDelete();
        scan_active = false;
    }
    if (connection_queued && static_cast<int32_t>(now - connect_due) >= 0) {
        connection_queued = false;
        start_connection(now);
    }
    if (phase == Phase::Connecting) {
        if (WiFi.status() == WL_CONNECTED) connection_succeeded(now);
        else if (now - connect_started >= 20000) connection_failed(now);
    } else if (phase == Phase::Ready && WiFi.status() != WL_CONNECTED) {
        attempts = 0;
        start_connection(now);
    }
    if (phase == Phase::Ready && portal_active && static_cast<int32_t>(now - portal_close_at) >= 0) {
        portal.stop();
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_STA);
        portal_active = false;
        remote_portal = false;
        remote_token = "";
    }
}

bool network_config::connected() { return phase == Phase::Ready && WiFi.status() == WL_CONNECTED; }
const String& network_config::server_url() { return saved.server; }

/** @brief 网页请求保留现有 STA 连接，保护热点同时提供切换网络失败后的恢复入口。 */
String network_config::open_remote_portal()
{
    error_message = "";
    start_portal(false);
    if (!portal_active || WiFi.status() != WL_CONNECTED) return "";
    phase = Phase::Ready;
    remote_portal = true;
    if (remote_token.isEmpty()) {
        char token[33];
        snprintf(token, sizeof(token), "%08lx%08lx%08lx%08lx", static_cast<unsigned long>(esp_random()),
                 static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
        remote_token = token;
    }
    portal_close_at = millis() + 600000;
    Serial.println("[network] Configuration page opened from workbench.");
    return setup_url();
}

String network_config::setup_url()
{
    return remote_portal && portal_active && phase == Phase::Ready && WiFi.status() == WL_CONNECTED
        ? "http://" + WiFi.localIP().toString() : "";
}
const String& network_config::setup_token() { return remote_token; }

namespace {
bool authorize_portal()
{
    if (remote_portal && portal.header("Authorization") != "Bearer " + remote_token) {
        portal.send(401, "application/json; charset=utf-8", "{\"error\":\"请从工作台使用管理员授权链接打开配网页。\"}");
        return false;
    }
    return true;
}

bool read_settings()
{
    Preferences storage;
    if (!storage.begin("epaper-net", false)) {
        Serial.println("[network] Cannot open configuration storage.");
        return false;
    }
    if (storage.isKey("ssid")) {
        saved.ssid = storage.getString("ssid");
        saved.password = storage.isKey("password") ? storage.getString("password") : "";
        saved.server = storage.getString("server");
    }
    if (storage.isKey("ap-key")) hotspot_password = storage.getString("ap-key");
    if (hotspot_password.isEmpty()) {
        char key[17];
        snprintf(key, sizeof(key), "%08lx%08lx", static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
        hotspot_password = key;
        if (!storage.putString("ap-key", hotspot_password)) Serial.println("[network] Cannot persist setup hotspot key.");
    }
    storage.end();
    return true;
}

bool save_settings()
{
    Preferences storage;
    if (!storage.begin("epaper-net", false)) return false;
    const bool ssid_ok = storage.putString("ssid", candidate.ssid) > 0;
    const bool password_ok = candidate.password.isEmpty()
        ? (!storage.isKey("password") || storage.remove("password"))
        : storage.putString("password", candidate.password) > 0;
    const bool server_ok = storage.putString("server", candidate.server) > 0;
    storage.end();
    return ssid_ok && password_ok && server_ok;
}

void start_portal(bool announce)
{
    if (hotspot_password.isEmpty()) {
        char key[17];
        snprintf(key, sizeof(key), "%08lx%08lx", static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
        hotspot_password = key;
    }
    WiFi.mode(WIFI_AP_STA);
    const String name = "EPaper-" + String(static_cast<uint32_t>(ESP.getEfuseMac() >> 24), HEX);
    if (!WiFi.softAP(name.c_str(), hotspot_password.c_str())) {
        Serial.println("[network] Setup hotspot failed.");
        return;
    }
    if (!portal_active) portal.begin();
    portal_active = true;
    phase = Phase::Portal;
    submission = false;
    if (!announce) return;
    Serial.println("[setup] Hotspot: " + name);
    Serial.println("[setup-secret] Hotspot password: " + hotspot_password);
    Serial.println("[setup] Open http://" + WiFi.softAPIP().toString());
    Serial.println("[setup] Home Wi-Fi credentials are entered only on the device page.");
}

void start_connection(uint32_t now)
{
    if (!portal_active) WiFi.mode(WIFI_STA);
    const Settings& settings = submission ? candidate : saved;
    WiFi.disconnect(false, false);
    WiFi.begin(settings.ssid.c_str(), settings.password.c_str());
    phase = Phase::Connecting;
    connect_started = now;
    ++attempts;
    Serial.println("[network] Connecting to configured Wi-Fi.");
}

String validate_form()
{
    const String ssid = portal.arg("ssid");
    const String password = portal.arg("password");
    String server = portal.arg("server");
    server.trim();
    if (server.endsWith("/")) server.remove(server.length() - 1);
    if (ssid.isEmpty() || ssid.length() > 32) return "Wi-Fi 名称须为 1 至 32 字节。";
    if (!password.isEmpty() && (password.length() < 8 || password.length() > 63)) return "Wi-Fi 密码须为空或 8 至 63 字节。";
    if (!server.startsWith("http://") || server.length() <= 7 || server.length() > 159 ||
        server.indexOf('/', 7) >= 0 || server.indexOf('@') >= 0 || server.indexOf('?') >= 0 ||
        server.indexOf('#') >= 0 || server.indexOf(' ') >= 0) return "请输入 http://电脑局域网地址:端口，不包含路径。";
    candidate = {ssid, password, server};
    return "";
}

void configure()
{
    if (!authorize_portal()) return;
    if (scan_active) {
        portal.send(409, "application/json; charset=utf-8", "{\"error\":\"请等待 Wi-Fi 扫描结束后提交。\"}");
        return;
    }
    error_message = validate_form();
    if (!error_message.isEmpty()) { reply_status(); return; }
    submission = true;
    attempts = 0;
    portal.send(202, "application/json", "{\"accepted\":true}");
    /** 先发出 HTTP 响应再切换 STA 网络，给客户端留出接收确认的时间。 */
    connect_due = millis() + 300;
    connection_queued = true;
}

/** @brief 异步扫描不阻塞配网页，序列化完成后立即释放 SDK 扫描结果。 */
void reply_scan()
{
    if (!authorize_portal()) return;
    if (portal.arg("start") == "1" && !scan_active) {
        if (phase == Phase::Connecting || connection_queued) {
            portal.send(409, "application/json; charset=utf-8", "{\"error\":\"正在连接网络，请稍后扫描。\"}");
            return;
        }
        scan_started = millis();
        scan_active = WiFi.scanNetworks(true, false) != WIFI_SCAN_FAILED;
    }
    const int16_t count = WiFi.scanComplete();
    if (count == WIFI_SCAN_RUNNING) {
        portal.send(202, "application/json", "{\"scanning\":true}");
        return;
    }
    JsonDocument document;
    int status = 200;
    if (count < 0) {
        document["error"] = "扫描失败，请点击重新扫描。";
        status = 503;
    } else {
        JsonArray networks = document["networks"].to<JsonArray>();
        for (int16_t index = 0; index < count && index < 64; ++index) {
            const String ssid = WiFi.SSID(index);
            if (ssid.isEmpty()) continue;
            JsonObject network = networks.add<JsonObject>();
            network["ssid"] = ssid;
            network["rssi"] = WiFi.RSSI(index);
            network["secure"] = WiFi.encryptionType(index) != WIFI_AUTH_OPEN;
        }
    }
    String body;
    serializeJson(document, body);
    WiFi.scanDelete();
    scan_active = false;
    portal.send(status, "application/json; charset=utf-8", body);
}

void reply_status()
{
    if (!authorize_portal()) return;
    JsonDocument document;
    document["connected"] = phase == Phase::Ready;
    document["error"] = error_message;
    String body;
    serializeJson(document, body);
    portal.send(error_message.isEmpty() ? 200 : 422, "application/json; charset=utf-8", body);
}

void connection_succeeded(uint32_t now)
{
    if (submission) {
        if (!save_settings()) {
            error_message = "配置保存失败，请检查设备存储后重试。";
            phase = Phase::Portal;
            submission = false;
            return;
        }
        saved = candidate;
        candidate.password = "";
    }
    submission = false;
    attempts = 0;
    error_message = "";
    phase = Phase::Ready;
    /** 联网工作台由 USB 供电，关闭调制解调器省电，避免收图等待唤醒。 */
    if (!WiFi.setSleep(false)) Serial.println("[network] Cannot disable Wi-Fi sleep.");
    portal_close_at = now + 5000;
    Serial.println("[network] Wi-Fi connected; display service ready.");
}

void connection_failed(uint32_t now)
{
    if (!submission && attempts < 3) { start_connection(now); return; }
    error_message = "连接超时，请确认 2.4 GHz Wi-Fi 名称和密码。";
    if (!portal_active) start_portal();
    phase = Phase::Portal;
    submission = false;
    candidate.password = "";
    Serial.println("[network] Wi-Fi connection timed out; use setup portal.");
}

void service_serial()
{
    while (Serial.available()) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            if (serial_command == "setup") { error_message = ""; start_portal(); }
            serial_command = "";
        } else if (serial_command.length() < 16) serial_command += c;
    }
}
}
