import os, json, threading, hashlib, hmac, sqlite3, logging, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Queue for notifying bot about profile updates (uid strings)
import queue as _queue
profile_update_queue = _queue.Queue()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_PATH = os.environ.get("DB_PATH", "/app/data/yhealth.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.execute("CREATE TABLE IF NOT EXISTS user_data (uid TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (uid, key))")
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
        DB.execute("INSERT OR REPLACE INTO user_data (uid,key,value) VALUES (?,?,?)", (uid, key, json.dumps(value, ensure_ascii=False)))
        DB.commit()

def verify_tg(init_data):
    if not init_data:
        return None
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        hash_val = parsed.get("hash", [""])[0]
        if not hash_val:
            return None
        parts = [f"{k}={v[0]}" for k, v in sorted(parsed.items()) if k != "hash"]
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret, "\n".join(parts).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val):
            return None
        user = json.loads(parsed.get("user", ["{}"])[0])
        return user.get("id")
    except Exception:
        return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Init-Data")
        webapp_url = os.environ.get("WEBAPP_URL", "")
        self.send_header("Content-Security-Policy",
            f"default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            f"connect-src * data: blob:; "
            f"script-src * 'unsafe-inline' 'unsafe-eval'; "
            f"style-src * 'unsafe-inline'")

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
            # Inject WEBAPP_URL into index.html so fetch works inside Telegram blob context
            if path.endswith("index.html"):
                webapp_url = os.environ.get("WEBAPP_URL", "")
                content = content.replace(b"__WEBAPP_URL__", webapp_url.encode())
            mime = {"html":"text/html;charset=utf-8","js":"application/javascript","css":"text/css","json":"application/json","png":"image/png","svg":"image/svg+xml"}.get(path.rsplit(".",1)[-1].lower(),"application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(content))
            if path.endswith("index.html"):
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Security-Policy",
                    "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                    "connect-src *; script-src * 'unsafe-inline' 'unsafe-eval'; "
                    "style-src * 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")

        # Debug — no auth
        if path == "/api/debug":
            try:
                rows = DB.execute("SELECT uid, key, length(value) as vlen FROM user_data ORDER BY uid, key").fetchall()
                return self._json({"status":"ok","db_path":DB_PATH,"rows":[{"uid":r[0],"key":r[1],"len":r[2]} for r in rows]})
            except Exception as e:
                return self._json({"status":"error","msg":str(e)})

        if path.startswith("/api/"):
            uid = str(verify_tg(self.headers.get("X-Init-Data","")) or "")
            if not uid:
                return self._json({"error":"unauthorized"}, 401)
            if path == "/api/data":
                return self._json({"days":db_get(uid,"days") or {},"weights":db_get(uid,"weights") or [],"profile":db_get(uid,"profile")})
            return self._json({"error":"not found"}, 404)

        fp = os.path.join(base, path.lstrip("/")) if path not in ("/","") else os.path.join(base,"index.html")
        if os.path.isfile(fp):
            return self._file(fp)
        return self._file(os.path.join(base,"index.html"))

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self.send_response(404); self.end_headers(); return

        length = int(self.headers.get("Content-Length",0))
        try:
            payload = json.loads(self.rfile.read(length) if length else b"{}")
        except Exception:
            return self._json({"error":"invalid json"}, 400)

        # Auth: try header first, then payload uid
        uid = str(verify_tg(self.headers.get("X-Init-Data","")) or "")
        if not uid:
            uid = str(payload.get("uid",""))
        if not uid:
            print(f"[AUTH] unauthorized POST {path}", flush=True)
            return self._json({"error":"unauthorized"}, 401)

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
                w = db_get(uid,"weights") or []
                if not isinstance(w,list): w=[]
                w.insert(0,{"date":date,"value":value})
                db_set(uid,"weights",w[:365])
            return self._json({"ok":True})

        if path == "/api/profile":
            profile = payload.get("profile")
            if profile is not None:
                db_set(uid,"profile",profile)
                print(f"[DB] profile saved uid={uid}", flush=True)
                profile_update_queue.put(uid)
            return self._json({"ok":True})

        if path == "/api/feedback":
            text = payload.get("text","")
            name = payload.get("name","")
            fid = os.environ.get("FEEDBACK_CHAT_ID","")
            if fid and text:
                def _send():
                    try:
                        tok = os.environ.get("BOT_TOKEN","")
                        data = json.dumps({"chat_id":fid,"text":f"💬 {name}:\n\n{text}"}).encode()
                        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, headers={"Content-Type":"application/json"})
                        urllib.request.urlopen(req, timeout=5)
                    except Exception as e:
                        print(f"[FEEDBACK] error: {e}", flush=True)
                threading.Thread(target=_send, daemon=True).start()
            return self._json({"ok":True})

        return self._json({"error":"not found"}, 404)

def run():
    port = int(os.environ.get("PORT",8080))
    httpd = HTTPServer(("0.0.0.0",port), Handler)
    print(f"[SERVER] started on port {port}", flush=True)
    httpd.serve_forever()

def start_server():
    threading.Thread(target=run, daemon=True).start()
