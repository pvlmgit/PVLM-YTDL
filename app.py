#!/usr/bin/env python3
"""PVLM YouTube Downloader — Web UI."""

import os
import re
import json
import tempfile
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__, static_folder="static", static_url_path="/static")

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' https:; img-src 'self' data: https:; script-src 'self' 'unsafe-inline' 'unsafe-eval';"
    return response

# Use temp directory for downloads (Railway has ephemeral filesystem)
TEMP_DIR = tempfile.mkdtemp()
VIDEO_DIR = os.path.join(TEMP_DIR, "Video")
MUSIC_DIR = os.path.join(TEMP_DIR, "Music")
Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)
Path(MUSIC_DIR).mkdir(parents=True, exist_ok=True)

# Mobile/Android path
MOBILE_VIDEO_DIR = "/storage/emulated/0/Download/PVLM YouTube Downloader/Video"
MOBILE_MUSIC_DIR = "/storage/emulated/0/Download/PVLM YouTube Downloader/Music"
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "download_history.json")

Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)
Path(MUSIC_DIR).mkdir(parents=True, exist_ok=True)

active_downloads = {}
history_lock = threading.Lock()

MEDIA_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3", ".wav", ".flac", ".m4a", ".opus", ".ogg"}


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", flush=True)


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def extract_artist_title(title):
    """Extract artist and title from patterns like 'Song - Artist', 'Song by Artist', 'Song (feat. Artist)'."""
    title_lower = title.lower()
    # Pattern: "Title - Artist" or "Title – Artist"
    m = re.match(r"^(.+?)\s*[-–—]\s*(.+?)$", title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Pattern: "Title by Artist"
    m = re.match(r"^(.+?)\s+by\s+(.+?)$", title_lower)
    if m:
        orig = title
        return orig[:m.end(1)].strip(), orig[m.start(2):m.end(2)].strip()
    # Pattern: "Title (feat. Artist)" or "Title (ft. Artist)"
    m = re.match(r"^(.+?)\s*[\(\[]\s*(?:feat\.?|ft\.?)\s*(.+?)[\)\]]$", title, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title, ""


def scan_existing_files():
    files = []
    for root, dirs, filenames in os.walk(os.path.join(DOWNLOADS_ROOT, "PVLMTube")):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in MEDIA_EXTS:
                stem = os.path.splitext(fname)[0]
                if ext in (".mp3", ".wav", ".flac", ".m4a", ".opus", ".ogg"):
                    fmt = "mp3" if ext == ".mp3" else ext[1:].upper()
                else:
                    fmt = "mp4" if ext == ".mp4" else ext[1:].upper()
                files.append((normalize_title(stem), fmt, stem))
    return files


def find_existing_match(title, existing_files):
    norm = normalize_title(title)
    if not norm:
        return False, None

    new_artist, new_song = extract_artist_title(title)

    for existing_norm, fmt, original_stem in existing_files:
        # Exact normalized match
        ratio = SequenceMatcher(None, norm, existing_norm).ratio()
        if ratio >= 0.80:
            return True, fmt

        # Artist+title extraction match
        if new_artist and new_song:
            exist_artist, exist_song = extract_artist_title(original_stem)
            if exist_artist and exist_song:
                artist_match = SequenceMatcher(None, normalize_title(new_artist), normalize_title(exist_artist)).ratio()
                song_match = SequenceMatcher(None, normalize_title(new_song), normalize_title(exist_song)).ratio()
                if artist_match >= 0.75 and song_match >= 0.75:
                    return True, fmt

    return False, None


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(entry):
    with history_lock:
        history = load_history()
        history.insert(0, entry)
        history = history[:50]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


def get_ydl_opts(mode, quality, audio_format, is_playlist=False):
    opts = {
        "progress_hooks": [],
        "quiet": True,
        "concurrent_fragment_downloads": 4,
        "extractor_retries": 2,
        "socket_timeout": 30,
        "retries": 3,
    }

    base_dir = VIDEO_DIR if mode == "video" else MUSIC_DIR

    if is_playlist:
        opts["outtmpl"] = os.path.join(base_dir, "%(playlist_title)s/%(title)s.%(ext)s")
    else:
        opts["outtmpl"] = os.path.join(base_dir, "%(title)s.%(ext)s")

    if mode == "video":
        quality_map = {
            "best": "bestvideo+bestaudio/best",
            "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        }
        opts["format"] = quality_map.get(quality, "bestvideo+bestaudio/best")
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }
        ]

    return opts


def download_worker(urls, mode, quality, audio_format, is_playlist, download_id):
    import yt_dlp

    total = len(urls)
    completed = 0
    failed = 0
    titles = []
    failed_items = []
    downloaded_files = []

    log(f"Starting download: {total} item(s), mode={mode}, quality={quality}")

    for url in urls:
        if active_downloads.get(download_id, {}).get("cancelled"):
            active_downloads[download_id]["status"] = "cancelled"
            active_downloads[download_id]["title"] = f"Cancelled — {completed}/{total} downloaded"
            log("Download cancelled by user")
            return

        opts = get_ydl_opts(mode, quality, audio_format, is_playlist)

        current_num = completed + 1
        active_downloads[download_id]["current_index"] = current_num
        active_downloads[download_id]["total_count"] = total

        def progress_hook(d, _url=url):
            if d["status"] == "downloading":
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                file_pct = round((downloaded / total_bytes * 100)) if total_bytes else 0
                overall_pct = round(((completed + file_pct / 100) / total) * 100)
                active_downloads[download_id]["progress"] = overall_pct
                active_downloads[download_id]["file_progress"] = file_pct

        opts["progress_hooks"] = [progress_hook]

        log(f"[{current_num}/{total}] Downloading: {url}")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Unknown")
                titles.append(title)
                completed += 1

                # Find downloaded file
                base_dir = VIDEO_DIR if mode == "video" else MUSIC_DIR
                ext = "mp4" if mode == "video" else audio_format
                file_path = os.path.join(base_dir, f"{title}.{ext}")
                if os.path.exists(file_path):
                    downloaded_files.append(file_path)

                active_downloads[download_id]["current"] = f"[{current_num}/{total}] {title}"
                active_downloads[download_id]["progress"] = round((completed / total) * 100)
                active_downloads[download_id]["file_progress"] = 0
                active_downloads[download_id]["current_index"] = current_num
                active_downloads[download_id]["files"] = downloaded_files
                log(f"[{current_num}/{total}] Done: {title}")
        except Exception as e:
            failed += 1
            err_msg = str(e)[:80]
            active_downloads[download_id]["current"] = f"[{current_num}/{total}] Failed: {err_msg}"
            failed_items.append({"url": url, "title": f"Video {current_num}", "error": err_msg})
            log(f"[{current_num}/{total}] FAILED: {err_msg}")

    status_text = f"Done — {completed}/{total} downloaded"
    if failed:
        status_text += f" ({failed} failed)"

    active_downloads[download_id]["status"] = "done"
    active_downloads[download_id]["title"] = status_text
    active_downloads[download_id]["progress"] = 100
    active_downloads[download_id]["completed_count"] = completed
    active_downloads[download_id]["failed_count"] = failed
    active_downloads[download_id]["failed_items"] = failed_items

    log(f"Finished: {completed}/{total} downloaded, {failed} failed")

    save_history({
        "title": ", ".join(titles[:3]) + (f" +{len(titles) - 3} more" if len(titles) > 3 else ""),
        "mode": mode,
        "quality": quality,
        "count": completed,
        "total": total,
        "failed": failed,
        "failed_items": failed_items,
        "date": time.strftime("%Y-%m-%d %I:%M %p"),
        "status": "done" if not failed else "partial",
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/download/<download_id>/<int:index>")
def serve_download(download_id, index):
    dl = active_downloads.get(download_id)
    if not dl or "files" not in dl:
        return jsonify({"error": "Not found"}), 404

    files = dl["files"]
    if index < 0 or index >= len(files):
        return jsonify({"error": "Invalid index"}), 404

    file_path = files[index]
    if not os.path.exists(file_path):
        return jsonify({"error": "File expired"}), 404

    return send_file(file_path, as_attachment=True)


@app.route("/api/fetch", methods=["POST"])
def fetch_playlist():
    import yt_dlp

    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    log(f"Fetching info: {url}")

    opts = {
        "quiet": True,
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({"error": "Could not fetch video info"}), 400

        existing_files = scan_existing_files()

        entries = info.get("entries")
        if entries:
            videos = []
            for i, entry in enumerate(entries):
                if entry is None:
                    continue
                vtitle = entry.get("title", f"Video {i + 1}")
                matched, fmt = find_existing_match(vtitle, existing_files)
                videos.append({
                    "index": i,
                    "title": vtitle,
                    "url": entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    "duration": entry.get("duration_string") or entry.get("duration") or "",
                    "already_downloaded": matched,
                    "downloaded_format": fmt,
                })
            log(f"Playlist found: {info.get('title')} ({len(videos)} videos)")
            return jsonify({
                "type": "playlist",
                "title": info.get("title", "Playlist"),
                "count": len(videos),
                "videos": videos,
            })
        else:
            vtitle = info.get("title", "Video")
            matched, fmt = find_existing_match(vtitle, existing_files)
            log(f"Single video: {vtitle}")
            return jsonify({
                "type": "video",
                "title": vtitle,
                "url": url,
                "duration": info.get("duration_string") or "",
                "already_downloaded": matched,
                "downloaded_format": fmt,
            })
    except Exception as e:
        log(f"Fetch error: {e}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json
    urls = data.get("urls", [])
    mode = data.get("mode", "video")
    quality = data.get("quality", "best")
    audio_format = data.get("audio_format", "mp3")

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    is_playlist = len(urls) > 1
    download_id = str(len(active_downloads) + 1)
    active_downloads[download_id] = {
        "status": "downloading",
        "progress": 0,
        "file_progress": 0,
        "current_index": 0,
        "total_count": len(urls),
        "completed_count": 0,
        "failed_count": 0,
        "failed_items": [],
        "title": f"Downloading {len(urls)} item(s)...",
        "current": "",
        "error": None,
        "cancelled": False,
    }

    thread = threading.Thread(
        target=download_worker,
        args=(urls, mode, quality, audio_format, is_playlist, download_id),
        daemon=True,
    )
    thread.start()

    return jsonify({"id": download_id})


@app.route("/api/retry", methods=["POST"])
def retry_failed():
    data = request.json
    urls = data.get("urls", [])
    mode = data.get("mode", "video")
    quality = data.get("quality", "best")
    audio_format = data.get("audio_format", "mp3")

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    download_id = str(len(active_downloads) + 1)
    active_downloads[download_id] = {
        "status": "downloading",
        "progress": 0,
        "file_progress": 0,
        "current_index": 0,
        "total_count": len(urls),
        "completed_count": 0,
        "failed_count": 0,
        "failed_items": [],
        "title": f"Retrying {len(urls)} item(s)...",
        "current": "",
        "error": None,
        "cancelled": False,
    }

    thread = threading.Thread(
        target=download_worker,
        args=(urls, mode, quality, audio_format, len(urls) > 1, download_id),
        daemon=True,
    )
    thread.start()

    return jsonify({"id": download_id})


@app.route("/api/cancel/<download_id>", methods=["POST"])
def cancel_download(download_id):
    dl = active_downloads.get(download_id)
    if not dl:
        return jsonify({"error": "Not found"}), 404
    dl["cancelled"] = True
    log("Cancel requested")
    return jsonify({"ok": True})


@app.route("/api/status/<download_id>")
def get_status(download_id):
    dl = active_downloads.get(download_id)
    if not dl:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dl)


@app.route("/api/history")
def get_history():
    return jsonify(load_history())


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    with history_lock:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    log("History cleared")
    return jsonify({"ok": True})


@app.route("/api/history/<int:index>", methods=["DELETE"])
def delete_history_item(index):
    with history_lock:
        history = load_history()
        if 0 <= index < len(history):
            history.pop(index)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    print()
    print("  ================================================")
    print("   PVLM YouTube Downloader")
    print("   Created by Prince Vic Lacson Mayordo")
    print("  ================================================")
    print(f"   Video: {VIDEO_DIR}")
    print(f"   Music: {MUSIC_DIR}")
    print()
    print("   Local:   http://localhost:5000")
    print("   Network: http://192.168.254.102:5000")
    print("  ================================================")
    print()
    app.run(debug=True, host='0.0.0.0', port=5000)
