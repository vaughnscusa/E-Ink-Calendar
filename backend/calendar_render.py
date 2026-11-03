"""Week-view renderer for the e-ink calendar backend.

Pipeline: ICS feed -> expanded events -> HTML/CSS week grid -> screenshot
-> 1-bit 800x480 image.

Setup:
    pip install flask requests icalendar recurring-ical-events jinja2 pillow playwright
    playwright install chromium

Used by app.py (/frame.png for preview, /frame.bin for the ESP32).
"""
import io
import os
import threading
import time
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import icalendar
import recurring_ical_events
from jinja2 import Template
from PIL import Image
from playwright.sync_api import sync_playwright

_tz = os.environ.get("CAL_TZ")
TZ = ZoneInfo(_tz) if _tz else None  # None = system local time
DAYS = 7              # columns shown, starting today
MAX_PER_DAY = 8       # events per column before "+N more"
CACHE_SECONDS = 300   # re-render at most every 5 min
_cache = {}
_lock = threading.Lock()

PAGE = Template("""<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;width:800px;height:480px;background:#fff;color:#000;
     font-family:'DejaVu Sans',Arial,sans-serif;display:flex;overflow:hidden}
.col{flex:1;min-width:0;border-right:2px solid #000;overflow:hidden}
.col:last-child{border-right:none}
.head{text-align:center;padding:8px 0;font-weight:bold;font-size:18px;
      border-bottom:3px solid #000}
.today .head{background:#000;color:#fff}
.ev{padding:4px 5px;border-bottom:1px solid #000;font-size:13px;line-height:1.2;
    word-wrap:break-word}
.ev .t{font-weight:bold}
.allday{background:#000;color:#fff;font-weight:bold}
.more{padding:4px 5px;font-size:12px;font-style:italic}
</style></head><body>
{% for d in days %}<div class="col{{ ' today' if d.today }}">
<div class="head">{{ d.label }}</div>
{% for e in d.events %}<div class="ev{{ ' allday' if e.all_day }}">
{% if not e.all_day %}<div class="t">{{ e.time }}</div>{% endif %}{{ e.title }}</div>
{% endfor %}{% if d.more %}<div class="more">+{{ d.more }} more</div>{% endif %}
</div>{% endfor %}
</body></html>""", autoescape=True)


def build_days(ics_url):
    resp = requests.get(ics_url, timeout=15)
    resp.raise_for_status()
    cal = icalendar.Calendar.from_ical(resp.content)

    now = dt.datetime.now(TZ) if TZ else dt.datetime.now().astimezone()
    today = now.date()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=DAYS)
    # expands recurring events into the actual occurrences in this window
    events = recurring_ical_events.of(cal).between(start, end)

    days = [{"date": today + dt.timedelta(days=i), "events": []} for i in range(DAYS)]

    for ev in events:
        s = ev.decoded("DTSTART")
        e = ev.decoded("DTEND", s)
        all_day = not isinstance(s, dt.datetime)
        if all_day:
            s_date, e_date = s, e - dt.timedelta(days=1)  # DTEND is exclusive
            sort_key = dt.time.min
            time_str = ""
        else:
            s, e = s.astimezone(TZ), e.astimezone(TZ)
            s_date, e_date = s.date(), e.date()
            if e > s and e.time() == dt.time.min:  # ends exactly at midnight
                e_date -= dt.timedelta(days=1)
            sort_key = s.time()
            time_str = s.strftime("%-I:%M%p").lower()
        e_date = max(e_date, s_date)

        item = {
            "title": str(ev.get("SUMMARY", "(no title)")),
            "all_day": all_day,
            "time": time_str,
            "sort": (not all_day, sort_key),
        }
        for d in days:
            if s_date <= d["date"] <= e_date:
                d["events"].append(item)

    for d in days:
        d["events"].sort(key=lambda x: x["sort"])
        d["more"] = max(0, len(d["events"]) - MAX_PER_DAY)
        d["events"] = d["events"][:MAX_PER_DAY]
        d["label"] = d["date"].strftime("%a %-d")
        d["today"] = d["date"] == today
    return days


def render_image(ics_url):
    """Return the calendar as a 1-bit 800x480 PIL image (cached, thread-safe)."""
    with _lock:
        return _render_image(ics_url)


def _render_image(ics_url):
    hit = _cache.get(ics_url)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]

    html = PAGE.render(days=build_days(ics_url))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 480})
        page.set_content(html)
        png = page.screenshot()
        browser.close()

    # hard threshold (no dithering) keeps text crisp on a B&W panel
    img = (Image.open(io.BytesIO(png)).convert("L")
           .point(lambda v: 255 if v > 140 else 0).convert("1"))
    _cache[ics_url] = (time.time(), img)
    return img


def render(ics_url, fmt="PNG"):
    """Same image as bytes (PNG or BMP)."""
    buf = io.BytesIO()
    render_image(ics_url).save(buf, fmt)
    return buf.getvalue()


if __name__ == "__main__":
    # quick test: ICS_URL=... python calendar_render.py  -> writes preview.png
    with open("preview.png", "wb") as f:
        f.write(render(os.environ["ICS_URL"]))
    print("wrote preview.png")