// JURAS Fire Detection Node - ESP32 DevKit C V4 (Wokwi)
//
// Hardware:
//   DHT22 DATA   -> GPIO 15
//   MQ-2 AOUT    -> GPIO 34
//   Flame button -> GPIO 25 (button to GND, active LOW)
//   Red LED      -> GPIO 26
//   Yellow LED   -> GPIO 27
//   Green LED    -> GPIO 14
//   Buzzer       -> GPIO 13
//
// Libraries: DHT sensor library (Adafruit) + Adafruit Unified Sensor.
//
// Backend contract: POST /api/v1/readings (the existing JURAS ingestion
// endpoint). The sketch sends the exact ReadingCreate fields plus extra
// hardware values that the backend stores but does not need for risk.
//
// For local development with the Wokwi Private IoT Gateway:
//   SERVER_URL = "http://host.wokwi.internal:8000/api/v1/readings"
// For a public HTTPS backend, use its canonical URL. Never use a URL that
// redirects (301/302/307/308), because POST redirects are rejected here.

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <DHT.h>
#include <math.h>
#include <time.h>

// ==========================================
// 1. WIFI / SERVER CONFIGURATION
// ==========================================

#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""
#define WIFI_CHANNEL 6

const char* SERVER_URL = "http://host.wokwi.internal:8000/api/v1/readings";

// Optional shared secret. Leave empty when the backend does not set
// DEVICE_API_KEY. When set on both sides it is sent as X-Device-Key.
const char* DEVICE_API_KEY = "";

// ==========================================
// 2. DEVICE / TARGET CONFIGURATION
// ==========================================

// Must match an existing JURAS sensor code and its building code.
// Seed defaults: JM-014 belongs to B-014.
#define DEVICE_ID "JURAS-FIRE-001"
#define SENSOR_CODE "JM-014"
#define BUILDING_CODE "B-014"

// ==========================================
// 3. PIN CONFIGURATION
// ==========================================

#define DHT_PIN 15
#define MQ2_PIN 34
#define FLAME_BTN_PIN 25
#define LED_RED_PIN 26
#define LED_YELLOW_PIN 27
#define LED_GREEN_PIN 14
#define BUZZER_PIN 13

#define DHT_TYPE DHT22

// ==========================================
// 4. FIRE THRESHOLDS (DEMO VALUES, NOT CERTIFIED)
// ==========================================

const float TEMP_WARNING_C = 45.0;
const float TEMP_CRITICAL_C = 70.0;

const float SMOKE_WARNING_LEVEL = 60.0;
const float SMOKE_CRITICAL_LEVEL = 80.0;

const float SMOKE_TEMP_COMBO_C = 60.0;
const float SMOKE_TEMP_COMBO_LEVEL = 60.0;

// ==========================================
// 5. TIMING
// ==========================================

const unsigned long SENSOR_INTERVAL_MS = 2000;
const unsigned long UPLOAD_INTERVAL_MS = 5000;
const unsigned long FLUSH_INTERVAL_MS = 1000;
const unsigned long WIFI_RETRY_MS = 10000;
const unsigned long ALERT_BLINK_MS = 500;
const unsigned long BUZZER_BEEP_MS = 120;
const unsigned long BUZZER_PERIOD_MS = 2000;
const unsigned long NTP_RETRY_MS = 30000;
const int MQ2_BASELINE_SAMPLES = 30;
const size_t SAMPLE_BUFFER_SIZE = 12;

// ==========================================
// 6. STATE
// ==========================================

enum FireState {
  STATE_NORMAL,
  STATE_WARNING,
  STATE_CRITICAL
};

struct Sample {
  uint32_t seq;
  time_t epoch;
  float temperature_c;
  float humidity_pct;
  int smoke_raw;
  float smoke_level;
  bool flame;
  bool dht_ok;
  int rssi;
};

DHT dht(DHT_PIN, DHT_TYPE);

FireState fireState = STATE_NORMAL;

float temperatureC = NAN;
float humidityPct = NAN;
float lastGoodTemperature = NAN;
float lastGoodHumidity = NAN;

int smokeRaw = 0;
float smokeLevel = 0.0;
float gasBaseline = 800.0;

bool dhtOk = false;
bool flameDetected = false;
bool wifiWasConnected = false;
bool ntpRequested = false;

int lastFlameReading = HIGH;
unsigned long lastFlameChange = 0;

uint32_t sequence = 0;

Sample pending;
Sample queue[SAMPLE_BUFFER_SIZE];
size_t queueCount = 0;

unsigned long lastSensorRead = 0;
unsigned long lastUpload = 0;
unsigned long lastWifiAttempt = 0;
unsigned long lastNtpRequest = 0;

// ==========================================
// 7. WIFI + TIME
// ==========================================

void requestNtpSync() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  ntpRequested = true;
  Serial.println("NTP sync requested");
}

bool clockValid() {
  return time(nullptr) > 1700000000;
}

void maintainWifi(unsigned long now) {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.print("WiFi connected. IP: ");
      Serial.println(WiFi.localIP());
      requestNtpSync();
    }
    if (!clockValid() && now - lastNtpRequest >= NTP_RETRY_MS) {
      lastNtpRequest = now;
      requestNtpSync();
    }
    return;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    Serial.println("WiFi disconnected. Buffering telemetry.");
  }

  if (now - lastWifiAttempt >= WIFI_RETRY_MS) {
    lastWifiAttempt = now;
    Serial.println("Reconnecting WiFi...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  }
}

// ==========================================
// 8. SENSOR READING
// ==========================================

void pollFlameButton(unsigned long now) {
  int reading = digitalRead(FLAME_BTN_PIN);
  if (reading != lastFlameReading) {
    lastFlameReading = reading;
    lastFlameChange = now;
  }
  if (now - lastFlameChange >= 50) {
    flameDetected = (reading == LOW);
  }
}

float calibrateGasBaseline() {
  float sum = 0.0;
  for (int i = 0; i < MQ2_BASELINE_SAMPLES; i++) {
    sum += analogRead(MQ2_PIN);
    delay(100);
  }
  return sum / MQ2_BASELINE_SAMPLES;
}

void readSensors() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  dhtOk = isfinite(t) && isfinite(h) &&
          t > -40.0 && t < 125.0 &&
          h >= 0.0 && h <= 100.0;

  if (dhtOk) {
    lastGoodTemperature = t;
    lastGoodHumidity = h;
  } else {
    Serial.println("DHT22 read failed. Keeping last good values.");
  }

  temperatureC = dhtOk ? t : lastGoodTemperature;
  humidityPct = dhtOk ? h : lastGoodHumidity;

  smokeRaw = analogRead(MQ2_PIN);
  if (smokeRaw < 0) {
    smokeRaw = 0;
  } else if (smokeRaw > 4095) {
    smokeRaw = 4095;
  }

  if (gasBaseline < 50.0) {
    gasBaseline = 50.0;
  }

  float span = 4095.0 - gasBaseline;
  if (span > 1.0 && smokeRaw > gasBaseline) {
    smokeLevel = ((smokeRaw - gasBaseline) / span) * 100.0;
  } else {
    smokeLevel = 0.0;
  }
  smokeLevel = constrain(smokeLevel, 0.0, 100.0);

  // Track clean-air drift slowly, but never while smoke or flame is present.
  if (!flameDetected && smokeLevel < 10.0) {
    gasBaseline = gasBaseline * 0.99 + smokeRaw * 0.01;
  }
}

// ==========================================
// 9. FIRE CLASSIFICATION
// ==========================================

void calculateFireState() {
  bool criticalByValue =
      temperatureC >= TEMP_CRITICAL_C ||
      smokeLevel >= SMOKE_CRITICAL_LEVEL;

  bool criticalByCombo =
      temperatureC >= SMOKE_TEMP_COMBO_C &&
      smokeLevel >= SMOKE_TEMP_COMBO_LEVEL;

  bool warning =
      !dhtOk ||
      temperatureC >= TEMP_WARNING_C ||
      smokeLevel >= SMOKE_WARNING_LEVEL;

  if (flameDetected || criticalByValue || criticalByCombo) {
    fireState = STATE_CRITICAL;
  } else if (warning) {
    fireState = STATE_WARNING;
  } else {
    fireState = STATE_NORMAL;
  }
}

const char* stateName() {
  switch (fireState) {
    case STATE_CRITICAL:
      return "critical";
    case STATE_WARNING:
      return "warning";
    default:
      return "normal";
  }
}

// ==========================================
// 10. LED + BUZZER OUTPUT
// ==========================================

void updateAlerts(unsigned long now) {
  bool blink = ((now / ALERT_BLINK_MS) % 2) == 0;

  digitalWrite(LED_GREEN_PIN, fireState == STATE_NORMAL ? HIGH : LOW);
  digitalWrite(LED_YELLOW_PIN,
               fireState == STATE_WARNING ? (blink ? HIGH : LOW) : LOW);
  digitalWrite(LED_RED_PIN, fireState == STATE_CRITICAL ? HIGH : LOW);

  if (fireState == STATE_CRITICAL) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (fireState == STATE_WARNING) {
    bool beep = (now % BUZZER_PERIOD_MS) < BUZZER_BEEP_MS;
    digitalWrite(BUZZER_PIN, beep ? HIGH : LOW);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }
}

// ==========================================
// 11. SERIAL MONITOR
// ==========================================

void printReadings() {
  Serial.println("\n========== JURAS FIRE MONITOR ==========");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);
  Serial.print("Sensor: ");
  Serial.println(SENSOR_CODE);
  Serial.print("Building: ");
  Serial.println(BUILDING_CODE);
  Serial.print("DHT ok: ");
  Serial.println(dhtOk ? "yes" : "no");
  Serial.print("Temperature: ");
  Serial.println(isfinite(temperatureC) ? String(temperatureC, 2) : String("n/a"));
  Serial.print("Humidity: ");
  Serial.println(isfinite(humidityPct) ? String(humidityPct, 2) : String("n/a"));
  Serial.print("MQ-2 raw: ");
  Serial.println(smokeRaw);
  Serial.print("MQ-2 baseline: ");
  Serial.println(gasBaseline, 1);
  Serial.print("Smoke level: ");
  Serial.println(smokeLevel, 1);
  Serial.print("Flame button: ");
  Serial.println(flameDetected ? "TRIGGERED" : "clear");
  Serial.print("State: ");
  Serial.println(stateName());
  Serial.println("========================================");
}

// ==========================================
// 12. PAYLOAD + HTTP
// ==========================================

String isoUtc(time_t epoch) {
  struct tm tmUtc;
  gmtime_r(&epoch, &tmUtc);
  char buf[24];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tmUtc);
  return String(buf);
}

Sample captureSample() {
  Sample s;
  s.seq = ++sequence;
  s.epoch = clockValid() ? time(nullptr) : 0;
  s.temperature_c = temperatureC;
  s.humidity_pct = humidityPct;
  s.smoke_raw = smokeRaw;
  s.smoke_level = smokeLevel;
  s.flame = flameDetected;
  s.dht_ok = dhtOk;
  s.rssi = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  return s;
}

String buildPayload(const Sample &s) {
  String p = "{";
  p += "\"sensor_id\":\"" SENSOR_CODE "\",";
  p += "\"building_id\":\"" BUILDING_CODE "\",";
  p += "\"hazard\":\"fire\",";
  p += "\"source\":\"field\",";
  p += "\"simulation\":false,";

  if (s.epoch >= 1700000000) {
    p += "\"observed_at\":\"" + isoUtc(s.epoch) + "\",";
  }

  p += "\"values\":{";
  bool first = true;

  if (isfinite(s.temperature_c)) {
    p += "\"temperature_c\":" + String(s.temperature_c, 2);
    first = false;
  }
  if (isfinite(s.humidity_pct)) {
    if (!first) {
      p += ",";
    }
    p += "\"humidity_pct\":" + String(s.humidity_pct, 2);
    first = false;
  }

  if (!first) {
    p += ",";
  }

  p += "\"smoke_raw\":" + String(s.smoke_raw) + ",";
  p += "\"smoke_level\":" + String(s.smoke_level, 2) + ",";
  p += "\"flame\":" + String(s.flame ? 1 : 0) + ",";
  p += "\"dht_ok\":" + String(s.dht_ok ? 1 : 0) + ",";
  p += "\"rssi\":" + String(s.rssi) + ",";
  p += "\"seq\":" + String((unsigned long)s.seq);
  p += "}}";
  return p;
}

enum PostResult {
  POST_OK,
  POST_RETRY,
  POST_DROP
};

PostResult executePost(HTTPClient &http, const String &payload, const Sample &s) {
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Accept", "application/json");
  http.addHeader("Idempotency-Key",
                 String(DEVICE_ID) + "-" + String((unsigned long)s.seq));

  if (strlen(DEVICE_API_KEY) > 0) {
    http.addHeader("X-Device-Key", DEVICE_API_KEY);
  }

  int code = http.POST(payload);

  if (code >= 200 && code < 300) {
    Serial.print("Telemetry accepted: HTTP ");
    Serial.println(code);
    return POST_OK;
  }

  if (code < 0) {
    Serial.print("HTTP transport error: ");
    Serial.println(http.errorToString(code));
    return POST_RETRY;
  }

  if (code == 408 || code == 429 || code >= 500) {
    Serial.print("Retryable HTTP error: ");
    Serial.println(code);
    return POST_RETRY;
  }

  Serial.print("Non-retryable HTTP error: ");
  Serial.print(code);
  Serial.print(" ");
  Serial.println(http.getString());
  return POST_DROP;
}

PostResult postSample(const Sample &s) {
  if (WiFi.status() != WL_CONNECTED) {
    return POST_RETRY;
  }

  String url = String(SERVER_URL);
  String payload = buildPayload(s);

  Serial.println("POST " + url);
  Serial.println(payload);

  HTTPClient http;
  http.setConnectTimeout(5000);
  http.setTimeout(5000);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);

  if (url.startsWith("https://")) {
    WiFiClientSecure client;
    // Prototype only. Production must validate the server certificate.
    client.setInsecure();
    if (!http.begin(client, url)) {
      Serial.println("HTTPS begin failed");
      return POST_RETRY;
    }
    PostResult result = executePost(http, payload, s);
    http.end();
    return result;
  }

  WiFiClient client;
  if (!http.begin(client, url)) {
    Serial.println("HTTP begin failed");
    return POST_RETRY;
  }
  PostResult result = executePost(http, payload, s);
  http.end();
  return result;
}

// ==========================================
// 13. OFFLINE BUFFER + UPLOAD LOOP
// ==========================================

void enqueueSample(const Sample &s) {
  if (queueCount > 0 && queue[queueCount - 1].seq == s.seq) {
    return;
  }

  if (queueCount >= SAMPLE_BUFFER_SIZE) {
    for (size_t i = 1; i < SAMPLE_BUFFER_SIZE; i++) {
      queue[i - 1] = queue[i];
    }
    queueCount = SAMPLE_BUFFER_SIZE - 1;
  }

  queue[queueCount++] = s;
}

void popSample() {
  if (queueCount == 0) {
    return;
  }
  for (size_t i = 1; i < queueCount; i++) {
    queue[i - 1] = queue[i];
  }
  queueCount--;
}

void uploadLoop(unsigned long now) {
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastUpload >= UPLOAD_INTERVAL_MS) {
      lastUpload = now;
      enqueueSample(pending);
      Serial.println("Offline: sample buffered");
    }
    return;
  }

  bool flushing = queueCount > 0;
  unsigned long interval = flushing ? FLUSH_INTERVAL_MS : UPLOAD_INTERVAL_MS;
  if (now - lastUpload < interval) {
    return;
  }
  lastUpload = now;

  Sample sample = flushing ? queue[0] : pending;
  PostResult result = postSample(sample);

  if (result == POST_OK || result == POST_DROP) {
    if (flushing) {
      popSample();
    }
    if (result == POST_DROP) {
      Serial.println("Sample dropped after non-retryable response.");
    }
  } else if (!flushing) {
    enqueueSample(pending);
    Serial.println("Upload failed: sample buffered for retry.");
  }
}

// ==========================================
// 14. SETUP
// ==========================================

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_YELLOW_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(FLAME_BTN_PIN, INPUT_PULLUP);
  pinMode(MQ2_PIN, INPUT);

  digitalWrite(LED_RED_PIN, LOW);
  digitalWrite(LED_YELLOW_PIN, LOW);
  digitalWrite(LED_GREEN_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  analogReadResolution(12);

  Serial.println("\nStarting JURAS Fire Detection Node");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);

  dht.begin();

  Serial.print("Calibrating MQ-2 baseline");
  gasBaseline = calibrateGasBaseline();
  Serial.print(" -> ");
  Serial.println(gasBaseline, 1);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);

  Serial.print("Connecting to WiFi");
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 10000) {
    delay(100);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wifiWasConnected = true;
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    requestNtpSync();
  } else {
    Serial.println("WiFi not connected yet. Will retry in the main loop.");
    lastWifiAttempt = millis();
  }

  readSensors();
  calculateFireState();
  pending = captureSample();
  printReadings();

  Serial.println("JURAS FIRE DEVICE READY");
}

// ==========================================
// 15. MAIN LOOP
// ==========================================

void loop() {
  unsigned long now = millis();

  pollFlameButton(now);
  maintainWifi(now);
  updateAlerts(now);

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    readSensors();
    calculateFireState();
    pending = captureSample();
    printReadings();
  }

  uploadLoop(now);
  delay(10);
}
