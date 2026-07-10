"""SPEC-070: Mirror Screenshot Capture service.
Takes periodic screenshots and POSTs JPEG frames to a collector adt_center.
Runs in a background thread; thread-safe start/stop/status interface.
"""
import io
import time
import threading
import logging

log = logging.getLogger(__name__)

try:
    import mss
    import mss.tools
    _MSS_OK = True
except ImportError:
    _MSS_OK = False
    log.warning("mss not installed — screen capture unavailable. pip install mss")

try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


class MirrorScreenshotCapture:
    """Captures the primary monitor every INTERVAL seconds and POSTs JPEG to collector_url."""

    INTERVAL = 2.0       # seconds between frames
    JPEG_QUALITY = 55    # lower = smaller frames, less bandwidth
    MAX_WIDTH = 1280     # downscale if wider

    def __init__(self, collector_url: str, peer_id: str, session_id: str):
        self.collector_url = collector_url.rstrip("/")
        self.peer_id = peer_id
        self.session_id = session_id
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._frames_sent = 0
        self._last_sent_at: float | None = None
        self._last_error: str | None = None
        self._running = False

    def start(self):
        if self._running:
            return
        if not _MSS_OK:
            raise RuntimeError("mss not installed — cannot capture screen")
        self._stop_evt.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mirror-capture")
        self._thread.start()
        log.info("MirrorScreenshotCapture started → %s (peer=%s)", self.collector_url, self.peer_id)

    def stop(self):
        self._stop_evt.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("MirrorScreenshotCapture stopped")

    def status(self) -> dict:
        return {
            "running": self._running and bool(self._thread and self._thread.is_alive()),
            "frames_sent": self._frames_sent,
            "last_sent_at": self._last_sent_at,
            "last_error": self._last_error,
        }

    def _loop(self):
        import urllib.request
        while not self._stop_evt.is_set():
            try:
                jpeg = self._capture_jpeg()
                self._post_frame(jpeg, urllib.request)
            except Exception as exc:
                self._last_error = str(exc)[:200]
                log.debug("Capture error: %s", exc)
            self._stop_evt.wait(self.INTERVAL)

    def _capture_jpeg(self) -> bytes:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            shot = sct.grab(monitor)

        if _PIL_OK:
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            w, h = img.size
            if w > self.MAX_WIDTH:
                ratio = self.MAX_WIDTH / w
                img = img.resize((self.MAX_WIDTH, int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self.JPEG_QUALITY, optimize=True)
            return buf.getvalue()
        else:
            # Fallback: use mss's built-in PNG → convert to JPEG via stdlib (no PIL)
            # mss can output PNG; we serve it as JPEG header with PNG body (monitor
            # will still show it since browsers handle both, just less efficient).
            buf = io.BytesIO()
            mss.tools.to_png(shot.rgb, shot.size, output=buf)
            return buf.getvalue()

    def _post_frame(self, jpeg: bytes, urllib_request):
        url = f"{self.collector_url}/api/mirror/frame"
        req = urllib_request.Request(url, data=jpeg, method="POST")
        req.add_header("Content-Type", "image/jpeg")
        req.add_header("X-Peer-Id", self.peer_id)
        req.add_header("X-Session-Id", self.session_id)
        req.add_header("X-Frame-Ts", str(time.time()))
        with urllib_request.urlopen(req, timeout=5) as resp:
            resp.read()
        self._frames_sent += 1
        self._last_sent_at = time.time()
        self._last_error = None
