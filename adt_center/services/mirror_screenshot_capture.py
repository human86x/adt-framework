"""SPEC-070: Mirror Screenshot Capture service.
Takes periodic screenshots and POSTs JPEG frames to a collector adt_center.
Runs in a background thread; thread-safe start/stop/status interface.
"""
import io
import os
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


def _discover_display():
    """Find X11 DISPLAY from running processes (WSLg / desktop sessions)."""
    if os.environ.get("DISPLAY"):
        return os.environ["DISPLAY"]
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                env_raw = open(f"/proc/{pid}/environ", "rb").read().decode(errors="replace")
                for entry in env_raw.split("\0"):
                    if entry.startswith("DISPLAY="):
                        d = entry.split("=", 1)[1]
                        if d:
                            return d
            except Exception:
                pass
    except Exception:
        pass
    # WSLg defaults
    for candidate in (":0", ":1"):
        sock = f"/tmp/.X11-unix/X{candidate.lstrip(':')}"
        if os.path.exists(sock):
            return candidate
    return ":0"


class MirrorScreenshotCapture:
    """Captures the primary monitor every INTERVAL seconds and POSTs JPEG to collector_url."""

    INTERVAL = 2.0
    JPEG_QUALITY = 55
    MAX_WIDTH = 1280

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
        # Ensure DISPLAY is set so mss can connect to X11 (critical for WSLg)
        display = _discover_display()
        if display and not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = display
        self._stop_evt.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mirror-capture")
        self._thread.start()
        log.info("MirrorScreenshotCapture started → %s (peer=%s, display=%s)",
                 self.collector_url, self.peer_id, os.environ.get("DISPLAY", "unset"))

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
        # Try PowerShell if no X11 display available (WSL without WSLg)
        if not os.environ.get("DISPLAY"):
            try:
                return self._capture_powershell()
            except Exception as ps_err:
                log.debug("PowerShell capture failed: %s", ps_err)

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
            buf = io.BytesIO()
            mss.tools.to_png(shot.rgb, shot.size, output=buf)
            return buf.getvalue()

    def _capture_powershell(self) -> bytes:
        """WSL fallback: use PowerShell to capture the Windows desktop."""
        import subprocess
        import shutil
        tmp = "/tmp/_adt_mirror_cap.png"
        ps_code = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$s=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$b=New-Object System.Drawing.Bitmap $s.Width,$s.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($b);"
            "$g.CopyFromScreen($s.Location,[System.Drawing.Point]::Empty,$s.Size);"
            f"$b.Save('{tmp}',[System.Drawing.Imaging.ImageFormat]::Png);"
            "$g.Dispose();$b.Dispose()"
        )
        ps_exe = shutil.which("powershell.exe") or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.run([ps_exe, "-Command", ps_code],
                       capture_output=True, timeout=15, check=True)
        with open(tmp, "rb") as f:
            png_data = f.read()
        try:
            os.unlink(tmp)
        except Exception:
            pass
        if _PIL_OK:
            img = Image.open(io.BytesIO(png_data))
            if img.size[0] > self.MAX_WIDTH:
                ratio = self.MAX_WIDTH / img.size[0]
                img = img.resize((self.MAX_WIDTH, int(img.size[1] * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self.JPEG_QUALITY, optimize=True)
            return buf.getvalue()
        return png_data

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
