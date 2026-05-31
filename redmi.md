<p align="center">
  <img src="PollenScripe.ico" alt="PollenScribe icon" width="96" height="96">
</p>

<h1 align="center">PollenScribe Reboot & Release Checklist</h1>

<p align="center">
  Lightweight Windows dictation utility for recording speech, transcribing it, and pasting the result into the active app.
</p>

<p align="center">
  <strong>Hotkey:</strong> Ctrl + Shift + Space · <strong>UI:</strong> Ctrl + Shift + P · <strong>Platform:</strong> Windows
</p>

---

## Quick status

| Item | Detail |
| --- | --- |
| App name | `PollenScribe` |
| Main source file | `pollenscribe.py` |
| Packaged executable | `PollenScribe.exe` |
| Latest exe size to publish | About `94 MB` |
| App icon | `PollenScripe.ico` |
| Build output folder | `dist\` |
| Required runtime config | `.env` next to the running `.exe` |

---

## Most important release rule

When someone runs the packaged executable, these two files must be in the same folder:

```text
PollenScribe.exe
.env
```

If `.env` is missing, renamed, or placed somewhere else, the app will not be able to load `POLLINATIONS_API_KEY`, and transcription will fail.

Do not publish your real `.env` file. Publish `.env.example` and tell each user to copy it to `.env` and add their own API key.

---

## Files to include when publishing

Include:

```text
PollenScribe.exe
.env.example
README.md
redmi.md
```

Do not include:

```text
.env
pollenscribe_temp.wav
__pycache__\
build\
```

Optional but useful to include for developers:

```text
pollenscribe.py
requirements.txt
setup.bat
build_exe.bat
install_startup.bat
uninstall_startup.bat
PollenScripe.ico
```

---

## Environment setup

Create `.env` from `.env.example`:

```powershell
copy .env.example .env
```

Then edit `.env` and set the required key:

```env
POLLINATIONS_API_KEY=your_api_key_here
```

Optional settings:

```env
POLLENSCRIBE_MODEL=whisper
POLLINATIONS_BASE_URL=https://gen.pollinations.ai/v1
POLLENSCRIBE_SILENCE_THRESHOLD=500
POLLENSCRIBE_TRIM_PADDING_MS=250
```

### Environment variable meaning

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `POLLINATIONS_API_KEY` | Yes | none | API key used for transcription. |
| `POLLENSCRIBE_MODEL` | No | `whisper` | Transcription model name. |
| `POLLINATIONS_BASE_URL` | No | `https://gen.pollinations.ai/v1` | OpenAI-compatible API base URL. |
| `POLLENSCRIBE_SILENCE_THRESHOLD` | No | `500` | Controls how aggressively silence is trimmed. |
| `POLLENSCRIBE_TRIM_PADDING_MS` | No | `250` | Keeps padding around detected speech. |

---

## User instructions for the released exe

Give users these exact steps:

1. Download or unzip the release folder.
2. Copy `.env.example` to `.env`.
3. Open `.env` and set `POLLINATIONS_API_KEY`.
4. Keep `.env` in the same folder as `PollenScribe.exe`.
5. Double-click `PollenScribe.exe`.
6. Use `Ctrl + Shift + Space` to start recording.
7. Press `Ctrl + Shift + Space` again or `Enter` to stop and transcribe.
8. Use `Ctrl + Shift + P` to show or hide the floating UI.

---

## Build checklist

Before building:

- Confirm `PollenScripe.ico` exists in the repo root.
- Confirm `.env.example` exists and does not contain a real secret.
- Confirm `.env` exists locally only if testing the built exe.
- Confirm dependencies are installed with `setup.bat`.

Build:

```powershell
.\build_exe.bat
```

Expected output:

```text
dist\PollenScribe.exe
```

The build script uses this icon:

```text
PollenScripe.ico
```

If local `.env` exists, `build_exe.bat` copies it to:

```text
dist\.env
```

That copied file is only for local testing. Do not upload or share `dist\.env`.

---

## Startup checklist

To make the app start when Windows signs in:

1. Build the exe first.
2. Confirm this exists:

```text
dist\PollenScribe.exe
```

3. Confirm this exists for local startup testing:

```text
dist\.env
```

4. Run:

```powershell
.\install_startup.bat
```

The startup shortcut points to the exe and uses `dist` as the working directory, so the `.env` file needs to be inside `dist` when using the startup shortcut from this repo.

To remove auto-start:

```powershell
.\uninstall_startup.bat
```

Or delete this shortcut manually:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PollenScribe.lnk
```

---

## App controls

| Action | Control |
| --- | --- |
| Start recording | `Ctrl + Shift + Space` |
| Stop and transcribe | `Ctrl + Shift + Space` or `Enter` |
| Show/hide UI | `Ctrl + Shift + P` |
| Pause recording | Pause button in overlay |
| Cancel recording | Stop button in overlay |
| Quit app | System tray menu |

---

## Troubleshooting

### App says `POLLINATIONS_API_KEY is not set`

Check:

- `.env` exists.
- `.env` is in the same folder as the running `PollenScribe.exe`.
- `.env` contains `POLLINATIONS_API_KEY=...`.
- The key line is not commented out with `#`.

### Transcription fails

Check:

- API key is valid.
- `POLLINATIONS_BASE_URL` is correct.
- Internet connection is working.
- Microphone audio was actually captured.

### Hotkeys do not work

Try:

- Run PollenScribe as Administrator.
- Close another app using the same hotkey.
- Restart PollenScribe after changing permissions.

### Microphone does not record

Check:

- Windows microphone privacy permissions.
- Default input device.
- Microphone is not muted.
- Another app is not exclusively controlling the mic.

### Icon is missing or wrong

Check:

- `PollenScripe.ico` exists in the repo root.
- `build_exe.bat` was used after the icon was added.
- The old exe was replaced with the newly built exe.
- Windows icon cache may still show the old icon temporarily.

---

## Final release reminder

Before publishing the 94 MB exe, make sure the release notes clearly say:

> `PollenScribe.exe` requires a `.env` file in the same folder. Copy `.env.example` to `.env`, add your API key, then run the exe.

This one detail prevents the most common setup issue.
