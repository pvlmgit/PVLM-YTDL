# Build EXE - Windows Desktop App

## Prerequisites
1. Install Node.js: https://nodejs.org
2. Install Python: https://python.org

## Steps

### 1. Install Dependencies
Open terminal in the `electron` folder:
```bash
cd electron
npm install
```

### 2. Test the App First
```bash
npm start
```
This opens the app. Make sure Flask server starts automatically.

### 3. Build the EXE
```bash
npm run build
```

### 4. Find Your EXE
The EXE will be in: `electron/dist/PVLM YouTube Downloader Setup.exe`

---

## How It Works
- Electron starts the Python/Flask server in background
- Opens a window loading http://localhost:5000
- Downloads go to your local Downloads folder
- Works offline, no YouTube blocking!

---

## Troubleshooting
If Python doesn't start:
1. Make sure Python is installed
2. Make sure `pip install -r requirements.txt` was run
3. Check that port 5000 is not in use
