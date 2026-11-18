// JURAS Stormwater Node - ESP32 DevKit C V4 (Wokwi)
//
// Hardware:
//   HC-SR04 TRIG    -> GPIO 5
//   HC-SR04 ECHO    -> GPIO 18
//   Rain sensor AO  -> GPIO 34 (analog)
//   DHT22 DATA      -> GPIO 15
//   Red LED         -> GPIO 26
//   Yellow LED      -> GPIO 27
//   Green LED       -> GPIO 14
//   Buzzer          -> GPIO 13
//
// Libraries: DHT sensor library (Adafruit) + Adafruit Unified Sensor.
//
// Backend contract: POST /api/v1/readings (the existing JURAS ingestion
// endpoint). This node reports against lane node "I" (Lane I-L low point), not
// a building. Values are validated by the backend; a NaN/Inf or out-of-range
// reading is rejected instead of being stored as zero.
//
// For local development with the Wokwi Private IoT Gateway:
//   BACKEND_URL = "http://host.wokwi.internal:8000"
// For a public HTTPS backend, use its canonical base URL (no trailing slash).
// Never use a URL that redirects (301/302/307/308), because POST redirects are
// rejected here.
//
// Rain calibration: keep the sensor dry during boot. The sketch records the dry
// ADC baseline, then measures the absolute deviation from that baseline. This
// works with both types of comparator boards (voltage rising or falling when
// wet) without needing to know the polarity.

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

// Change this one line when the backend moves (local gateway, LAN IP or a
// public HTTPS deployment). Keep it a base URL; the path is added below.
const char* BACKEND_URL = "https://liability-boat-interaction-manuals.trycloudflare.com";
const char* TELEMETRY_PATH = "/api/v1/readings";

// Optional shared secret. Leave empty when the backend does not set
// DEVICE_API_KEY. When set on both sides it is sent as X-Device-Key.
const char* DEVICE_API_KEY = "";

// ==========================================
// 2. DEVICE / TARGET CONFIGURATION
// ==========================================

// Verified mapping: JM-R01 is the rain-level sensor at lane node I.
#define DEVICE_ID "JURAS-STORM-001"
#define SENSOR_CODE "JM-R01"
#define NODE_CODE "I"

// ==========================================
// 3. PIN CONFIGURATION
// ==========================================

#define TRIG_PIN 5
#define ECHO_PIN 18
#define RAIN_PIN 34
#define DHT_PIN 4
#define LED_RED_PIN 26
#define BUZZER_PIN 27

#define DHT_TYPE DHT22

// ==========================================
// 4. FLOOD THRESHOLDS (DEMO VALUES)
// ==========================================

// Local alarm bands mirror the dashboard and backend high bands. The backend
// still computes the authoritative risk score from water_level_cm / rain_mmh.
const float LEVEL_WARNING_CM = 10.0;
const float LEVEL_CRITICAL_CM = 25.0;
const float LEVEL_BACKEND_CRITICAL_CM = 40.0;
const float RAIN_CRITICAL_MMH = 30.0;

// HC-SR04 is mounted this far above the channel bed / road low point.
const float SENSOR_MOUNT_CM = 100.0;
const float RAIN_MMH_PER_PCT = 1.5;

// ==========================================
// 5. TIMING
// ==========================================

const unsigned long SENSOR_INTERVAL_MS = 2000;
const unsigned long UPLOAD_INTERVAL_MS = 2500;
const unsigned long FLUSH_INTERVAL_MS = 1000;
const unsigned long MAX_BACKOFF_MS = 30000;
const unsigned long WIFI_RETRY_MS = 10000;
const unsigned long ALERT_BLINK_MS = 500;
const unsigned long BUZZER_BEEP_MS = 120;
const unsigned long BUZZER_PERIOD_MS = 2000;
const unsigned long NTP_RETRY_MS = 30000;
const int RAIN_CAL_SAMPLES = 20;
const size_t SAMPLE_BUFFER_SIZE = 12;

// ==========================================
// 6. STATE
// ==========================================

enum FloodState {
  STATE_NORMAL,
  STATE_WARNING,
  STATE_CRITICAL
};

// Declared before the first function: the Arduino auto-prototype pass hoists
// function signatures to the top of the sketch, so a custom return type must
// already be visible there.
enum PostResult {
  POST_OK,
  POST_RETRY,
  POST_DROP
};

struct Sample {
  uint32_t seq;
  time_t epoch;
  float water_level_cm;
  float distance_cm;
  float rain_mmh;
  float rain_pct;
  int rain_raw;
  float temperature_c;
  float humidity_pct;
  bool dht_ok;
  bool sonar_ok;
  int rssi;
};

DHT dht(DHT_PIN, DHT_TYPE);

FloodState floodState = STATE_NORMAL;

float waterLevelCm = NAN;
float distanceCm = NAN;
float rainMmh = 0.0;
float rainPct = 0.0;
int rainRaw = 0;
float rainDryRaw = 2048.0;

float temperatureC = NAN;
float humidityPct = NAN;

bool dhtOk = false;
bool sonarOk = false;
bool wifiWasConnected = false;
bool ntpRequested = false;

uint32_t sequence = 0;

Sample pending;
Sample queue[SAMPLE_BUFFER_SIZE];
size_t queueCount = 0;

unsigned long lastSensorRead = 0;
unsigned long lastUpload = 0;
unsigned long lastWifiAttempt = 0;
unsigned long lastNtpRequest = 0;
unsigned long retryBackoffMs = 0;

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
    Serial.print("Reconnecting WiFi... (status ");
    Serial.print((int)WiFi.status());
    Serial.println(")");
    WiFi.disconnect();
    delay(100);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  }
}

// ==========================================
// 8. SENSOR READING
// ==========================================

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (duration == 0) {
    return NAN;
  }
  float cm = duration * 0.0343 / 2.0;
  if (!isfinite(cm) || cm <= 0.0 || cm > 400.0) {
    return NAN;
  }
  return cm;
}

float calibrateRainBaseline() {
  long sum = 0;
  for (int i = 0; i < RAIN_CAL_SAMPLES; i++) {
    sum += analogRead(RAIN_PIN);
    delay(50);
  }
  return (float)sum / RAIN_CAL_SAMPLES;
}

float readRainPercent() {
  rainRaw = analogRead(RAIN_PIN);
  float span = max(rainDryRaw, 4095.0f - rainDryRaw);
  if (span < 1.0) {
    span = 4095.0;
  }
  float pct = (fabs((float)rainRaw - rainDryRaw) / span) * 100.0;
  return constrain(pct, 0.0, 100.0);
}

void readSensors() {
  distanceCm = readDistanceCm();
  sonarOk = isfinite(distanceCm);
  if (sonarOk) {
    waterLevelCm = SENSOR_MOUNT_CM - distanceCm;
    waterLevelCm = constrain(waterLevelCm, 0.0, 1000.0);
  } else {
    // Do not resend the previous level: a missing echo is missing data.
    waterLevelCm = NAN;
    Serial.println("HC-SR04 echo lost. Water level will be N/A.");
  }

  float t = dht.readTemperature();
  float h = dht.readHumidity();
  dhtOk = isfinite(t) && isfinite(h) &&
          t > -40.0 && t < 125.0 &&
          h >= 0.0 && h <= 100.0;
  if (dhtOk) {
    temperatureC = t;
    humidityPct = h;
  } else {
    temperatureC = NAN;
    humidityPct = NAN;
    Serial.println("DHT22 read failed. Temperature/humidity will be N/A.");
  }

  // Smooth the rain estimate so a single noisy ADC sample cannot raise an
  // incident, while keeping the raw value for debugging.
  float pct = readRainPercent();
  rainPct = rainPct * 0.65 + pct * 0.35;
  rainMmh = rainPct * RAIN_MMH_PER_PCT;
}

// ==========================================
// 9. FLOOD CLASSIFICATION
// ==========================================

void calculateFloodState() {
  bool critical =
      waterLevelCm >= LEVEL_CRITICAL_CM ||
      rainMmh >= RAIN_CRITICAL_MMH;

  bool warning = !sonarOk || waterLevelCm >= LEVEL_WARNING_CM;

  if (critical) {
    floodState = STATE_CRITICAL;
  } else if (warning) {
    floodState = STATE_WARNING;
  } else {
    floodState = STATE_NORMAL;
  }
}

const char* stateName() {
  switch (floodState) {
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

  digitalWrite(LED_RED_PIN,
               floodState == STATE_CRITICAL ? HIGH
               : floodState == STATE_WARNING ? (blink ? HIGH : LOW)
               : LOW);

  if (floodState == STATE_CRITICAL) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (floodState == STATE_WARNING) {
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
  Serial.println("\n======= JURAS STORMWATER MONITOR =======");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);
  Serial.print("Sensor: ");
  Serial.println(SENSOR_CODE);
  Serial.print("Lane node: ");
  Serial.println(NODE_CODE);
  Serial.print("Sonar ok: ");
  Serial.println(sonarOk ? "yes" : "no");
  Serial.print("Distance: ");
  Serial.println(isfinite(distanceCm) ? String(distanceCm, 1) : String("n/a"));
  Serial.print("Water level: ");
  Serial.print(waterLevelCm, 1);
  Serial.println(" cm");
  Serial.print("Rain raw: ");
  Serial.println(rainRaw);
  Serial.print("Rain: ");
  Serial.print(rainMmh, 1);
  Serial.print(" mm/h (");
  Serial.print(rainPct, 1);
  Serial.println("%)");
  Serial.print("DHT ok: ");
  Serial.println(dhtOk ? "yes" : "no");
  Serial.print("Temperature: ");
  Serial.println(isfinite(temperatureC) ? String(temperatureC, 2) : String("n/a"));
  Serial.print("Humidity: ");
  Serial.println(isfinite(humidityPct) ? String(humidityPct, 2) : String("n/a"));
  Serial.print("State: ");
  Serial.print(stateName());
  Serial.print(" (backend critical at ");
  Serial.print(LEVEL_BACKEND_CRITICAL_CM, 0);
  Serial.println(" cm)");
  Serial.println("=========================================");
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
  s.water_level_cm = waterLevelCm;
  s.distance_cm = distanceCm;
  s.rain_mmh = rainMmh;
  s.rain_pct = rainPct;
  s.rain_raw = rainRaw;
  s.temperature_c = temperatureC;
  s.humidity_pct = humidityPct;
  s.dht_ok = dhtOk;
  s.sonar_ok = sonarOk;
  s.rssi = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  return s;
}

String buildPayload(const Sample &s) {
  String p = "{";
  p += "\"device_id\":\"" DEVICE_ID "\",";
  p += "\"sensor_id\":\"" SENSOR_CODE "\",";
  p += "\"node_code\":\"" NODE_CODE "\",";
  p += "\"hazard\":\"flood\",";
  p += "\"source\":\"simulation\",";
  p += "\"simulation\":true,";

  if (s.epoch >= 1700000000) {
    p += "\"observed_at\":\"" + isoUtc(s.epoch) + "\",";
  }

  p += "\"values\":{";
  bool first = true;
  auto addField = [&p, &first](const String &field) {
    if (!first) {
      p += ",";
    }
    p += field;
    first = false;
  };

  // Ultrasonic failure omits level/distance entirely instead of sending a
  // stale level or a zero.  Rain ADC values are always physical samples.
  if (s.sonar_ok && isfinite(s.water_level_cm) && isfinite(s.distance_cm)) {
    addField("\"water_level_cm\":" + String(s.water_level_cm, 1));
    addField("\"level_cm\":" + String(s.water_level_cm, 1));
    addField("\"distance_cm\":" + String(s.distance_cm, 1));
  }
  addField("\"rain_mmh\":" + String(s.rain_mmh, 1));
  addField("\"rain_pct\":" + String(s.rain_pct, 1));
  addField("\"rain_raw\":" + String(s.rain_raw));

  if (s.dht_ok && isfinite(s.temperature_c)) {
    addField("\"temperature_c\":" + String(s.temperature_c, 2));
  }
  if (s.dht_ok && isfinite(s.humidity_pct)) {
    addField("\"humidity_pct\":" + String(s.humidity_pct, 2));
  }

  addField("\"dht_ok\":" + String(s.dht_ok ? 1 : 0));
  addField("\"sonar_ok\":" + String(s.sonar_ok ? 1 : 0));
  addField("\"rssi\":" + String(s.rssi));
  addField("\"seq\":" + String((unsigned long)s.seq));
  p += "}}";
  return p;
}

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
    String body = http.getString();
    if (body.length()) {
      Serial.print("Response: ");
      Serial.println(body);
    }
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

  String base = String(BACKEND_URL);
  while (base.endsWith("/")) {
    base.remove(base.length() - 1);
  }
  String url = base + TELEMETRY_PATH;
  String payload = buildPayload(s);

  Serial.println("POST " + url);
  Serial.println(payload);

  HTTPClient http;
  http.setConnectTimeout(2500);
  http.setTimeout(2500);
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
  unsigned long interval = flushing ? FLUSH_INTERVAL_MS : (retryBackoffMs > 0 ? retryBackoffMs : UPLOAD_INTERVAL_MS);
  if (now - lastUpload < interval) {
    return;
  }
  lastUpload = now;

  Sample sample = flushing ? queue[0] : pending;
  PostResult result = postSample(sample);

  if (result == POST_OK) {
    retryBackoffMs = 0;
    if (flushing) {
      popSample();
    }
  } else if (result == POST_DROP) {
    retryBackoffMs = 0;
    if (flushing) {
      popSample();
    }
    Serial.println("Sample dropped after non-retryable response.");
  } else if (!flushing) {
    enqueueSample(pending);
    retryBackoffMs = retryBackoffMs == 0 ? UPLOAD_INTERVAL_MS : min(MAX_BACKOFF_MS, retryBackoffMs * 2);
    Serial.print("Upload failed: sample buffered. Retry in ");
    Serial.print(retryBackoffMs);
    Serial.println(" ms");
  } else {
    retryBackoffMs = retryBackoffMs == 0 ? FLUSH_INTERVAL_MS : min(MAX_BACKOFF_MS, retryBackoffMs * 2);
    Serial.print("Flush failed: retry in ");
    Serial.print(retryBackoffMs);
    Serial.println(" ms");
  }
}

// ==========================================
// 14. SETUP
// ==========================================

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(RAIN_PIN, INPUT);

  digitalWrite(LED_RED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(TRIG_PIN, LOW);

  analogReadResolution(12);

  Serial.println("\nStarting JURAS Stormwater Node");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);

  dht.begin();

  Serial.print("Calibrating rain sensor (keep it dry)");
  rainDryRaw = calibrateRainBaseline();
  Serial.print(" -> ");
  Serial.println(rainDryRaw, 1);

  readSensors();
  calculateFloodState();
  pending = captureSample();
  printReadings();

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
    Serial.print("WiFi not connected yet (status ");
    Serial.print((int)WiFi.status());
    Serial.println("). Will retry in the main loop.");
    lastWifiAttempt = millis();
  }

  Serial.println("JURAS STORMWATER DEVICE READY");
}

// ==========================================
// 15. MAIN LOOP
// ==========================================

void loop() {
  unsigned long now = millis();

  maintainWifi(now);
  updateAlerts(now);

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    readSensors();
    calculateFloodState();
    pending = captureSample();
    printReadings();
  }

  uploadLoop(now);
  delay(10);
}
