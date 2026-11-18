// JURAS Structural Health Node - ESP32 DevKit C V4 (Wokwi)
//
// Hardware:
//   MPU6050 SDA      -> GPIO 21
//   MPU6050 SCL      -> GPIO 22
//   Crack pot wiper  -> GPIO 34 (analog)
//   Vibration AO     -> GPIO 35 (analog)
//   Red LED          -> GPIO 26
//   Yellow LED       -> GPIO 27
//   Green LED        -> GPIO 14
//   Buzzer           -> GPIO 13
//
// Libraries: none beyond the ESP32 Arduino core. The MPU6050 is read over raw
// I2C so the sketch does not depend on a third-party IMU library.
//
// Backend contract: POST /api/v1/readings (the existing JURAS ingestion
// endpoint). Values are validated by the backend; a NaN/Inf or out-of-range
// reading is rejected instead of being stored as zero.
//
// For local development with the Wokwi Private IoT Gateway:
//   BACKEND_URL = "http://host.wokwi.internal:8000"
// For a public HTTPS backend, use its canonical base URL (no trailing slash).
// Never use a URL that redirects (301/302/307/308), because POST redirects are
// rejected here.

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
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

// Must match an existing JURAS sensor code and its building code.
// Verified mapping: JM-S07 belongs to B-007.
#define DEVICE_ID "JURAS-STRUCT-001"
#define SENSOR_CODE "JM-S07"
#define BUILDING_CODE "B-007"

// ==========================================
// 3. PIN CONFIGURATION
// ==========================================

#define MPU_SDA_PIN 21
#define MPU_SCL_PIN 22
#define CRACK_PIN 34
#define VIB_PIN 35
#define LED_RED_PIN 26
#define BUZZER_PIN 27

// ==========================================
// 4. STRUCTURAL THRESHOLDS (DEMO VALUES)
// ==========================================

// Local warning bands match the dashboard marker colours; critical bands match
// backend/app/risk/thresholds.py so the local buzzer and server risk agree.
const float TILT_WARNING_DEG = 0.45;
const float TILT_CRITICAL_DEG = 1.10;
const float CRACK_WARNING_MM = 0.55;
const float CRACK_CRITICAL_MM = 1.40;
const float VIB_WARNING_MS2 = 0.50;
const float VIB_CRITICAL_MS2 = 2.00;

// Demo scaling for the two analog sensors.
const float CRACK_FULL_SCALE_MM = 5.0;       // pot 0..4095 -> 0..5 mm
const float VIB_COUNTS_TO_MS2 = 9.81 / 2048.0;
const float SENSOR_HEIGHT_MM = 3300.0;       // used for deviation_mm estimate

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
const unsigned long MPU_RETRY_MS = 5000;
const int MPU_BASELINE_SAMPLES = 20;
const size_t SAMPLE_BUFFER_SIZE = 12;

// ==========================================
// 6. STATE
// ==========================================

enum StructState {
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
  float tilt_deg;
  float crack_mm;
  int crack_raw;
  float vib_rms;
  float deviation_mm;
  bool mpu_ok;
  int rssi;
};

StructState structState = STATE_NORMAL;

float tiltDeg = 0.0;
float crackMm = 0.0;
int crackRaw = 0;
float vibRms = 0.0;
float deviationMm = 0.0;
bool mpuOk = false;

float baseAx = 0.0;
float baseAy = 0.0;
float baseAz = 1.0;
bool mpuReady = false;
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
unsigned long lastMpuAttempt = 0;
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
// 8. MPU6050 OVER RAW I2C
// ==========================================

const uint8_t MPU_ADDR = 0x68;

bool mpuWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool mpuRead(uint8_t reg, uint8_t *buffer, uint8_t length) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom((uint8_t)MPU_ADDR, length) != length) {
    return false;
  }
  for (uint8_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }
  return true;
}

bool initMpu() {
  Wire.begin(MPU_SDA_PIN, MPU_SCL_PIN, 400000);
  // Wake from sleep, 44 Hz DLPF, +/-2g full scale.
  if (!mpuWrite(0x6B, 0x00)) {
    return false;
  }
  delay(50);
  mpuWrite(0x1A, 0x03);
  mpuWrite(0x1C, 0x00);
  return true;
}

bool readAccel(float &ax, float &ay, float &az) {
  uint8_t buf[6];
  if (!mpuRead(0x3B, buf, 6)) {
    return false;
  }
  int16_t rawAx = (int16_t)((buf[0] << 8) | buf[1]);
  int16_t rawAy = (int16_t)((buf[2] << 8) | buf[3]);
  int16_t rawAz = (int16_t)((buf[4] << 8) | buf[5]);
  ax = rawAx / 16384.0;
  ay = rawAy / 16384.0;
  az = rawAz / 16384.0;
  if (!isfinite(ax) || !isfinite(ay) || !isfinite(az)) {
    return false;
  }
  // A missing or unpowered MPU6050 typically reads all zero.
  return (fabs(ax) + fabs(ay) + fabs(az)) > 0.1;
}

bool calibrateMpuBaseline() {
  float sx = 0.0;
  float sy = 0.0;
  float sz = 0.0;
  int good = 0;
  for (int i = 0; i < MPU_BASELINE_SAMPLES; i++) {
    float ax, ay, az;
    if (readAccel(ax, ay, az)) {
      sx += ax;
      sy += ay;
      sz += az;
      good++;
    }
    delay(20);
  }
  if (good < MPU_BASELINE_SAMPLES / 2) {
    return false;
  }
  baseAx = sx / good;
  baseAy = sy / good;
  baseAz = sz / good;
  float norm = sqrt(baseAx * baseAx + baseAy * baseAy + baseAz * baseAz);
  if (norm < 0.1) {
    return false;
  }
  baseAx /= norm;
  baseAy /= norm;
  baseAz /= norm;
  return true;
}

// Angle between the current gravity vector and the commissioning baseline.
float tiltFromBaseline(float ax, float ay, float az) {
  float norm = sqrt(ax * ax + ay * ay + az * az);
  if (norm < 0.1) {
    return tiltDeg;
  }
  float dot = (ax * baseAx + ay * baseAy + az * baseAz) / norm;
  dot = constrain(dot, -1.0, 1.0);
  return acos(dot) * 180.0 / PI;
}

// ==========================================
// 9. SENSOR READING
// ==========================================

void readSensors() {
  unsigned long now = millis();

  if (!mpuReady && now - lastMpuAttempt >= MPU_RETRY_MS) {
    lastMpuAttempt = now;
    Serial.println("Initialising MPU6050...");
    mpuReady = initMpu();
    if (mpuReady) {
      mpuOk = calibrateMpuBaseline();
      Serial.print("MPU6050 baseline: ");
      Serial.print(baseAx, 3);
      Serial.print(", ");
      Serial.print(baseAy, 3);
      Serial.print(", ");
      Serial.println(baseAz, 3);
    } else {
      Serial.println("MPU6050 not responding. Keeping last good tilt.");
    }
  }

  if (mpuReady) {
    float ax, ay, az;
    if (readAccel(ax, ay, az)) {
      mpuOk = true;
      tiltDeg = tiltFromBaseline(ax, ay, az);
    } else {
      mpuOk = false;
      Serial.println("MPU6050 read failed. Keeping last good tilt.");
    }
  } else {
    mpuOk = false;
  }

  long rawSum = 0;
  for (int i = 0; i < 8; i++) {
    rawSum += analogRead(CRACK_PIN);
  }
  crackRaw = (int)(rawSum / 8);
  crackRaw = constrain(crackRaw, 0, 4095);
  crackMm = (crackRaw / 4095.0) * CRACK_FULL_SCALE_MM;

  // AC RMS around the window mean, converted with a demo scale.
  const int samples = 200;
  float sum = 0.0;
  float sumSq = 0.0;
  for (int i = 0; i < samples; i++) {
    int raw = analogRead(VIB_PIN);
    sum += raw;
    sumSq += (float)raw * (float)raw;
    delayMicroseconds(500);
  }
  float mean = sum / samples;
  float variance = (sumSq / samples) - (mean * mean);
  if (variance < 0.0) {
    variance = 0.0;
  }
  vibRms = sqrt(variance) * VIB_COUNTS_TO_MS2;

  if (isfinite(tiltDeg)) {
    deviationMm = tan(tiltDeg * PI / 180.0) * SENSOR_HEIGHT_MM;
    if (isfinite(deviationMm)) {
      deviationMm = constrain(deviationMm, 0.0, 10000.0);
    } else {
      deviationMm = NAN;
    }
  } else {
    deviationMm = NAN;
  }
}

// ==========================================
// 10. STRUCTURAL CLASSIFICATION
// ==========================================

void calculateStructState() {
  bool critical =
      tiltDeg >= TILT_CRITICAL_DEG ||
      crackMm >= CRACK_CRITICAL_MM ||
      vibRms >= VIB_CRITICAL_MS2;

  bool warning =
      !mpuOk ||
      tiltDeg >= TILT_WARNING_DEG ||
      crackMm >= CRACK_WARNING_MM ||
      vibRms >= VIB_WARNING_MS2;

  if (critical) {
    structState = STATE_CRITICAL;
  } else if (warning) {
    structState = STATE_WARNING;
  } else {
    structState = STATE_NORMAL;
  }
}

const char* stateName() {
  switch (structState) {
    case STATE_CRITICAL:
      return "critical";
    case STATE_WARNING:
      return "warning";
    default:
      return "normal";
  }
}

// ==========================================
// 11. LED + BUZZER OUTPUT
// ==========================================

void updateAlerts(unsigned long now) {
  bool blink = ((now / ALERT_BLINK_MS) % 2) == 0;

  digitalWrite(LED_RED_PIN,
               structState == STATE_CRITICAL ? HIGH
               : structState == STATE_WARNING ? (blink ? HIGH : LOW)
               : LOW);

  if (structState == STATE_CRITICAL) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (structState == STATE_WARNING) {
    bool beep = (now % BUZZER_PERIOD_MS) < BUZZER_BEEP_MS;
    digitalWrite(BUZZER_PIN, beep ? HIGH : LOW);
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }
}

// ==========================================
// 12. SERIAL MONITOR
// ==========================================

void printReadings() {
  Serial.println("\n======= JURAS STRUCTURAL MONITOR =======");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);
  Serial.print("Sensor: ");
  Serial.println(SENSOR_CODE);
  Serial.print("Building: ");
  Serial.println(BUILDING_CODE);
  Serial.print("MPU ok: ");
  Serial.println(mpuOk ? "yes" : "no");
  Serial.print("Tilt: ");
  Serial.print(tiltDeg, 3);
  Serial.println(" deg");
  Serial.print("Crack: ");
  Serial.print(crackMm, 3);
  Serial.print(" mm (raw ");
  Serial.print(crackRaw);
  Serial.println(")");
  Serial.print("Vibration RMS: ");
  Serial.print(vibRms, 3);
  Serial.println(" m/s2");
  Serial.print("Deviation: ");
  Serial.print(deviationMm, 2);
  Serial.println(" mm");
  Serial.print("State: ");
  Serial.println(stateName());
  Serial.println("========================================");
}

// ==========================================
// 13. PAYLOAD + HTTP
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
  s.tilt_deg = tiltDeg;
  s.crack_mm = crackMm;
  s.crack_raw = crackRaw;
  s.vib_rms = vibRms;
  s.deviation_mm = deviationMm;
  s.mpu_ok = mpuOk;
  s.rssi = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  return s;
}

String buildPayload(const Sample &s) {
  String p = "{";
  p += "\"device_id\":\"" DEVICE_ID "\",";
  p += "\"sensor_id\":\"" SENSOR_CODE "\",";
  p += "\"building_id\":\"" BUILDING_CODE "\",";
  p += "\"hazard\":\"structural\",";
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

  // Only send physical samples that were actually acquired.  A missing MPU
  // sample or crack sample is omitted so the dashboard renders N/A instead
  // of a fabricated zero / stale value.
  if (s.mpu_ok && isfinite(s.tilt_deg) && isfinite(s.vib_rms) &&
      isfinite(s.deviation_mm)) {
    addField("\"tilt_deg\":" + String(s.tilt_deg, 3));
    addField("\"vib_rms\":" + String(s.vib_rms, 3));
    addField("\"deviation_mm\":" + String(s.deviation_mm, 2));
  }
  bool crackOk = isfinite(s.crack_mm);
  if (crackOk) {
    addField("\"crack_mm\":" + String(s.crack_mm, 3));
    addField("\"crack_raw\":" + String(s.crack_raw));
  }

  addField("\"mpu_ok\":" + String(s.mpu_ok ? 1 : 0));
  addField("\"crack_ok\":" + String(crackOk ? 1 : 0));
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
// 14. OFFLINE BUFFER + UPLOAD LOOP
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
// 15. SETUP
// ==========================================

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(CRACK_PIN, INPUT);
  pinMode(VIB_PIN, INPUT);

  digitalWrite(LED_RED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  analogReadResolution(12);

  Serial.println("\nStarting JURAS Structural Health Node");
  Serial.print("Device: ");
  Serial.println(DEVICE_ID);

  lastMpuAttempt = millis() - MPU_RETRY_MS;
  readSensors();
  calculateStructState();
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

  Serial.println("JURAS STRUCTURAL DEVICE READY");
}

// ==========================================
// 16. MAIN LOOP
// ==========================================

void loop() {
  unsigned long now = millis();

  maintainWifi(now);
  updateAlerts(now);

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    readSensors();
    calculateStructState();
    pending = captureSample();
    printReadings();
  }

  uploadLoop(now);
  delay(10);
}
