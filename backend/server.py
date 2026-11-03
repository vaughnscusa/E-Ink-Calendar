import hashlib, hmac, os
from flask import Flask, Response, request
from calendar_render import render, render_image

ICS_URL = os.environ["ICS_URL"]
API_TOKEN = os.environ.get("API_TOKEN", "")
app = Flask(__name__)


@app.before_request
def require_token():
    # Every request must carry ?key=<API_TOKEN>. If no token is configured, nothing is served.
    supplied = request.args.get("key", "")
    if not API_TOKEN or not hmac.compare_digest(supplied.encode(), API_TOKEN.encode()):
        return Response("Forbidden", status=403)


@app.get("/frame.png")           # preview in your browser
def png():
    return Response(render(ICS_URL), mimetype="image/png")


@app.get("/frame.bin")           # what the ESP32 fetches: 48,000 bytes
def frame():
    data = render_image(ICS_URL).tobytes()
    etag = hashlib.md5(data).hexdigest()
    if request.headers.get("If-None-Match") == etag:
        return Response(status=304)
    return Response(data, mimetype="application/octet-stream", headers={"ETag": etag})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
