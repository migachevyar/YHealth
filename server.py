import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging

logger = logging.getLogger(__name__)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def run():
    port = int(os.environ.get("PORT", 8080))
    original_dir = os.getcwd()
    webapp_dir = os.path.join(original_dir, "webapp")
    os.chdir(webapp_dir)
    httpd = HTTPServer(("0.0.0.0", port), QuietHandler)
    logger.info(f"Mini App server started on port {port}")
    httpd.serve_forever()


def start_server():
    t = threading.Thread(target=run, daemon=True)
    t.start()
