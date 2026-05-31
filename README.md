<p align="center">
  <img src="PollenScripe.png" alt="PollenScribe icon" width="120" height="120">
</p>

<h1 align="center">PollenScribe</h1>

<p align="center">
  <strong>Lightweight Windows dictation that records your voice, transcribes it, and pastes the text into the active app.</strong>
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Build" src="https://img.shields.io/badge/build-PyInstaller-2E3440?style=for-the-badge">
  <img alt="Config" src="https://img.shields.io/badge/config-.env_required-EAB308?style=for-the-badge">
</p>

<p align="center">
  <a href="https://github.com/its3li/PollenScripe/releases/tag/v1.0.0"><strong>Download latest release</strong></a>
  ·
  <a href="#quick-start-for-the-exe"><strong>Quick start</strong></a>
  ·
  <a href="#troubleshooting"><strong>Troubleshooting</strong></a>
</p>

---

## What it does

PollenScribe runs quietly in the Windows tray. Press the dictation hotkey, speak, stop recording, and the transcription is pasted into the app you were using.

```text
Press hotkey → Speak → Stop recording → Text gets pasted
```

---

## Visual overview

| Area | What you get |
| --- | --- |
| 🎙️ Dictation | Global voice recording with `Ctrl + Shift + Space` |
| 📝 Transcription | Uses a Pollinations/OpenAI-compatible audio transcription endpoint |
| 📋 Paste behavior | Pastes into the active window or copies to clipboard if focus changed |
| 🪟 Overlay | Small floating control panel for status, pause, and cancel |
| 🧭 Tray app | Runs in the system tray with show/hide and quit controls |
| 🎨 Icon | Uses `PollenScripe.ico` for the app/release branding |

---

## Controls

| Action | Shortcut / control |
| --- | --- |
| Start recording | `Ctrl + Shift + Space` |
| Stop and transcribe | `Ctrl + Shift + Space` or `Enter` |
| Show / hide overlay | `Ctrl + Shift + P` |
| Pause / resume | Overlay pause button |
| Cancel recording | Overlay stop button |
| Quit | System tray menu |

---

## Requirements

| Requirement | Needed for |
| --- | --- |
| Windows 10/11 | The app uses Windows tray, hotkeys, and paste behavior |
| Working microphone | Audio capture |
| Pollinations API key | Transcription requests |
| Python 3.10+ | Only needed when running from source |

---

## Quick start for the exe

Download the release exe from:

https://github.com/its3li/PollenScripe/releases/tag/v1.0.0

Then keep these files together in the same folder:

```text
PollenScribe-V1.0.exe
.env
```

> [!IMPORTANT]
> The `.env` file must be next to the `.exe`. If `.env` is missing or in another folder, transcription will fail with `POLLINATIONS_API_KEY is not set`.

Create `.env` from `.env.example`:

```powershell
copy .env.example .env
```

Then edit `.env` and add your real API key:

```env
POLLINATIONS_API_KEY=your_api_key_here
```

Run the exe:

```powershell
.\PollenScribe-V1.0.exe
```

---

## Quick install from source

1. Clone or download this folder.
2. Copy `.env.example` to `.env`.
3. Put your API key in `.env`.
4. Run setup.
5. Start the app.

```powershell
copy .env.example .env
.\setup.bat
.\.venv\Scripts\python.exe pollenscribe.py
```

---

## Manual source install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe pollenscribe.py
```

---

## Build a standalone exe

Run:

```powershell
.\build_exe.bat
```

The executable is created at:

```text
dist\PollenScribe.exe
```

The build uses this icon:

```text
PollenScripe.ico
```

> [!NOTE]
> If a local `.env` exists, `build_exe.bat` copies it to `dist\.env` for local testing. Do not publish your real `.env`.

---

---

## Start automatically with Windows

After building the exe:

```powershell
.\install_startup.bat
```

That creates this shortcut:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PollenScribe.lnk
```

To remove auto-start:

```powershell
.\uninstall_startup.bat
```

---

## Configuration

Create a `.env` file from `.env.example`.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `POLLINATIONS_API_KEY` | Yes | none | API key for the transcription endpoint |
| `POLLENSCRIBE_MODEL` | No | `whisper` | Transcription model name |
| `POLLINATIONS_BASE_URL` | No | `https://gen.pollinations.ai/v1` | OpenAI-compatible API base URL |
| `POLLENSCRIBE_SILENCE_THRESHOLD` | No | `500` | Higher trims silence more aggressively |
| `POLLENSCRIBE_TRIM_PADDING_MS` | No | `250` | Speech padding kept around detected audio |

Example:

```env
POLLINATIONS_API_KEY=your_api_key_here
POLLENSCRIBE_MODEL=whisper
POLLINATIONS_BASE_URL=https://gen.pollinations.ai/v1
POLLENSCRIBE_SILENCE_THRESHOLD=500
POLLENSCRIBE_TRIM_PADDING_MS=250
```

---

## Troubleshooting

### `POLLINATIONS_API_KEY is not set`

Check that:

- `.env` exists.
- `.env` is in the same folder as the running exe.
- `.env` contains `POLLINATIONS_API_KEY=...`.
- The key line is not commented out.

### Hotkeys do not work

Try:

- Run PollenScribe as Administrator.
- Close any app using the same hotkey.
- Restart PollenScribe after permission changes.

### Microphone capture fails

Check:

- Windows microphone privacy permissions.
- Default input device.
- Microphone mute state.
- Whether another app is exclusively using the microphone.

### Transcription fails

Check:

- API key is valid.
- Internet connection is working.
- `POLLINATIONS_BASE_URL` is correct.
- Audio was actually recorded.

### Icon looks wrong after rebuilding

Check:

- `PollenScripe.ico` exists in the repo root.
- You rebuilt after adding the icon.
- You are running the newly built exe, not an older one.
- Windows icon cache may still show the old icon temporarily.

---

## Security notes

> [!WARNING]
> Never publish your real `.env` file or API key.

Safe to publish:

```text
.env.example
```

Do not publish:

```text
.env
```

If a real API key was exposed, rotate it before publishing another release.

---

## Project files

| File | Purpose |
| --- | --- |
| `pollenscribe.py` | Main application |
| `PollenScripe.ico` | App and README icon |
| `build_exe.bat` | Builds the standalone exe |
| `setup.bat` | Creates/install source environment |
| `install_startup.bat` | Adds Windows startup shortcut |
| `uninstall_startup.bat` | Removes Windows startup shortcut |
| `.env.example` | Safe config template |
| `redmi.md` | Reboot/release handoff checklist |

---

<p align="center">
  <strong>Remember:</strong> the exe and `.env` must stay together.
</p>
