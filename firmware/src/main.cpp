// E-ink calendar firmware (ESP32 + Waveshare 7.5" 800x480 B/W)
//
// On each wake: connect to WiFi, fetch the pre-rendered 1-bit frame from the
// backend (IMAGE_URL in config.h), redraw the panel only if it changed (ETag),
// then deep-sleep for REFRESH_INTERVAL_MINUTES.

#include <Arduino.h>
#include <SPI.h>
#include <GxEPD2_BW.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "config.h"
#include <WiFiClientSecure.h>

#define PIN_BUSY 25
#define PIN_RST  26
#define PIN_DC   27
#define PIN_CS   15
#define PIN_SCK  13
#define PIN_MOSI 14

GxEPD2_BW<GxEPD2_750_T7, GxEPD2_750_T7::HEIGHT / 8> display(
  GxEPD2_750_T7(PIN_CS, PIN_DC, PIN_RST, PIN_BUSY));

static const size_t IMG_BYTES = 800 * 480 / 8;   // 48,000
static uint8_t imgBuf[IMG_BYTES];
RTC_DATA_ATTR char lastEtag[40] = "";            // survives deep sleep

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) delay(250);
  Serial.println(WiFi.status() == WL_CONNECTED ? "WiFi connected" : "WiFi failed");
  return WiFi.status() == WL_CONNECTED;
}

// 1 = new image downloaded, 0 = unchanged, -1 = error
int fetchFrame() {
  WiFiClientSecure client;
  client.setInsecure();            // encrypts, but doesn't verify the server's identity (fine for testing)

  HTTPClient http;
  http.begin(client, IMAGE_URL);
  http.setTimeout(45000);          // first request after idle can take 10-20 s (cold start + render)
  const char* keys[] = {"ETag"};
  http.collectHeaders(keys, 1);
  if (lastEtag[0]) http.addHeader("If-None-Match", lastEtag);

  int code = http.GET();
  if (code == 304) { http.end(); return 0; }
  if (code != 200) { Serial.printf("HTTP error %d\n", code); http.end(); return -1; }
  if (http.getSize() != (int)IMG_BYTES) {
    Serial.printf("Unexpected size %d\n", http.getSize());
    http.end(); return -1;
  }

  WiFiClient* s = http.getStreamPtr();
  size_t got = 0;
  uint32_t t0 = millis();
  while (got < IMG_BYTES && millis() - t0 < 20000) {
    got += s->readBytes(imgBuf + got, IMG_BYTES - got);
  }
  String etag = http.header("ETag");
  http.end();

  if (got != IMG_BYTES) { Serial.println("Short read"); return -1; }
  strlcpy(lastEtag, etag.c_str(), sizeof(lastEtag));
  return 1;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  int r = -1;
  if (connectWiFi()) {
    for (int attempt = 1; attempt <= 2 && r == -1; attempt++) {
      r = fetchFrame();
      Serial.printf("fetch attempt %d result: %d\n", attempt, r);
    }
    if (r == 1) {
      SPI.begin(PIN_SCK, 12, PIN_MOSI, PIN_CS);   // SCK, MISO, MOSI, CS
      display.init(115200);
      display.drawImage(imgBuf, 0, 0, 800, 480);   // 1 = white, 0 = black
      display.hibernate();
    }
  }

  WiFi.disconnect(true);
  uint64_t sleepMin = (r == -1) ? 5 : REFRESH_INTERVAL_MINUTES;
  esp_sleep_enable_timer_wakeup(sleepMin * 60ULL * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() {}