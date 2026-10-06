"""
ScribeAR link helper: downloads the audio from a YouTube / TikTok / Instagram / X / any
yt-dlp-supported link and returns it as small 16 kHz mono MP3 for the ScribeAR website.
"""
import os, glob, shutil, subprocess, tempfile, threading, hmac
from flask import Flask, request, jsonify, send_file, after_this_request
import yt_dlp

app = Flask(__name__)
KEY = os.environ.get("HELPER_KEY", "")
MAX_HOURS = float(os.environ.get("MAX_HOURS", "4"))
COOKIES = None
if os.environ.get("YT_COOKIES"):
    COOKIES = os.path.join(tempfile.gettempdir(), "cookies.txt")
    with open(COOKIES, "w") as f:
        f.write(os.environ["YT_COOKIES"])
busy = threading.Semaphore(2)


@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Expose-Headers"] = "X-Title, Content-Length"
    return r


def err(msg, code=400):
    return jsonify(error=msg), code


@app.route("/")
def home():
    return jsonify(ok=True, service="ScribeAR link helper", yt_dlp=yt_dlp.version.__version__)


@app.route("/audio", methods=["GET", "OPTIONS"])
def audio():
    if request.method == "OPTIONS":
        return "", 204
    if KEY and not hmac.compare_digest(request.args.get("key", ""), KEY):
        return err("Wrong helper key. Check the key in ScribeAR settings.", 403)
    url = request.args.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        return err("Missing or invalid link.")
    if not busy.acquire(timeout=600):
        return err("Helper is busy, try again in a minute.", 503)
    tmp = tempfile.mkdtemp()
    try:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmp, "src.%(ext)s"),
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "socket_timeout": 30, "retries": 3,
            "match_filter": yt_dlp.utils.match_filter_func(f"duration < {int(MAX_HOURS*3600)} | !duration"),
        }
        if COOKIES:
            opts["cookiefile"] = COOKIES
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
        src = [p for p in glob.glob(os.path.join(tmp, "src.*")) if not p.endswith(".part")]
        if not src:
            return err("Couldn't download that link (too long, private, or not a video).")
        out = os.path.join(tmp, "audio.mp3")
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", src[0],
                        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", out], check=True)
        title = (info or {}).get("title") or "audio"

        @after_this_request
        def cleanup(r):
            shutil.rmtree(tmp, ignore_errors=True)
            return r

        r = send_file(out, mimetype="audio/mpeg", as_attachment=False)
        r.headers["X-Title"] = title.encode("ascii", "xmlcharrefreplace").decode()
        return r
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        m = str(e)
        if "Sign in to confirm" in m or "bot" in m.lower():
            return err("YouTube is blocking the helper as a bot. Add YT_COOKIES (see setup notes) or try again later.", 502)
        return err("Download failed: " + m.replace("ERROR: ", "")[:300], 502)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return err("Helper error: " + str(e)[:300], 500)
    finally:
        busy.release()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
