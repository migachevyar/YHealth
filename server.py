import os
import json
import threading
import hashlib
import hmac
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

USER_DATA = {}
DATA_LOCK = threading.Lock()


def verify_telegram_data(init_data: str):
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        hash_val = parsed.get("hash", [""])[0]
        if not hash_val:
            return None

        parts = [f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"]
        data_check_string = "\n".join(parts)

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed, hash_val):
            return None

        user = json.loads(parsed.get("user", ["{}"])[0])
        return user.get("id")

    except Exception:
        return None


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        try:
            with open(path, "rb") as f:
                content = f.read()

            mime = {
                "html": "text/html; charset=utf-8",
                "js": "application/javascript",
                "css": "text/css",
                "json": "application/json",
                "png": "image/png",
                "svg": "image/svg+xml",
            }.get(path.rsplit(".", 1)[-1].lower(), "application/octet-stream")

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)

        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _uid(self):
        return str(verify_telegram_data(self.headers.get("X-Init-Data", "")) or "")

    def _ensure_user(self, uid):
        if uid not in USER_DATA:
            USER_DATA[uid] = {
                "days": {},
                "weights": {},
                "vit_state": {},
                "profile": None
            }

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path.startswith("/api/"):
            uid = self._uid()
            if not uid:
                return self._json({"error": "unauthorized"}, 401)

            with DATA_LOCK:
                self._ensure_user(uid)
                udata = USER_DATA[uid]

            if path == "/api/data":
                return self._json({
                    "days": udata.get("days", {}),
                    "weights": udata.get("weights", {}),
                    "vit_state": udata.get("vit_state", {}),
                    "profile": udata.get("profile"),
                })

            return self._json({"error": "not found"}, 404)

        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")

        if path in ("/", ""):
            return self._file(os.path.join(base, "index.html"))

        fp = os.path.join(base, path.lstrip("/"))
        if os.path.isfile(fp):
            return self._file(fp)

        return self._file(os.path.join(base, "index.html"))

    def do_POST(self):
        path = urlparse(self.path).path

        if not path.startswith("/api/"):
            self.send_response(404)
            self.end_headers()
            return

        uid = self._uid()
        if not uid:
            return self._json({"error": "unauthorized"}, 401)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(body)
        except Exception:
            return self._json({"error": "invalid json"}, 400)

        with DATA_LOCK:
            self._ensure_user(uid)

            if path == "/api/day":
                date, data = payload.get("date"), payload.get("data")
                if date and data is not None:
                    USER_DATA[uid]["days"][date] = data
                return self._json({"ok": True})

            if path == "/api/weight":
                date, value = payload.get("date"), payload.get("value")
                if date and value is not None:
                    USER_DATA[uid]["weights"][date] = value
                return self._json({"ok": True})

            if path == "/api/vit_state":
                state = payload.get("state")
                if state is not None:
                    USER_DATA[uid]["vit_state"] = state
                return self._json({"ok": True})

            if path == "/api/profile":
                profile = payload.get("profile")
                if profile is not None:
                    USER_DATA[uid]["profile"] = profile
                return self._json({"ok": True})

        return self._json({"error": "not found"}, 404)


def run():
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), AppHandler)
    logger.info(f"Server started on port {port}")
    httpd.serve_forever()


def start_server():
    threading.Thread(target=run, daemon=True).start()