import io, os, hashlib, datetime as dt
import requests, icalendar, recurring_ical_events
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, Response, request

ICS_URL = os.environ["ICS_URL"]
FONT = os.environ.get("FONT", "/System/Library/Fonts/Supplemental/Arial.ttf")
W, H = 800, 480
app = Flask(__name__)

def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default(size)

def load_events(days=7):
    r = requests.get(ICS_URL, timeout=15)
    r.raise_for_status()
    cal = icalendar.Calendar.from_ical(r.content)
    start = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    events = recurring_ical_events.of(cal).between(start, start + dt.timedelta(days=days))
    out = []
    for e in events:
        s = e["DTSTART"].dt
        allday = not isinstance(s, dt.datetime)
        s = dt.datetime.combine(s, dt.time.min) if allday else s
        out.append((s.astimezone(), allday, str(e.get("SUMMARY", "(no title)"))))
    return sorted(out, key=lambda x: (x[0], not x[1]))

def render():
    img = Image.new("1", (W, H), 1)  # 1 = white
    d = ImageDraw.Draw(img)
    now = dt.datetime.now().astimezone()
    d.text((20, 12), now.strftime("%A, %B %-d"), font=font(40), fill=0)
    d.line((20, 62, W - 20, 62), fill=0, width=2)

    y, last_day = 76, None
    for start, allday, title in load_events():
        if start.date() != last_day:
            last_day = start.date()
            d.text((20, y), start.strftime("%a %b %-d").upper(), font=font(20), fill=0)
            y += 28
        label = "All day" if allday else start.strftime("%-I:%M %p")
        d.text((40, y), label, font=font(22), fill=0)
        d.text((170, y), title[:45], font=font(22), fill=0)
        y += 30
        if y > H - 30:
            break
    return img

@app.get("/frame.png")           # preview in your browser
def png():
    buf = io.BytesIO()
    render().save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png")

@app.get("/frame.bin")           # what the ESP32 fetches: 48,000 bytes
def frame():
    data = render().tobytes()
    etag = hashlib.md5(data).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)
    return Response(data, mimetype="application/octet-stream", headers={"ETag": etag})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)