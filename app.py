import ipaddress
import os
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = Path(os.getenv("TEMP_DIR", str(BASE_DIR / "tmp")))
TEMP_DIR.mkdir(exist_ok=True, parents=True)
MAX_CONCURRENT_DOWNLOADS = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")))
DEFAULT_HOST = os.getenv("HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("PORT", "8000"))
API_KEY = os.getenv("API_KEY")
MAX_FILE_AGE_SECONDS = int(os.getenv("MAX_FILE_AGE_SECONDS", str(60 * 60 * 24)))
ALLOW_PRIVATE_URLS = os.getenv("ALLOW_PRIVATE_URLS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="DL Repostium", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)


class VideoRequest(BaseModel):
    url: str = Field(..., min_length=5)
    format_id: Optional[str] = None
    mode: str = "video"
    audio_quality: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url_field(cls, value: str) -> str:
        return validate_url(value)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"video", "audio"}:
            raise ValueError("Mode must be 'video' or 'audio'.")
        return normalized


class BulkVideoRequest(BaseModel):
    urls: List[str] = Field(..., min_items=1, max_items=20)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: List[str]) -> List[str]:
        return [validate_url(item) for item in value]


def validate_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("URL is required.")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")
    if not parsed.netloc:
        raise ValueError("A valid hostname is required.")

    host = parsed.hostname
    if not host:
        raise ValueError("URL hostname is invalid.")

    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed.")

    if not ALLOW_PRIVATE_URLS:
        try:
            for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
                sockaddr = info[4]
                if not sockaddr:
                    continue
                ip_value = ipaddress.ip_address(sockaddr[0])
                if (
                    ip_value.is_private
                    or ip_value.is_loopback
                    or ip_value.is_link_local
                    or ip_value.is_multicast
                    or ip_value.is_reserved
                    or ip_value.is_unspecified
                ):
                    raise ValueError("Private and local network URLs are not allowed.")
        except socket.gaierror:
            pass

    return url


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "", name or "download")
    cleaned = cleaned.strip() or "download"
    return cleaned[:120]


def now_timestamp() -> float:
    return time.time()


def cleanup_old_temp_files() -> None:
    now = now_timestamp()
    for item in TEMP_DIR.iterdir():
        try:
            if item.is_dir() and (now - item.stat().st_mtime) > MAX_FILE_AGE_SECONDS:
                for nested in sorted(item.rglob("*"), reverse=True):
                    if nested.is_file() or nested.is_symlink():
                        nested.unlink(missing_ok=True)
                for nested in sorted(item.rglob("*"), reverse=True):
                    if nested.is_dir():
                        nested.rmdir()
                item.rmdir(missing_ok=True)
            elif item.is_file() and (now - item.stat().st_mtime) > MAX_FILE_AGE_SECONDS:
                item.unlink(missing_ok=True)
        except OSError:
            continue


async def enforce_api_key(request: Request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        provided = request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "", 1)
        if provided != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key."})
    return await call_next(request)


app.middleware("http")(enforce_api_key)


def get_platform_name(info: Dict[str, Any]) -> str:
    if not info:
        return "Unknown"
    platform = info.get("extractor") or info.get("extractor_key") or info.get("webpage_url") or "Unknown"
    return platform.split(":")[-1].split(".")[0].title() if platform else "Unknown"


def normalize_video_info(raw_info: Dict[str, Any]) -> Dict[str, Any]:
    if not raw_info:
        return {}

    info = dict(raw_info)
    if isinstance(info.get("entries"), list):
        entries = [entry for entry in info["entries"] if isinstance(entry, dict)]
        if entries:
            candidate = next(
                (
                    entry
                    for entry in entries
                    if entry.get("ext") == "mp4"
                    or entry.get("vcodec") not in [None, "none"]
                    or entry.get("duration") is not None
                ),
                entries[0],
            )
            info = dict(candidate)

    formats = []
    for entry in info.get("formats", []) or []:
        if not isinstance(entry, dict):
            continue
        formats.append(
            {
                "format_id": entry.get("format_id"),
                "ext": entry.get("ext"),
                "format_note": entry.get("format_note"),
                "quality": entry.get("quality"),
                "vcodec": entry.get("vcodec"),
                "acodec": entry.get("acodec"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "fps": entry.get("fps"),
                "tbr": entry.get("tbr"),
                "filesize": entry.get("filesize"),
                "filesize_approx": entry.get("filesize_approx"),
                "audio_ext": entry.get("audio_ext"),
                "video_ext": entry.get("video_ext"),
            }
        )

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel") or "Unknown",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail")
        or next(
            (
                thumbnail.get("url")
                for thumbnail in reversed(info.get("thumbnails") or [])
                if isinstance(thumbnail, dict) and thumbnail.get("url")
            ),
            None,
        ),
        "webpage_url": info.get("webpage_url") or info.get("url"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "platform": get_platform_name(info),
        "formats": formats or [],
        "ext": info.get("ext"),
    }


def get_yt_info(url: str, playlist: bool = False) -> Dict[str, Any]:
    ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": not playlist,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(url, download=False)
    return normalize_video_info(info)


def _find_downloaded_file(dir_path: Path) -> Optional[Path]:
    candidates = sorted(dir_path.rglob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in {".mp4", ".m4a", ".mp3", ".webm", ".mkv", ".aac", ".mov", ".avi"}:
            return candidate
    return None


def _generate_job_record(job_id: str, url: str, mode: str) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "url": url,
        "mode": mode,
        "status": "queued",
        "created_at": now_timestamp(),
        "updated_at": now_timestamp(),
        "progress": 0,
        "filename": None,
        "file_path": None,
        "error": None,
        "size_bytes": 0,
    }


def download_worker(job_id: str, url: str, mode: str, format_id: Optional[str], audio_quality: Optional[str]) -> None:
    record = jobs.get(job_id)
    if not record:
        return

    try:
        record["status"] = "running"
        record["updated_at"] = now_timestamp()
        target_dir = TEMP_DIR / f"job_{job_id}"
        target_dir.mkdir(exist_ok=True, parents=True)

        ydl_options: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "restrictfilenames": True,
            "socket_timeout": 30,
            "paths": {"home": str(target_dir)},
            "outtmpl": "%(title)s.%(ext)s",
            "format": "bestaudio/best" if mode == "audio" else (format_id or "bestvideo+bestaudio/best"),
        }

        if mode == "audio":
            ydl_options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_quality or "0",
            }]
            ydl_options["format"] = "bestaudio/best"
        else:
            ydl_options["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            ydl.download([url])

        downloaded = _find_downloaded_file(target_dir)
        if downloaded is None:
            raise FileNotFoundError("No file was produced during download.")

        record["status"] = "completed"
        record["filename"] = sanitize_filename(downloaded.name)
        record["file_path"] = str(downloaded)
        record["size_bytes"] = downloaded.stat().st_size
        record["progress"] = 100
        record["updated_at"] = now_timestamp()

    except Exception as exc:  # pragma: no cover - runtime path only
        record["status"] = "failed"
        record["error"] = str(exc)
        record["progress"] = 0
        record["updated_at"] = now_timestamp()
    finally:
        cleanup_old_temp_files()


@app.on_event("startup")
def startup_events() -> None:
    cleanup_old_temp_files()


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def legacy_health():
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "DL Repostium",
        "max_concurrent_downloads": MAX_CONCURRENT_DOWNLOADS,
        "temp_dir": str(TEMP_DIR),
    }


@app.post("/api/info")
async def api_info(payload: VideoRequest):
    info = get_yt_info(payload.url, playlist=False)
    if not info:
        raise HTTPException(status_code=404, detail="No media information was returned for that URL.")
    return {"success": True, **info}


@app.post("/api/playlist")
async def api_playlist(payload: VideoRequest):
    info = get_yt_info(payload.url, playlist=True)
    if not info:
        raise HTTPException(status_code=404, detail="No playlist information was returned for that URL.")
    return {"success": True, **info}


@app.post("/api/download")
async def api_download(payload: VideoRequest):
    with jobs_lock:
        active_jobs = sum(1 for job in jobs.values() if job["status"] in {"queued", "running"})
        if active_jobs >= MAX_CONCURRENT_DOWNLOADS:
            raise HTTPException(status_code=429, detail="Download queue limit reached. Please wait for a running task to finish.")

        job_id = uuid.uuid4().hex
        record = _generate_job_record(job_id, payload.url, payload.mode)
        jobs[job_id] = record

    executor.submit(download_worker, job_id, payload.url, payload.mode, payload.format_id, payload.audio_quality)
    return {"success": True, "job_id": job_id, "status": record["status"]}


@app.post("/api/bulk-download")
async def api_bulk_download(payload: BulkVideoRequest):
    results = []
    for url in payload.urls:
        item = VideoRequest(url=url)
        try:
            response = await api_download(item)
            results.append({"url": url, "status": "queued", "job_id": response["job_id"]})
        except HTTPException as exc:
            results.append({"url": url, "status": "failed", "error": exc.detail})
    return {"success": True, "results": results}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    record = jobs.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Unknown job ID.")
    return {"success": True, **record}


@app.get("/api/file/{job_id}")
async def api_file(job_id: str):
    record = jobs.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Unknown job ID.")
    if record["status"] != "completed" or not record.get("file_path"):
        raise HTTPException(status_code=409, detail="The file is not ready yet.")

    file_path = Path(record["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="The requested file no longer exists on the server.")

    def stream_file():
        try:
            with file_path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass
            if job_id in jobs:
                jobs[job_id]["status"] = "served"
                jobs[job_id]["updated_at"] = now_timestamp()

    return StreamingResponse(
        stream_file(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{record["filename"] or "download"}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)
