import os, json, threading, hashlib, hmac, sqlite3, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "/app/data/yhealth.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.execute("""CREATE TABLE IF NOT EXISTS user_data (
        uid TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
        PRIMARY KEY (uid, key))""")
    db.commit()
    return db

DB = get_db()
DB_LOCK = threading.Lock()

def db_get(uid, key):
    with DB_LOCK:
        row = DB.execute("SELECT value FROM user_data WHERE uid=? AND key=?", (uid, key)).fetchone()
        return json.loads(row[0]) if row else None

def db_set(uid, key, value):
    with DB_LOCK:
        DB.execute("INSERT OR REPLACE INTO user_data (uid,key,value) VALUES (?,?,?)",
                   (uid, key, json.dumps(value, ensure_ascii=False)))
        DB.commit()

def verify_tg(init_data):
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        hash_val = parsed.get("hash", [""])[0]
        if not hash_val: return None
        parts = [f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"]
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret, "\n".join(parts).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val): return None
        return json.loads(parsed.get("user", ["{}"])[0]).get("id")
    except: return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self._cors(); self.end_headers(); self.wfile.write(body)

    def _file(self, path):
        try:
            with open(path, "rb") as f: content = f.read()
            mime = {"html":"text/html;charset=utf-8","js":"application/javascript","css":"text/css","json":"application/json","png":"image/png","svg":"image/svg+xml"}.get(path.rsplit(".",1)[-1].lower(),"application/octet-stream")
            self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", len(content)); self.end_headers(); self.wfile.write(content)
        except FileNotFoundError: self.send_response(404); self.end_headers()

    def _uid(self): return str(verify_tg(self.headers.get("X-Init-Data","")) or "")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            uid = self._uid()
            if not uid: return self._json({"error":"unauthorized"},401)
            if path == "/api/data":
                return self._json({
                    "days": db_get(uid,"days") or {},
                    "weights": db_get(uid,"weights") or {},
                    "profile": db_get(uid,"profile"),
                })
            if path.startswith("/api/schedule/"):
                # Bot reads schedule by user_id: GET /api/schedule/123456
                target_uid = path.split("/")[-1]
                sched = db_get(target_uid,"schedule")
                return self._json({"schedule": sched})
            if path == "/api/feedback":
                text = payload.get("text","")
                name = payload.get("name","")
                fid = os.environ.get("FEEDBACK_CHAT_ID","")
                if fid and text:
                    import threading
                    def send_fb():
                    try:
                        import urllib.request
                        tok = os.environ.get("BOT_TOKEN","")
                        msg = f"💬 Замечание от {name}:\n\n{text}"
                        data = json.dumps({"chat_id":fid,"text":msg}).encode()
                        req = urllib.request.Request(
                            f"https://api.telegram.org/bot{tok}/sendMessage",
                            data=data, headers={"Content-Type":"application/json"}
                        )
                        urllib.request.urlopen(req, timeout=5)
                    except: pass
                threading.Thread(target=send_fb, daemon=True).start()
            return self._json({"ok":True})
        return self._json({"error":"not found"},404)
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),"webapp")
        fp = os.path.join(base, path.lstrip("/")) if path not in ("/","") else os.path.join(base,"index.html")
        if os.path.isfile(fp): return self._file(fp)
        return self._file(os.path.join(base,"index.html"))

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"): self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length",0))
        try: payload = json.loads(self.rfile.read(length) if length else b"{}")
        except: return self._json({"error":"invalid json"},400)
        uid = self._uid()
        # For /api/schedule allow uid from payload body (WebApp sends it)
        if not uid and self.path.startswith("/api/schedule"):
            uid = str(payload.get("uid",""))
        if not uid: return self._json({"error":"unauthorized"},401)
        if path == "/api/day":
            date, data = payload.get("date"), payload.get("data")
            if date and data is not None:
                days = db_get(uid,"days") or {}
                days[date] = data
                db_set(uid,"days",days)
            return self._json({"ok":True})
        if path == "/api/weight":
            date, value = payload.get("date"), payload.get("value")
            if date and value is not None:
                weights = db_get(uid,"weights") or {}
                weights[date] = value
                db_set(uid,"weights",weights)
            return self._json({"ok":True})
        if path == "/api/profile":
            profile = payload.get("profile")
            if profile is not None: db_set(uid,"profile",profile)
            return self._json({"ok":True})
        if path == "/api/schedule":
            # Store user's reminder schedule for bot
            schedule = payload.get("schedule")
            if schedule is not None: db_set(uid,"schedule",schedule)
            return self._json({"ok":True})
        if path == "/api/getschedule":
            # Bot reads this to set up reminders
            sched = db_get(uid,"schedule")
            return self._json({"schedule": sched})
        return self._json({"error":"not found"},404)

def run():
    port = int(os.environ.get("PORT",8080))
    httpd = HTTPServer(("0.0.0.0",port), Handler)
    logger.info(f"Server on port {port}")
    httpd.serve_forever()

def start_server():
    threading.Thread(target=run, daemon=True).start()
