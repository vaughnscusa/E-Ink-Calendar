#pragma once

// ---- Edit these before flashing ----

#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"


// URL of the raw 1-bit bitmap your backend serves.
// Must be exactly WIDTH * HEIGHT / 8 bytes, MSB-first, 1 = white / 0 = black
// (GxEPD2's expected packed format).
#define IMAGE_URL "https://YOUR-SERVICE-URL/frame.bin?key=YOUR_TOKEN"

// How often to check for a new image, in minutes.
#define REFRESH_INTERVAL_MINUTES 20
