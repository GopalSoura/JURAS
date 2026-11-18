# JURAS Wokwi ESP32 nodes

Three ESP32 DevKit C V4 sketches post to the existing JURAS ingestion endpoint
`POST /api/v1/readings`. They never create sensors, buildings or lanes; the
backend validates the device/sensor/target mapping and forces
`source=simulation`, `simulation=true` for these registered nodes. The dashboard
tells them apart from seeded data with the `realtime` flag, so they only show up
in **REALTIME** mode.

| Sketch | Dashboard label | Device ID | Sensor | Target | Hazard |
| --- | --- | --- | --- | --- | --- |
| `fire_node` | Old Jammu Heritage Building | `JURAS-FIRE-001` | `JM-014` (`smoke_temp`) | building `B-014` | `fire` |
| `structural_node` | Residential Structure — Purani Mandi | `JURAS-STRUCT-001` | `JM-S07` (`structure`) | building `B-007` | `structural` |
| `stormwater_node` | Flood-Prone Lane Building — Purani Mandi | `JURAS-STORM-001` | `JM-R01` (`rain_level`) | lane node `I` | `flood` |

> The `JURAS-BLD-00x` building codes are display labels only — those rows do not
> exist in the database. The sketches keep posting to the real targets above.

---

## Two-laptop setup (Wokwi online editor)

The nodes run in the **wokwi.com online editor on a second laptop**, and the
JURAS backend runs on this laptop. The free Wokwi public gateway only reaches the
public internet — it **cannot** reach this laptop's LAN IP (`10.145.121.35`). So
we expose the backend with a public HTTPS tunnel and point the sketches at it.

```
[ Laptop B: wokwi.com ]  --HTTPS-->  [ Cloudflare tunnel ]  -->  [ Laptop A: JURAS backend 127.0.0.1:8000 ]
```

### Laptop A (this one) — backend + tunnel

1. Start the backend:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe run.py
   ```

   It listens on `http://127.0.0.1:8000`. Check <http://127.0.0.1:8000/health>.

2. Start the public tunnel (a quick tunnel, no account needed):

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate
   ```

   `cloudflared.exe` is already in `C:\Users\Hp\Downloads\`. The command prints a
   `https://<random-words>.trycloudflare.com` URL and keeps running. Leave both
   windows open while the demo runs.

3. Verify the tunnel before touching Wokwi:

   ```powershell
   curl.exe https://<your-tunnel>.trycloudflare.com/health
   # -> {"status":"healthy","db":true}
   ```

   Current verified URL: `https://liability-boat-interaction-manuals.trycloudflare.com`

### Laptop B — Wokwi online editor

For each of the three nodes, create a new ESP32 project on
<https://wokwi.com> and fill in its tabs:

| Wokwi tab | What to paste |
| --- | --- |
| `sketch.ino` | the matching `firmware/<node>/sketch.ino` file |
| `diagram.json` | the matching `firmware/<node>/diagram.json` file |
| `libraries.txt` | the matching `firmware/<node>/libraries.txt` (structural node needs none) |

> Each node folder has the sketch under two names: `sketch.ino` (matches the
> Wokwi online editor tab, so you can copy it straight in) and `<node>.ino` (a
> descriptive copy). The content is identical. If you ever open a node with the
> Arduino IDE or the Wokwi VS Code extension, keep only one of the two `.ino`
> files in the folder — two sketches in one folder make the compiler complain.

Then press the green **play** button. The Serial Monitor should show
`JURAS ... DEVICE READY`, a WiFi `connected` line, and then a
`POST https://.../api/v1/readings` line every ~2.5 s with
`Telemetry accepted: HTTP 201`.

### Dashboard

On this laptop open the JURAS dashboard and switch the top bar to **REALTIME**.
The three IoT cards move from `WAITING` to `LIVE` as frames arrive; missing
sensors show `N/A`. **SIMULATION** mode is untouched and keeps showing all the
seeded incidents.

### If the tunnel URL changes

Quick-tunnel URLs are random and change every time `cloudflared` restarts. If
that happens:

1. Copy the new `https://...trycloudflare.com` URL from the `cloudflared` window.
2. In each sketch update the one line:

   ```cpp
   const char* BACKEND_URL = "https://liability-boat-interaction-manuals.trycloudflare.com";
   ```

   Keep it a base URL — no trailing slash, and never a URL that redirects, since
   the sketches disable redirect following on purpose.
3. Re-run the three Wokwi projects.

---

## Wiring

The `diagram.json` files already contain this wiring, so normally you only paste
them. The tables below are the reference.

### Fire node
| Part | Pin |
| --- | --- |
| DHT22 DATA (`SDA`) | GPIO 15 |
| MQ-2 `AOUT` | GPIO 34 |
| Flame button (to GND, active LOW) | GPIO 25 |
| Red LED (via 220 Ω) | GPIO 26 |
| Yellow LED (via 220 Ω) | GPIO 27 |
| Green LED (via 220 Ω) | GPIO 14 |
| Buzzer (pin 2 → GPIO, pin 1 → GND) | GPIO 13 |

### Structural node
| Part | Pin |
| --- | --- |
| MPU6050 `SDA` / `SCL` | GPIO 21 / 22 |
| Crack potentiometer `SIG` | GPIO 34 |
| Vibration potentiometer `SIG` | GPIO 35 |
| Red LED (via 220 Ω) | GPIO 26 |
| Buzzer (pin 2 → GPIO, pin 1 → GND) | GPIO 27 |

The sketch talks to the MPU6050 over raw I2C (address `0x68`), so no IMU library
is required. Keep the node still during boot: the first 20 samples are the
commissioning baseline, and `tilt_deg` is the angle away from it.

### Stormwater node
| Part | Pin |
| --- | --- |
| HC-SR04 `TRIG` / `ECHO` | GPIO 5 / 18 |
| Rain sensor `AO` | GPIO 34 |
| DHT22 DATA (`SDA`) | GPIO 4 |
| Red LED (via 220 Ω) | GPIO 26 |
| Buzzer (pin 2 → GPIO, pin 1 → GND) | GPIO 27 |

Keep the rain sensor dry during boot; the dry ADC value is the calibration
baseline. Water level is `SENSOR_MOUNT_CM (100 cm) - HC-SR04 distance`.

---

## Simulating the sensors in Wokwi

Click a part while the simulation runs to change its value:

| Node | Part | What to change |
| --- | --- | --- |
| Fire | DHT22 | temperature / humidity sliders |
| Fire | MQ-2 (`wokwi-gas-sensor`) | `ppm` — raise well above 400 to trigger smoke alarms |
| Fire | Flame button (`FLAME`, key `F`) | press it (or hold `F`) to assert the flame signal |
| Structural | MPU6050 | change `accelX/accelY` to tilt the structure |
| Structural | `CRACK` potentiometer | turn the knob to open the crack |
| Structural | `VIBRATION` potentiometer | turn the knob to raise vibration |
| Stormwater | HC-SR04 | set `distance` — `100 - distance` is the water level (`90`→10 cm, `60`→40 cm critical) |
| Stormwater | Rain sensor (`wokwi-photoresistor-sensor`) | change `lux` — moving away from the dry baseline raises `rain_mmh` |

The Wokwi `wokwi-buzzer` is a passive piezo, while the sketches drive an
active-buzzer DC signal, so the buzzer may not sound in the simulator. The LED
still reflects the alarm state — that is expected, not a fault.

---

## Backend prerequisite

The mappings are idempotent and already applied to the seeded database. On a
fresh database run:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\seed_demo_data.py
.\.venv\Scripts\python.exe scripts\ensure_iot_sensors.py
```

`ensure_iot_sensors.py` only updates the three existing sensor rows. It fails
loudly if `B-014`, `B-007` or lane node `I` is missing instead of inventing an ID.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Serial shows `WiFi connected` then `HTTP transport error` / `-1` | Tunnel down or URL stale. Re-check `/health` through the tunnel and update `BACKEND_URL`. |
| `Non-retryable HTTP error: 404` | `BACKEND_URL` includes a wrong path or a trailing slash. It must be just the origin. |
| `Non-retryable HTTP error: 422` | A sensor/target mapping is wrong — re-run `ensure_iot_sensors.py`. |
| Serial shows `Offline: sample buffered` | Backend unreachable; the sketch buffers the last 12 samples and replays them on reconnect. |
| DHT22 keeps printing `read failed` | Wokwi DHT timing on ESP32 — reload the project; if it persists, use the "DHT sensor library for ESPx" library and adjust the two `dht.read*()` calls. |
| Cards stay `WAITING` in REALTIME | Confirm you are in REALTIME mode and that `POST` returns `HTTP 201` in the Serial Monitor. |
| Buzzer silent in Wokwi | Expected (passive piezo + DC drive); watch the LED instead. |
