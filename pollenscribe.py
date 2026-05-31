"""PollenScribe: lightweight Windows dictation-to-paste utility."""

from __future__ import annotations

import ctypes
import io
import os
import queue
import sys
import threading
import time
from pathlib import Path

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import winsound
from dotenv import load_dotenv
from openai import APIStatusError, OpenAI
from scipy.io.wavfile import write as write_wav
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget

load_dotenv()

APP_NAME = "PollenScribe"
HOTKEY = "ctrl+shift+space"
UI_HOTKEY = "ctrl+shift+p"
TEMP_WAV = Path("pollenscribe_temp.wav")
SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "int16"
MODEL = os.getenv("POLLENSCRIBE_MODEL", "whisper")
SILENCE_THRESHOLD = int(os.getenv("POLLENSCRIBE_SILENCE_THRESHOLD", "500"))
TRIM_PADDING_MS = int(os.getenv("POLLENSCRIBE_TRIM_PADDING_MS", "250"))
POLLINATIONS_BASE_URL = os.getenv("POLLINATIONS_BASE_URL", "https://gen.pollinations.ai/v1")
REQUEST_HEADERS = {
    "User-Agent": "PollenScribe/1.0 Windows Dictation App",
    "Accept": "application/json",
}

recording = False
recording_paused = False
cancel_recording = False
processing = False
recording_lock = threading.Lock()
audio_queue: queue.Queue[np.ndarray] = queue.Queue()
status_queue: queue.Queue[tuple[str, str]] = queue.Queue()
ui_command_queue: queue.Queue[str] = queue.Queue()
audio_level_queue: queue.Queue[float] = queue.Queue()
audio_chunks: list[np.ndarray] = []
stream: sd.InputStream | None = None
openai_client: OpenAI | None = None
target_window: int | None = None
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def log(message: str) -> None:
    print(f"[{APP_NAME}] {message}", flush=True)


def show_status(state: str, detail: str = "") -> None:
    status_queue.put((state, detail))


def show_overlay() -> None:
    ui_command_queue.put("show")


def hide_overlay(delay_ms: int = 0) -> None:
    ui_command_queue.put(f"hide:{delay_ms}")


def toggle_status_ui() -> None:
    ui_command_queue.put("toggle")


def toggle_pause_recording() -> None:
    global recording_paused

    with recording_lock:
        if not recording:
            return
        recording_paused = not recording_paused
        paused = recording_paused

    show_status("Paused" if paused else "Recording...", "")


def cancel_current_recording() -> None:
    global cancel_recording

    with recording_lock:
        if not recording:
            return
        cancel_recording = True
    stop_recording()


def start_status_ui() -> None:
    ui_thread = threading.Thread(target=run_status_ui, daemon=True)
    ui_thread.start()


def run_status_ui() -> None:
    app = QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(False)

    widget = StatusWidget()
    tray = PollenTrayIcon(widget)
    tray.show()

    timer = QTimer()
    timer.timeout.connect(widget.poll_queues)
    timer.start(33)

    app.exec()


def create_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#1F2937"))
    painter.setPen(QColor("#6B7280"))
    painter.drawEllipse(4, 4, 56, 56)
    painter.setPen(QColor("#E5E7EB"))
    painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "P")
    painter.end()

    return QIcon(pixmap)


class PollenTrayIcon(QSystemTrayIcon):
    def __init__(self, widget: "StatusWidget") -> None:
        super().__init__(create_tray_icon())
        self.widget = widget
        self.setToolTip(f"{APP_NAME} — {HOTKEY} to dictate, {UI_HOTKEY} to show/hide")

        menu = QMenu()
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(widget.toggle_visible)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self.on_activated)

    def on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.widget.toggle_visible()

    def quit_app(self) -> None:
        keyboard.unhook_all_hotkeys()
        QApplication.quit()


class StatusWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(470, 250)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.level = 0.08
        self.smoothed_level = 0.08
        self.wave_values = [0.14] * 22
        self.phase = 0
        self.is_recording_visual = False
        self.is_paused_visual = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 20, 32, 18)
        layout.setSpacing(5)

        self.title_label = QLabel("PollenScribe")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFixedHeight(34)
        self.title_label.setFont(QFont("Segoe UI Variable Display", 22, QFont.Weight.DemiBold))
        self.title_label.setStyleSheet("color: rgba(255, 255, 255, 242); background: transparent; letter-spacing: 0.25px;")

        self.state_label = QLabel("Ready")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setFont(QFont("Segoe UI Variable Text", 10, QFont.Weight.DemiBold))
        self.state_label.setWordWrap(False)
        self.state_label.setFixedHeight(20)
        self.state_label.setStyleSheet("color: rgba(255, 255, 255, 185); background: transparent;")

        self.detail_label = QLabel(f"{HOTKEY} to dictate")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setFont(QFont("Segoe UI Variable Text", 9))
        self.detail_label.setWordWrap(True)
        self.detail_label.setFixedHeight(18)
        self.detail_label.setStyleSheet("color: rgba(255, 255, 255, 150); background: transparent;")

        controls_widget = QWidget()
        controls_widget.setFixedHeight(38)
        controls = QHBoxLayout(controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pause_button = QPushButton("⏸")
        self.stop_button = QPushButton("⏹")
        for button in (self.pause_button, self.stop_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(38, 38)
            button.setStyleSheet(
                "QPushButton { background: rgba(255, 255, 255, 22); color: rgba(255, 255, 255, 230); "
                "border: 1px solid rgba(255, 255, 255, 42); border-radius: 19px; "
                "font: 700 15px 'Segoe UI Symbol'; padding: 0px; }"
                "QPushButton:hover { background: rgba(255, 255, 255, 36); border-color: rgba(255, 255, 255, 68); }"
                "QPushButton:pressed { background: rgba(255, 255, 255, 16); }"
            )
        self.pause_button.setStyleSheet(self.pause_button.styleSheet() + "QPushButton { padding-left: 1px; padding-bottom: 0px; }")
        self.stop_button.setStyleSheet(self.stop_button.styleSheet() + "QPushButton { padding-left: 1px; padding-bottom: 1px; }")
        self.pause_button.clicked.connect(toggle_pause_recording)
        self.stop_button.clicked.connect(cancel_current_recording)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)

        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addSpacing(58)
        layout.addWidget(self.detail_label)
        layout.addSpacing(2)
        layout.addWidget(controls_widget)

    def show_overlay(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 42)
        self.show()
        self.raise_()

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show_overlay()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QColor(255, 255, 255, 28))
        painter.setBrush(QColor(8, 8, 10, 232))
        painter.drawRoundedRect(rect, 26, 26)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 16))
        painter.drawRoundedRect(rect.adjusted(18, 14, -18, -154), 22, 22)

        wave_rect = self.rect().adjusted(18, 108, -18, -92)
        painter.setPen(QColor(255, 255, 255, 22))
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(wave_rect, 18, 18)

        center_y = wave_rect.center().y()
        bars_rect = wave_rect.adjusted(18, 0, -18, 0)
        bar_count = len(self.wave_values)
        gap = bars_rect.width() / bar_count
        max_h = wave_rect.height() - 10
        for index, value in enumerate(self.wave_values):
            height = max(8, int(value * max_h))
            x = int(bars_rect.left() + index * gap + gap * 0.28)
            width = max(5, int(gap * 0.48))
            color = QColor(245, 245, 247, 220) if self.is_recording_visual else QColor(255, 255, 255, 90)
            if self.is_paused_visual:
                color = QColor(255, 255, 255, 145)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(x, center_y - height // 2, width, height, 4, 4)

    def set_status_text(self, state: str, detail: str) -> None:
        state = state if len(state) <= 24 else f"{state[:21]}..."
        detail = detail if len(detail) <= 96 else f"{detail[:93]}..."
        self.state_label.setText(state)
        self.detail_label.setText(detail)

    def poll_queues(self) -> None:
        while True:
            try:
                command = ui_command_queue.get_nowait()
            except queue.Empty:
                break
            if command == "toggle":
                self.toggle_visible()
            elif command == "show":
                self.show_overlay()
            elif command.startswith("hide:"):
                delay_ms = int(command.split(":", 1)[1])
                if delay_ms > 0:
                    QTimer.singleShot(delay_ms, self.hide)
                else:
                    self.hide()

        while True:
            try:
                state, detail = status_queue.get_nowait()
            except queue.Empty:
                break
            self.set_status_text(state, detail)
            lower_state = state.lower()
            self.is_recording_visual = lower_state.startswith("recording")
            self.is_paused_visual = lower_state.startswith("paused")
            self.pause_button.setText("▶" if self.is_paused_visual else "⏸")
            controls_visible = self.is_recording_visual or self.is_paused_visual
            self.pause_button.setVisible(controls_visible)
            self.stop_button.setVisible(controls_visible)

        while True:
            try:
                self.level = audio_level_queue.get_nowait()
            except queue.Empty:
                break

        if self.is_recording_visual:
            self.phase += 0.62
            self.smoothed_level += (max(0.08, min(1.0, self.level)) - self.smoothed_level) * 0.28
            base = max(0.12, min(1.0, self.smoothed_level))
            targets = [
                max(0.10, min(1.0, base * (0.70 + 0.55 * (0.5 + 0.5 * np.sin(self.phase + i * 0.72)))))
                for i in range(len(self.wave_values))
            ]
            self.wave_values = [current + (target - current) * 0.34 for current, target in zip(self.wave_values, targets)]
        elif self.is_paused_visual:
            self.wave_values = [current + (0.18 - current) * 0.22 for current in self.wave_values]
        else:
            self.wave_values = [current + (0.10 - current) * 0.18 for current in self.wave_values]

        self.update()


def notify_transcription_copied(text: str) -> None:
    preview = text if len(text) <= 90 else f"{text[:87]}..."
    show_status("Copied to clipboard", preview)
    hide_overlay(2200)
    log("Original window is no longer active; transcription copied to clipboard.")
    winsound.MessageBeep(winsound.MB_ICONASTERISK)


def play_beep(frequency: int) -> None:
    try:
        winsound.Beep(frequency, 120)
    except RuntimeError:
        winsound.MessageBeep(winsound.MB_OK)


def beep_start() -> None:
    play_beep(880)


def beep_stop() -> None:
    play_beep(660)


def get_foreground_window() -> int | None:
    hwnd = user32.GetForegroundWindow()
    return hwnd or None


def is_foreground_window(hwnd: int | None) -> bool:
    return bool(hwnd and user32.IsWindow(hwnd) and user32.GetForegroundWindow() == hwnd)


def paste_text(text: str, hwnd: int | None) -> bool:
    if hwnd and not is_foreground_window(hwnd):
        pyperclip.copy(text)
        notify_transcription_copied(text)
        return False

    previous_clipboard = None
    clipboard_had_text = False
    try:
        previous_clipboard = pyperclip.paste()
        clipboard_had_text = True
    except pyperclip.PyperclipException:
        pass

    pyperclip.copy(text)
    keyboard.press_and_release("ctrl+v")
    time.sleep(0.03)

    if clipboard_had_text:
        pyperclip.copy(previous_clipboard)

    return True


def load_api_key() -> str:
    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "POLLINATIONS_API_KEY is not set. Set it in Windows environment variables or a local .env file."
        )
    return api_key


def audio_callback(indata: np.ndarray, frames: int, time_info, status: sd.CallbackFlags) -> None:
    if status:
        log(f"Audio warning: {status}")

    with recording_lock:
        paused = recording_paused

    if paused:
        try:
            audio_level_queue.put_nowait(0.05)
        except queue.Full:
            pass
        return

    audio_queue.put(indata.copy())
    level = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)) / 32768.0)
    try:
        audio_level_queue.put_nowait(min(1.0, level * 24))
    except queue.Full:
        pass


def drain_audio_queue() -> None:
    while True:
        try:
            audio_chunks.append(audio_queue.get_nowait())
        except queue.Empty:
            break


def start_recording() -> None:
    global recording, recording_paused, cancel_recording, stream, audio_chunks, target_window

    with recording_lock:
        if recording or processing:
            return

        recording_paused = False
        cancel_recording = False
        target_window = get_foreground_window()
        show_overlay()
        while not audio_queue.empty():
            audio_queue.get_nowait()

        audio_chunks = []
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=audio_callback,
        )
        stream.start()
        recording = True

    beep_start()
    log("Recording...")
    show_status("Recording...", "")


def stop_recording() -> None:
    global recording, recording_paused, processing, stream

    with recording_lock:
        if not recording or processing:
            return

        should_cancel = cancel_recording
        recording = False
        recording_paused = False
        processing = not should_cancel
        current_stream = stream
        stream = None

    if current_stream is not None:
        current_stream.stop()
        current_stream.close()

    drain_audio_queue()
    beep_stop()

    if should_cancel:
        log("Recording cancelled.")
        show_status("Cancelled", "Recording discarded")
        hide_overlay(900)
        return

    worker = threading.Thread(target=transcribe_and_paste, daemon=True)
    worker.start()


def toggle_recording() -> None:
    try:
        if recording:
            stop_recording()
        else:
            start_recording()
    except Exception as exc:
        log(f"Error: {exc}")


def trim_silence(audio_data: np.ndarray) -> np.ndarray:
    mono = audio_data.reshape(-1) if audio_data.ndim == 1 else audio_data[:, 0]
    active_samples = np.flatnonzero(np.abs(mono) > SILENCE_THRESHOLD)
    if active_samples.size == 0:
        return audio_data

    padding = int(SAMPLE_RATE * TRIM_PADDING_MS / 1000)
    start = max(0, int(active_samples[0]) - padding)
    end = min(len(audio_data), int(active_samples[-1]) + padding + 1)
    return audio_data[start:end]


def build_audio_file() -> io.BytesIO:
    if not audio_chunks:
        raise RuntimeError("No audio was recorded.")

    audio_data = trim_silence(np.concatenate(audio_chunks, axis=0))
    audio_file = io.BytesIO()
    write_wav(audio_file, SAMPLE_RATE, audio_data)
    audio_file.seek(0)
    audio_file.name = TEMP_WAV.name
    return audio_file


def extract_transcription_text(transcription) -> str:
    text = getattr(transcription, "text", None)
    if text is None and isinstance(transcription, dict):
        text = transcription.get("text")
    if not text:
        raise RuntimeError("Transcription returned no text.")
    return text.strip()


def format_api_error(exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        details = exc.message
        try:
            response_text = exc.response.text
            if response_text and response_text not in details:
                details = f"{details} | Response: {response_text}"
        except Exception:
            pass
        return f"Pollinations API HTTP {exc.status_code}: {details}"
    return str(exc)


def create_openai_client() -> OpenAI:
    global openai_client

    if openai_client is None:
        openai_client = OpenAI(
            base_url=POLLINATIONS_BASE_URL,
            api_key=load_api_key(),
            default_headers=REQUEST_HEADERS,
            timeout=120,
        )
    return openai_client


def transcribe_audio_file() -> str:
    client = create_openai_client()
    audio_file = build_audio_file()
    transcription = client.audio.transcriptions.create(
        model=MODEL,
        file=audio_file,
        response_format="json",
    )
    return extract_transcription_text(transcription)


def transcribe_and_paste() -> None:
    global processing, target_window

    with recording_lock:
        paste_window = target_window

    try:
        log(f"Transcribing (using {MODEL})...")
        show_status("Transcribing...", "")

        text = transcribe_audio_file()
        pasted = paste_text(text, paste_window)
        if pasted:
            log("Text pasted successfully.")
            show_status("Text pasted", "Done")
        hide_overlay(1200)

    except Exception as exc:
        log(f"Error: {format_api_error(exc)}")
        show_status("Error", format_api_error(exc))
        hide_overlay(2500)
    finally:
        try:
            if TEMP_WAV.exists():
                TEMP_WAV.unlink()
        except Exception as cleanup_exc:
            log(f"Error: Could not delete temporary WAV file: {cleanup_exc}")

        with recording_lock:
            processing = False
            target_window = None


def main() -> int:
    if sys.platform != "win32":
        log("Error: PollenScribe is designed to run on Windows.")
        return 1

    try:
        load_api_key()
        start_status_ui()
        create_openai_client()
        keyboard.add_hotkey(HOTKEY, toggle_recording)
        keyboard.add_hotkey("enter", stop_recording)
        keyboard.add_hotkey(UI_HOTKEY, toggle_status_ui)
        log(f"Ready and listening for Ctrl+Shift+Space... UI: {UI_HOTKEY}")
        show_status("Ready in tray", f"{HOTKEY} to dictate • {UI_HOTKEY} to show/hide")
        keyboard.wait()
        return 0
    except KeyboardInterrupt:
        log("Exiting.")
        return 0
    except Exception as exc:
        log(f"Error: {exc}")
        return 1
    finally:
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
