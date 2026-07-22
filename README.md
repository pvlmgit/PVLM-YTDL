# PVLM YouTube Downloader

A free, fast, and easy-to-use YouTube video and music downloader with a modern web interface.

## Features

- Download YouTube videos in multiple qualities (720p, 1080p, 4K)
- Extract audio as MP3, WAV, FLAC, or M4A
- Download entire playlists at once
- Track download history
- Mobile-friendly responsive design
- Dark mode interface
- Progress tracking with real-time updates

## Live Demo

Visit: [pvlm.site/ytdownloader](https://pvlm.site/ytdownloader)

## How to Use

1. Copy a YouTube video or playlist URL
2. Paste it in the URL field
3. Choose Video or Audio format
4. Click Download
5. Wait for the download to complete

## Tech Stack

- **Backend:** Python, Flask, yt-dlp
- **Frontend:** HTML5, CSS3, JavaScript
- **Deployment:** Railway

## Installation

### Local Setup

```bash
# Clone the repository
git clone https://github.com/pvlmgit/PVLM-YTDL.git
cd PVLM-YTDL

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open http://localhost:5000 in your browser.

### Deploy to Railway

1. Fork or clone this repository
2. Go to [Railway](https://railway.app)
3. Create new project from GitHub repo
4. Select this repository
5. Railway will auto-deploy

## Project Structure

```
PVLM-YTDL/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── Procfile           # Railway deployment config
├── runtime.txt        # Python version
├── static/            # Static files (logo, PWA)
│   ├── logo.png
│   ├── manifest.json
│   └── sw.js
└── templates/         # HTML templates
    └── index.html
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main page |
| `/api/fetch` | POST | Fetch video/playlist info |
| `/api/download` | POST | Start download |
| `/api/status/<id>` | GET | Get download progress |
| `/api/cancel/<id>` | POST | Cancel download |
| `/api/history` | GET | Get download history |

## Requirements

- Python 3.8+
- pip

## Disclaimer

This tool is for educational purposes only. Please respect YouTube's Terms of Service and copyright laws.

## Author

**Prince Vic Lacson Mayordo**
- Website: [pvlm.site](https://pvlm.site)
- GitHub: [@pvlmgit](https://github.com/pvlmgit)

## License

MIT License

---

Made with Python and Flask
