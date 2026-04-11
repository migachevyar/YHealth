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
        data_check_parts = []
        for key, vals in sorted(parsed.items()):
            if key != "hash":
                data_check_parts.append(f"{key}={vals[0]}")
        data_check_string = "\n".join(data_check_parts)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val):
            return None
        user_str = parsed.get("user", ["{}"])[0]
        user = json.loads(user_str)
        return user.get("id")
    except Exception:
        return None


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        try:
            with open(path, "rb") as f:
                content = f.read()
            ext = path.rsplit(".", 1)[-1].lower()
            mime = {
                "html": "text/html", "js": "application/javascript",
                "css": "text/css", "json": "application/json",
                "png": "image/png", "svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _get_user_id(self):
        init_data = self.headers.get("X-Init-Data", "")
        if not init_data:
            return None
        return verify_telegram_data(init_data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            uid = str(self._get_user_id() or "")
            if not uid:
                return self._send_json({"error": "unauthorized"}, 401)
            with DATA_LOCK:
                udata = USER_DATA.get(uid, {})
            if path == "/api/data":
                return self._send_json({
                    "days": udata.get("days", {}),
                    "weights": udata.get("weights", {}),
                    "vit_state": udata.get("vit_state", {}),
                })
            return self._send_json({"error": "not found"}, 404)

        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
        if path in ("/", ""):
            return self._send_file(os.path.join(base, "index.html"))
        fp = os.path.join(base, path.lstrip("/"))
        if os.path.isfile(fp):
            return self._send_file(fp)
        return self._send_file(os.path.join(base, "index.html"))

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self.send_response(404); self.end_headers(); return

        uid = str(self._get_user_id() or "")
        if not uid:
            return self._send_json({"error": "unauthorized"}, 401)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except Exception:
            return self._send_json({"error": "invalid json"}, 400)

        with DATA_LOCK:
            if uid not in USER_DATA:
                USER_DATA[uid] = {"days": {}, "weights": {}, "vit_state": {}}
            if path == "/api/day":
                date = payload.get("date")
                data = payload.get("data")
                if date and data is not None:
                    USER_DATA[uid]["days"][date] = data
                return self._send_json({"ok": True})
            if path == "/api/weight":
                date = payload.get("date")
                value = payload.get("value")
                if date and value is not None:
                    USER_DATA[uid]["weights"][date] = value
                return self._send_json({"ok": True})
            if path == "/api/vit_state":
                state = payload.get("state")
                if state is not None:
                    USER_DATA[uid]["vit_state"] = state
                return self._send_json({"ok": True})

        return self._send_json({"error": "not found"}, 404)


def run():
    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), AppHandler)
    logger.info(f"Server started on port {port}")
    httpd.serve_forever()


def start_server():
    t = threading.Thread(target=run, daemon=True)
    t.start()
