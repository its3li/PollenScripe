"""Session-state tests: debounce, cancel, no-speech, and the hotkey lifecycle."""

from __future__ import annotations

import queue
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pith import app as app_module
from pith.app import DEBOUNCE_SECONDS, DictationApp
from test_groq_client import make_settings

SAMPLE_RATE = 16_000


class FakeRecorder:
    def __init__(self, audio: np.ndarray | None = None) -> None:
        self.audio = audio if audio is not None else np.zeros(0, dtype=np.int16)
        self.started = 0
        self.stopped = 0
        self.overflowed = False
        self.paused = False

    def start(self) -> None:
        self.started += 1

    def stop(self) -> np.ndarray:
        self.stopped += 1
        return self.audio

    def close(self) -> None:
        self.stopped += 1

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused


class FakeClient:
    def __init__(self, text: str = "hello there") -> None:
        self.text = text
        self.transcribed = 0
        self.fixed = 0

    def prewarm(self) -> None:
        pass

    def close(self) -> None:
        pass

    def transcribe(self, payload, filename) -> str:
        self.transcribed += 1
        return self.text

    def fix_transcript(self, text: str) -> str:
        self.fixed += 1
        return text


@pytest.fixture
def dictation(monkeypatch):
    """A DictationApp with the microphone, network, and hotkeys stubbed out."""
    bound: list[str] = []

    class FakeKeyboard:
        @staticmethod
        def add_hotkey(combo, handler, suppress=False):
            bound.append(combo)
            return combo

        @staticmethod
        def remove_hotkey(handle):
            bound.remove(handle)

    monkeypatch.setattr(app_module, "keyboard", FakeKeyboard)
    monkeypatch.setattr(app_module, "beep", lambda _frequency: None)

    instance = DictationApp(make_settings())
    instance.recorder = FakeRecorder()
    instance.client = FakeClient()
    instance.bound = bound
    return instance


def statuses(instance: DictationApp) -> list[str]:
    seen = []
    while True:
        try:
            seen.append(instance.bus.status.get_nowait()[0])
        except queue.Empty:
            return seen


class TestRecordingState:
    def test_start_then_stop_runs_one_recording(self, dictation, monkeypatch):
        processed = []
        monkeypatch.setattr(
            DictationApp, "_spawn_processing", lambda self, a, h: processed.append(a)
        )

        dictation.start()
        assert dictation.recorder.started == 1
        assert "Recording..." in statuses(dictation)

        dictation._started_at -= DEBOUNCE_SECONDS  # Pretend the user actually spoke.
        dictation.stop()
        assert dictation.recorder.stopped == 1
        assert len(processed) == 1

    def test_a_double_tap_is_swallowed_and_keeps_recording(self, dictation, monkeypatch):
        processed = []
        monkeypatch.setattr(
            DictationApp, "_spawn_processing", lambda self, a, h: processed.append(a)
        )

        dictation.start()
        dictation.stop()  # Immediately, so inside the debounce window.

        assert dictation.recorder.stopped == 0
        assert processed == []
        assert dictation._recording is True

    def test_cancel_ignores_the_debounce_because_it_is_deliberate(self, dictation, monkeypatch):
        processed = []
        monkeypatch.setattr(
            DictationApp, "_spawn_processing", lambda self, a, h: processed.append(a)
        )

        dictation.start()
        dictation.cancel()

        assert dictation.recorder.stopped == 1
        assert processed == []
        assert "Cancelled" in statuses(dictation)

    def test_stopping_when_idle_does_nothing(self, dictation):
        dictation.stop()
        assert dictation.recorder.stopped == 0

    def test_starting_twice_only_opens_one_stream(self, dictation):
        dictation.start()
        dictation.start()
        assert dictation.recorder.started == 1

    def test_pause_is_ignored_when_not_recording(self, dictation):
        dictation.toggle_pause()
        assert dictation.recorder.paused is False

    def test_a_microphone_failure_leaves_the_app_idle(self, dictation, monkeypatch):
        def explode() -> None:
            raise RuntimeError("no input device")

        monkeypatch.setattr(dictation.recorder, "start", explode)
        dictation.start()

        assert dictation._recording is False
        assert "Microphone error" in statuses(dictation)


class TestSessionHotkeys:
    def test_esc_is_bound_only_while_recording(self, dictation, monkeypatch):
        monkeypatch.setattr(DictationApp, "_spawn_processing", lambda self, a, h: None)

        assert dictation.bound == []
        dictation.start()
        assert dictation.bound == ["esc"]

        dictation._started_at -= DEBOUNCE_SECONDS
        dictation.stop()
        assert dictation.bound == []

    def test_enter_is_bound_only_when_opted_in(self, monkeypatch, dictation):
        # The reported bug: a permanently bound, unsuppressed Enter sent the
        # half-typed message it was meant to stop the recording on.
        dictation.settings = make_settings(stop_on_enter=True)
        dictation.start()
        assert dictation.bound == ["esc", "enter"]

    def test_cancelling_releases_the_session_hotkeys(self, dictation):
        dictation.start()
        dictation.cancel()
        assert dictation.bound == []


class TestProcess:
    def test_silence_is_never_uploaded(self, dictation, monkeypatch):
        monkeypatch.setattr(app_module, "paste_text", lambda *a, **k: pytest.fail("pasted"))

        dictation._process(np.zeros(SAMPLE_RATE, dtype=np.int16), None)

        assert dictation.client.transcribed == 0
        assert "No speech detected" in statuses(dictation)

    def test_speech_is_transcribed_cleaned_and_pasted(self, dictation, monkeypatch):
        pasted = []
        monkeypatch.setattr(
            app_module, "paste_text", lambda text, hwnd, keep, ms: pasted.append(text) or True
        )

        t = np.arange(SAMPLE_RATE, dtype=np.float32)
        speech = (6000 * np.sin(t * 0.05)).astype(np.int16)
        dictation._process(speech, None)

        assert dictation.client.transcribed == 1
        assert dictation.client.fixed == 1
        assert pasted == ["hello there"]
        assert dictation.history.items() == ["hello there"]
        assert "Pasted" in statuses(dictation)

    def test_a_moved_focus_leaves_the_text_on_the_clipboard(self, dictation, monkeypatch):
        monkeypatch.setattr(app_module, "paste_text", lambda *a, **k: False)
        monkeypatch.setattr(app_module.winsound, "MessageBeep", lambda _flag: None)

        t = np.arange(SAMPLE_RATE, dtype=np.float32)
        speech = (6000 * np.sin(t * 0.05)).astype(np.int16)
        dictation._process(speech, 1234)

        assert "Copied to clipboard" in statuses(dictation)
        # Still recoverable from the tray menu, so nothing is lost either way.
        assert dictation.history.items() == ["hello there"]

    def test_a_transcription_failure_is_reported_not_swallowed(self, dictation, monkeypatch):
        def explode(*_args, **_kwargs):
            raise RuntimeError("Groq is down")

        monkeypatch.setattr(dictation.client, "transcribe", explode)

        t = np.arange(SAMPLE_RATE, dtype=np.float32)
        speech = (6000 * np.sin(t * 0.05)).astype(np.int16)
        dictation._process(speech, None)

        assert "Error" in statuses(dictation)
        assert dictation.history.items() == []

    def test_an_oversized_recording_is_rejected_before_it_is_uploaded(self, dictation, monkeypatch):
        # Uploading past the limit does not reliably come back as a 413: the
        # connection is dropped mid-transfer and surfaces as "check your internet
        # connection", which would then be retried on the fallback model. So the
        # size check has to happen here, before the first byte goes out.
        monkeypatch.setattr(app_module, "UPLOAD_LIMIT_BYTES", 64 * 1024)
        monkeypatch.setattr(
            dictation.client, "transcribe", lambda *a, **k: pytest.fail("uploaded anyway")
        )

        t = np.arange(SAMPLE_RATE * 5, dtype=np.float32)
        speech = (6000 * np.sin(t * 0.05)).astype(np.int16)
        dictation._process(speech, None)

        assert "Error" in statuses(dictation)
