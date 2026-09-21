"""Short-lived, LAN-only upload sessions for the desktop application.

The server intentionally accepts one raw image per HTTP request instead of a
multipart batch.  Mobile browsers upload the selected files sequentially, so
the desktop process can stream each request directly to disk without holding a
whole batch in memory.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import secrets
import shutil
import socket
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

ALLOWED_SUFFIXES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MIME_SUFFIXES = {value: key for key, value in ALLOWED_SUFFIXES.items()}
MAX_FILENAME_LENGTH = 160


@dataclass(frozen=True)
class UploadLimits:
    """Configurable safety limits for one mobile upload session."""

    max_file_bytes: int = 50 * 1024 * 1024
    max_session_bytes: int = 1024 * 1024 * 1024
    max_files_per_session: int = 200
    session_ttl_seconds: int = 15 * 60


class UploadSessionError(RuntimeError):
    """Base error for a session that cannot be started or used."""


class LanUnavailableError(UploadSessionError):
    """Raised when no usable private IPv4 interface is available."""


class UploadRequestError(UploadSessionError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def find_lan_ipv4() -> str:
    """Return a private, non-loopback IPv4 address for the current machine."""

    candidates: set[str] = set()
    for hostname in (socket.gethostname(), socket.getfqdn()):
        try:
            infos = socket.getaddrinfo(hostname, 0, socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            continue
        candidates.update(str(info[4][0]) for info in infos)

    private: list[str] = []
    for value in candidates:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version == 4 and address.is_private and not address.is_loopback:
            private.append(value)
    if not private:
        raise LanUnavailableError(
            "ไม่พบเครือข่าย LAN ที่ใช้งานได้\n"
            "ให้เชื่อมต่อคอมพิวเตอร์และมือถือกับ Wi‑Fi/LAN เดียวกันก่อนเปิด QR"
        )
    return sorted(private, key=lambda value: (value.startswith("169.254."), value))[0]


def sanitize_filename(filename: str, suffix: str) -> str:
    """Keep a readable basename while preventing path traversal and control chars."""

    normalized = unicodedata.normalize("NFKC", filename or "")
    normalized = Path(normalized).name
    normalized = re.sub(r"[\x00-\x1f\x7f/\\]+", "_", normalized).strip(" .")
    if not normalized:
        normalized = f"upload-{uuid4().hex[:12]}{suffix}"
    current_suffix = Path(normalized).suffix.lower()
    if not current_suffix:
        normalized += suffix
    return normalized[:MAX_FILENAME_LENGTH]


def _image_signature_matches(path: Path, suffix: str) -> bool:
    with path.open("rb") as source:
        prefix = source.read(16)
    if suffix in {".jpg", ".jpeg"}:
        return prefix.startswith(b"\xff\xd8\xff")
    return prefix.startswith(b"\x89PNG\r\n\x1a\n")


def _upload_page(session: "UploadSession") -> bytes:
    purpose = "เฉลย" if session.purpose == "key" else "กระดาษคำตอบนักเรียน"
    multiple = " multiple" if session.purpose == "student" else ""
    max_files = session.max_files
    max_mb = session.limits.max_file_bytes // (1024 * 1024)
    title = html.escape(f"เพิ่ม{purpose}ผ่านมือถือ")
    body = f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  body {{ margin:0; background:#f6f8fb; color:#172033; }}
  main {{ max-width:620px; margin:0 auto; padding:28px 18px 48px; }}
  h1 {{ font-size:1.65rem; margin:0 0 10px; }}
  p {{ line-height:1.55; }}
  .notice {{ background:#eaf3ff; border:1px solid #bfd8f5; border-radius:14px; padding:14px 16px; }}
  .upload {{ display:block; width:100%; margin:28px 0 12px; padding:18px; border:0; border-radius:14px;
    background:#0969e8; color:#fff; font-size:1.15rem; font-weight:700; }}
  .hint {{ color:#526074; font-size:.95rem; }}
  #status {{ white-space:pre-wrap; min-height:2.4em; margin-top:20px; font-weight:600; }}
  #file {{ display:none; }}
</style></head><body><main>
<h1>{title}</h1>
<div class="notice">มือถือและคอมต้องอยู่เครือข่ายเดียวกัน<br>
เลือกจากคลังรูป ถ่ายภาพ หรือเลือกไฟล์ ตามความสามารถของเบราว์เซอร์</div>
<input id="file" type="file" accept="image/jpeg,image/png,.jpg,.jpeg,.png"{multiple}>
<button class="upload" id="choose">เลือกภาพและอัปโหลด</button>
<p class="hint">รับได้สูงสุด {max_files} ภาพ · ไม่เกิน {max_mb} MB ต่อภาพ · ระบบจะส่งทีละภาพ</p>
<div id="status">รอเลือกภาพ</div>
<script>
const picker = document.getElementById('file');
const choose = document.getElementById('choose');
const status = document.getElementById('status');
const endpoint = {json.dumps(session.endpoint_path)};
choose.onclick = () => picker.click();
picker.onchange = async () => {{
  const files = Array.from(picker.files || []);
  if (!files.length) return;
  choose.disabled = true;
  let completed = 0;
  for (const file of files) {{
    status.textContent = `กำลังส่ง ${{completed + 1}}/${{files.length}}: ${{file.name}}`;
    try {{
      const result = await new Promise((resolve, reject) => {{
        const request = new XMLHttpRequest();
        request.open('POST', endpoint);
        request.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
        request.setRequestHeader('X-File-Name', encodeURIComponent(file.name));
        request.onload = () => {{
          let payload = {{}};
          try {{ payload = JSON.parse(request.responseText); }} catch (_) {{}}
          if (request.status >= 200 && request.status < 300) resolve(payload);
          else reject(new Error(payload.error || 'อัปโหลดไม่สำเร็จ'));
        }};
        request.onerror = () => reject(new Error('เชื่อมต่อคอมพิวเตอร์ไม่ได้'));
        request.send(file);
      }});
      completed += 1;
      status.textContent = `รับแล้ว ${{completed}}/${{files.length}} ภาพ`;
    }} catch (error) {{
      status.textContent = `ส่งไม่สำเร็จ: ${{error.message}}`;
      break;
    }}
  }}
  choose.disabled = false;
  picker.value = '';
}};
</script></main></body></html>"""
    return body.encode("utf-8")


class _UploadHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _UploadHandler(BaseHTTPRequestHandler):
    server: _UploadHTTPServer

    def log_message(self, _format: str, *_args) -> None:
        return

    @property
    def session(self) -> "UploadSession":
        return self.server.session  # type: ignore[attr-defined]

    def _path_matches(self) -> bool:
        return urlsplit(self.path).path == self.session.endpoint_path

    def _send(self, status: HTTPStatus, payload: dict | bytes, content_type: str) -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        self._send(status, payload, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if not self._path_matches():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "ไม่พบลิงก์อัปโหลดนี้"})
            return
        if not self.session.is_active():
            self._send_json(HTTPStatus.GONE, {"error": "session หมดอายุหรือถูกปิดแล้ว"})
            return
        self._send(HTTPStatus.OK, _upload_page(self.session), "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if not self._path_matches():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "ไม่พบลิงก์อัปโหลดนี้"})
            return
        try:
            path = self._receive_one_file()
        except UploadRequestError as error:
            self._send_json(error.status, {"error": str(error)})
            return
        self._send_json(
            HTTPStatus.CREATED,
            {"ok": True, "filename": path.name, "message": "รับภาพแล้ว"},
        )

    def _receive_one_file(self) -> Path:
        if not self.session.is_active():
            raise UploadRequestError("session หมดอายุหรือถูกปิดแล้ว", HTTPStatus.GONE)
        raw_length = self.headers.get("Content-Length")
        if not raw_length:
            raise UploadRequestError(
                "เบราว์เซอร์ไม่ได้ระบุขนาดไฟล์ กรุณาลองเลือกภาพใหม่", HTTPStatus.LENGTH_REQUIRED
            )
        try:
            content_length = int(raw_length)
        except ValueError as error:
            raise UploadRequestError("ขนาดไฟล์ไม่ถูกต้อง") from error
        if content_length <= 0:
            raise UploadRequestError("ไฟล์ว่างเปล่า")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        raw_name = unquote(self.headers.get("X-File-Name", ""))
        suffix = Path(raw_name).suffix.lower()
        if not suffix and content_type in MIME_SUFFIXES:
            suffix = MIME_SUFFIXES[content_type]
        if suffix not in ALLOWED_SUFFIXES:
            raise UploadRequestError(
                "รองรับเฉพาะไฟล์ JPG, JPEG หรือ PNG", HTTPStatus.UNSUPPORTED_MEDIA_TYPE
            )
        expected_type = ALLOWED_SUFFIXES[suffix]
        if content_type not in {"", "application/octet-stream", expected_type}:
            raise UploadRequestError("ชนิดไฟล์ไม่ตรงกับนามสกุลไฟล์", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        if content_length > self.session.limits.max_file_bytes:
            raise UploadRequestError(
                f"ไฟล์ใหญ่เกิน {self.session.limits.max_file_bytes // (1024 * 1024)} MB ต่อภาพ",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        self.session.reserve(content_length)
        upload_dir = Path(tempfile.mkdtemp(dir=self.session.staging_dir, prefix=f"{uuid4().hex}-"))
        destination = upload_dir / sanitize_filename(raw_name, suffix)
        try:
            remaining = content_length
            with destination.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(64 * 1024, remaining))
                    if not chunk:
                        raise UploadRequestError("อัปโหลดไม่ครบ กรุณาลองใหม่")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
            if not _image_signature_matches(destination, suffix):
                raise UploadRequestError("ไฟล์ไม่ใช่ภาพ JPG/PNG ที่ถูกต้อง", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            self.session.accept(destination, content_length)
            return destination
        except Exception:
            self.session.release(content_length)
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise


class UploadSession(QObject):
    """A revocable one-exam upload session backed by a local HTTP server."""

    files_received = Signal(list)
    status_changed = Signal(str)

    def __init__(
        self,
        purpose: str,
        exam_id: str,
        room_id: str | None = None,
        limits: UploadLimits | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        if purpose not in {"key", "student"}:
            raise ValueError("ประเภท upload ไม่ถูกต้อง")
        self.purpose = purpose
        self.exam_id = exam_id
        self.room_id = room_id
        self.limits = limits or UploadLimits()
        self.max_files = 1 if purpose == "key" else self.limits.max_files_per_session
        self.token = secrets.token_urlsafe(32)
        self.endpoint_path = f"/upload/{self.token}"
        self._lock = threading.RLock()
        self._active = False
        self._expires_at = 0.0
        self._accepted_bytes = 0
        self._accepted_files = 0
        self._reserved_bytes = 0
        self._reserved_files = 0
        self._server: _UploadHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._url = ""
        self.staging_dir = Path(tempfile.mkdtemp(prefix="exam-grader-upload-"))

    @property
    def url(self) -> str:
        return self._url

    @property
    def expires_at(self) -> float:
        return self._expires_at

    def start(self, host: str | None = None, port: int = 0) -> str:
        if self.is_active():
            return self._url
        bind_host = host or find_lan_ipv4()
        try:
            server = _UploadHTTPServer((bind_host, port), _UploadHandler)
        except OSError as error:
            raise UploadSessionError(
                "เปิดช่องรับภาพไม่ได้ อาจถูก firewall บล็อกหรือพอร์ตไม่พร้อมใช้งาน"
            ) from error
        server.session = self  # type: ignore[attr-defined]
        self._server = server
        self._expires_at = time.time() + self.limits.session_ttl_seconds
        self._active = True
        self._url = f"http://{bind_host}:{server.server_port}{self.endpoint_path}"
        self._server_thread = threading.Thread(
            target=server.serve_forever,
            name="exam-grader-upload-server",
            daemon=True,
        )
        self._server_thread.start()
        self.status_changed.emit("รอรับภาพ")
        return self._url

    def is_active(self) -> bool:
        expired = False
        with self._lock:
            if self._active and time.time() >= self._expires_at:
                self._active = False
                expired = True
            active = self._active
        if expired:
            self._stop_server()
            self.status_changed.emit("session หมดอายุ")
        return active

    def counts(self) -> tuple[int, int]:
        with self._lock:
            return self._accepted_files, self._accepted_bytes

    def reserve(self, size: int) -> None:
        with self._lock:
            if not self._active or time.time() >= self._expires_at:
                raise UploadRequestError("session หมดอายุหรือถูกปิดแล้ว", HTTPStatus.GONE)
            if self._accepted_files + self._reserved_files >= self.max_files:
                raise UploadRequestError("session นี้รับภาพครบจำนวนที่กำหนดแล้ว", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            if self._accepted_bytes + self._reserved_bytes + size > self.limits.max_session_bytes:
                raise UploadRequestError(
                    f"ขนาดรวมเกิน {self.limits.max_session_bytes // (1024 * 1024 * 1024)} GB ต่อ session",
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
            self._reserved_files += 1
            self._reserved_bytes += size

    def release(self, size: int) -> None:
        with self._lock:
            self._reserved_files = max(0, self._reserved_files - 1)
            self._reserved_bytes = max(0, self._reserved_bytes - size)

    def accept(self, path: Path, size: int) -> None:
        with self._lock:
            self._reserved_files = max(0, self._reserved_files - 1)
            self._reserved_bytes = max(0, self._reserved_bytes - size)
            self._accepted_files += 1
            self._accepted_bytes += size
            count = self._accepted_files
        self.files_received.emit([str(path)])
        self.status_changed.emit(f"รับแล้ว {count} ภาพ")

    def revoke(self, keep_staged: bool = True) -> None:
        with self._lock:
            was_active = self._active
            self._active = False
        if was_active:
            self._stop_server()
            self.status_changed.emit("ปิด session แล้ว")
        if not keep_staged:
            self.cleanup()

    def cleanup(self) -> None:
        self.revoke(keep_staged=True)
        shutil.rmtree(self.staging_dir, ignore_errors=True)

    def _stop_server(self) -> None:
        server = self._server
        if server is None:
            return
        self._server = None
        try:
            server.shutdown()
        finally:
            server.server_close()
        thread = self._server_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
