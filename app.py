from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Repostium Downloader",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================
# Folder
# ==========================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)


# ==========================
# Model
# ==========================

class VideoRequest(BaseModel):
    url: str


# ==========================
# Home
# ==========================

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


# ==========================
# Health
# ==========================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# ==========================
# Video Info
# ==========================

@app.post("/info")
def video_info(data: VideoRequest):

    options = {
        "quiet": True,
        "skip_download": True
        # "noplaylist": True dihapus agar bisa membaca isi slide carousel
    }

    try:

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                data.url,
                download=False
            )

        # --- LOGIKA FILTER CAROUSEL / SLIDE INSTAGRAM ---
        if "entries" in info:
            video_entry = None
            for entry in info["entries"]:
                # Lewati foto, cari yang berekstensi mp4 atau punya codec video
                if entry.get("ext") == "mp4" or entry.get("vcodec") not in ["none", None]:
                    video_entry = entry
                    break
            
            if not video_entry:
                raise Exception("Tidak ada video yang ditemukan di postingan ini.")
            
            # Ganti info playlist dengan info spesifik video tersebut
            info = video_entry
        # ------------------------------------------------

        return {
            "success": True,
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count")
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# ==========================
# Download
# ==========================

@app.post("/download")
def download(data: VideoRequest):

    before = set(DOWNLOAD_DIR.glob("*"))

    options = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s")
        # "noplaylist": True dihapus
    }

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            # 1. Ekstrak info tanpa download langsung
            info = ydl.extract_info(
                data.url,
                download=False
            )

            # 2. Filter khusus slide video jika itu adalah carousel
            if "entries" in info:
                video_entry = None
                for entry in info["entries"]:
                    if entry.get("ext") == "mp4" or entry.get("vcodec") not in ["none", None]:
                        video_entry = entry
                        break
                
                if not video_entry:
                    raise Exception("Tidak ada video yang ditemukan di postingan ini.")
                
                info = video_entry
            
            # 3. Download HANYA data video yang sudah difilter di atas
            ydl.process_ie_result(info, download=True)

        after = set(DOWNLOAD_DIR.glob("*"))

        new_files = list(after - before)

        if new_files:

            newest = max(
                new_files,
                key=lambda f: f.stat().st_mtime
            )

        else:

            files = sorted(
                DOWNLOAD_DIR.glob("*"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            if not files:
                raise Exception("File tidak ditemukan")

            newest = files[0]

        return FileResponse(
            path=str(newest),
            filename=newest.name,
            media_type="application/octet-stream"
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
