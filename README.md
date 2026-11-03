[README.md](https://github.com/user-attachments/files/34341673/README.md)
# E-Ink Calendar

A battery-friendly desk calendar: an **ESP32** drives a **7.5" 800×480 black-and-white e-paper display** that shows the next seven days from a Google Calendar. A small **Flask service on Google Cloud Run** renders the week view and the ESP32 wakes up, fetches it, redraws only if something changed, and goes back to deep sleep.

<!-- Add a photo of the finished display, then uncomment the next line:
![The finished e-ink calendar](docs/display.jpg)
-->

## How it works

```
Google Calendar (private ICS feed)
        │
        ▼
Cloud Run (Flask + headless Chromium)
  ICS → expand recurring events → HTML/CSS week grid → screenshot → 1-bit 800×480 bitmap
        │   GET /frame.bin?key=…   (48,000 bytes, ETag)
        ▼
ESP32 (deep sleep, wakes every 20 min)
  WiFi → HTTPS fetch → 304? keep screen : redraw e-paper → deep sleep
```

- **Layout is HTML/CSS.** The backend builds the week grid with a Jinja2 template, screenshots it with Playwright, and thresholds it to 1-bit with Pillow. Changing the design means editing CSS, not drawing pixels in C++.
- **Recurring events are handled properly.** Events come from the calendar's ICS feed and are expanded with `recurring-ical-events`, including multi-day and all-day events.
- **The ESP32 does very little.** It downloads a ready-to-draw frame, which keeps the firmware small and the radio-on time short.

## Tech stack

| Part | Tools |
|---|---|
| Firmware | C++, PlatformIO, Arduino framework, GxEPD2, `HTTPClient` / `WiFiClientSecure` |
| Backend | Python 3.12, Flask, gunicorn, Playwright (Chromium), Jinja2, Pillow, icalendar, recurring-ical-events |
| Deployment | Docker, Google Cloud Run (deployed from source with `gcloud`) |
| Hardware | ESP32, Waveshare 7.5" 800×480 B/W e-paper panel |

## Design decisions

- **Conditional fetches (ETag).** The backend returns an ETag for each frame; the ESP32 sends `If-None-Match` and gets a `304` when nothing changed, so the slow, flashing e-paper refresh only happens when the content is different.
- **Fail safe.** If a fetch fails or the response isn't exactly 48,000 bytes, the display keeps its last good image. The firmware retries once, then sleeps 5 minutes before trying again.
- **Render caching.** The backend caches the rendered frame for 5 minutes behind a lock, so overlapping requests don't launch overlapping Chromium instances.
- **Scale-to-zero hosting.** Cloud Run runs the container only when the device asks for a frame, so the service costs little at this request volume. The firmware's HTTP timeout is set for the cold start.
- **Secrets stay out of the repo.** The calendar link, API token and timezone are environment variables on the server; WiFi credentials and the endpoint URL live in a git-ignored `config.h`. Every request must carry a token (`?key=…`) or it gets a 403.
- **Timezones.** Containers run in UTC, so the backend takes a `CAL_TZ` setting to keep "today" and event times correct.

## Repo layout

```
backend/    Flask app, renderer, Dockerfile, requirements
firmware/   PlatformIO project for the ESP32 (src/main.cpp, src/config.example.h)
```

## Running it

### Backend

Local preview:

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
ICS_URL="<your calendar's secret iCal address>" API_TOKEN="test" python server.py
# open http://localhost:8000/frame.png?key=test
```

Deploy to Cloud Run (from `backend/`, with an `env.yaml` that is **not** committed):

```yaml
# env.yaml
ICS_URL: "<your calendar's secret iCal address>"
API_TOKEN: "<a long random string>"
CAL_TZ: "America/New_York"
```

```bash
gcloud run deploy eink-calendar \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --concurrency 4 \
  --max-instances 1 \
  --allow-unauthenticated \
  --env-vars-file env.yaml
```

The service is public at the network level and protected by the token, since the ESP32 can't do Google IAM authentication.

### Firmware

```bash
cd firmware
cp src/config.example.h src/config.h
# edit src/config.h: WiFi name/password, IMAGE_URL (…/frame.bin?key=<token>), REFRESH_INTERVAL_MINUTES
pio run -t upload
pio device monitor
```

Display wiring is defined at the top of `src/main.cpp` (BUSY 25, RST 26, DC 27, CS 15, SCK 13, MOSI 14).

## Roadmap

- LiPo battery and a printed enclosure designed in SolidWorks
- Pin Google's root certificate in the firmware instead of `setInsecure()`
