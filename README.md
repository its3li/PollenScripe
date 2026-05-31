# PollenScribe

PollenScribe is a lightweight Windows dictation utility. Press a hotkey, speak, stop recording, and the transcription is pasted into the active window.

## Features

- Global dictation hotkey: `Ctrl + Shift + Space`
- Stop and transcribe with either `Ctrl + Shift + Space` or `Enter`
- Pause/resume and cancel controls in a small floating overlay
- System tray app with show/hide control
- Copies transcription to clipboard if the original target window is no longer active
- Uses a Pollinations/OpenAI-compatible transcription endpoint

## Requirements

- Python 3.10+
- A working microphone
- A Pollinations API key

## Quick install / use the released `.exe`

If you download or publish `PollenScribe.exe`, put a real `.env` file in the exact same folder as the executable:

```text
PollenScribe.exe
.env
```

This is required because the packaged app loads configuration from the folder it runs in. If `.env` is missing or somewhere else, transcription will fail with `POLLINATIONS_API_KEY is not set`.

Do not publish a real `.env` with secrets. Publish `.env.example`, then have each user copy it to `.env` and add their own API key.

## Quick install from source

1. Clone or download this folder.
2. Copy `.env.example` to `.env`.
3. Put your API key in `.env`:

```env
POLLINATIONS_API_KEY=your_api_key_here
```

4. Run the one-time setup script:

```powershell
.\setup.bat
```

5. Start the app:

```powershell
.\.venv\Scripts\python.exe pollenscribe.py
```

## Manual install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe pollenscribe.py
```

## Build a standalone `.exe`

Run:

```powershell
.\build_exe.bat
```

The executable will be created at:

```text
dist\PollenScribe.exe
```

Put your `.env` file next to `PollenScribe.exe` if you run the executable from `dist`.

The build uses `PollenScripe.ico` as the Windows executable icon. Keep that icon file in the repo root before running the build.

Release checklist:

- Build or publish `PollenScribe.exe`.
- Include `.env.example` for users.
- Tell users to create their own `.env` from `.env.example`.
- Tell users the final `.env` must be next to `PollenScribe.exe`.
- Do not publish your real `.env` or API key.

## Start automatically when Windows opens

After building the `.exe`, run:

```powershell
.\install_startup.bat
```

That creates a shortcut in your Windows Startup folder so PollenScribe launches when you sign in.

To remove auto-start, delete this shortcut:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PollenScribe.lnk
```

## Configuration

Create a `.env` file from `.env.example`.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `POLLINATIONS_API_KEY` | Yes | none | API key for the transcription endpoint. |
| `POLLENSCRIBE_MODEL` | No | `whisper` | Transcription model name. |
| `POLLINATIONS_BASE_URL` | No | `https://gen.pollinations.ai/v1` | OpenAI-compatible base URL. |
| `POLLENSCRIBE_SILENCE_THRESHOLD` | No | `500` | Higher trims silence more aggressively. |
| `POLLENSCRIBE_TRIM_PADDING_MS` | No | `250` | Speech padding kept around detected audio. |


## Troubleshooting

- If global hotkeys do not work, try running the terminal/app as Administrator.
- If microphone capture fails, check Windows microphone permissions and your default input device.
- If the app opens but transcription fails, verify `POLLINATIONS_API_KEY`, the base URL, and that `.env` is in the same folder as the running `PollenScribe.exe`.
- If the packaged exe has the wrong icon, confirm `PollenScripe.ico` exists before rebuilding.
