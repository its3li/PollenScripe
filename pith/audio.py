"""Microphone capture, silence trimming, and upload encoding."""

from __future__ import annotations

import io
import threading

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav

from .config import BYTES_PER_SAMPLE, CHANNELS, DTYPE, SAMPLE_RATE, Settings
from .status import StatusBus, log

WAV_NAME = "dictation.wav"
FLAC_NAME = "dictation.flac"


def trim_silence(audio: np.ndarray, threshold: int, padding_ms: int) -> np.ndarray:
    """Drop leading and trailing silence, keeping `padding_ms` either side."""
    if audio.size == 0:
        return audio

    active = np.flatnonzero(np.abs(audio) > threshold)
    if active.size == 0:
        return audio[:0]

    padding = int(SAMPLE_RATE * padding_ms / 1000)
    start = max(0, int(active[0]) - padding)
    end = min(audio.size, int(active[-1]) + padding + 1)
    return audio[start:end]


def encode_for_upload(audio: np.ndarray, flac_threshold_bytes: int) -> tuple[io.BytesIO, str]:
    """Encode audio for upload, preferring WAV for latency and FLAC for size.

    Groq's docs recommend WAV for the lowest latency (no server-side decode) and
    FLAC for lossless size reduction. Short clips take the WAV path; longer ones
    trade a few milliseconds of encoding for roughly half the upload.
    """
    if audio.size * BYTES_PER_SAMPLE >= flac_threshold_bytes:
        flac = _encode_flac(audio)
        if flac is not None:
            return flac, FLAC_NAME

    buffer = io.BytesIO()
    write_wav(buffer, SAMPLE_RATE, audio)
    buffer.seek(0)
    return buffer, WAV_NAME


def _encode_flac(audio: np.ndarray) -> io.BytesIO | None:
    """FLAC-encode via soundfile, or return None so the caller falls back to WAV."""
    try:
        import soundfile as sf
    except ImportError:
        return None

    try:
        buffer = io.BytesIO()
        sf.write(buffer, audio, SAMPLE_RATE, format="FLAC", subtype="PCM_16")
        buffer.seek(0)
        return buffer
    except Exception as exc:
        log(f"FLAC encoding failed ({exc}); using WAV instead.")
        return None


class AudioRecorder:
    """Owns the input stream and accumulates captured audio.

    Chunks are collected in a list and joined once, in the worker thread, after
    the stream has closed. Appending to a list is allocation-free enough for the
    realtime callback, and the join costs about a millisecond per minute of
    audio, so there is nothing to gain from a fancier buffer here.
    """

    def __init__(self, settings: Settings, bus: StatusBus) -> None:
        self._settings = settings
        self._bus = bus
        self._paused = threading.Event()
        self._chunks: list[np.ndarray] = []
        self._samples = 0
        self._max_samples = settings.max_seconds * SAMPLE_RATE
        self._overflowed = False
        self._stream: sd.InputStream | None = None

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def overflowed(self) -> bool:
        return self._overflowed

    def toggle_pause(self) -> bool:
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()
        return self._paused.is_set()

    def start(self) -> None:
        self._paused.clear()
        self._chunks = []
        self._samples = 0
        self._overflowed = False
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Close the stream and return everything captured as a mono array."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                log(f"Could not close the audio stream cleanly: {exc}")

        self._paused.clear()
        self._bus.set_level(0.0)
        if not self._chunks:
            return np.empty(0, dtype=np.int16)

        chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks)

    def close(self) -> None:
        """Release the microphone without collecting the audio, for shutdown."""
        self.stop()
        self._chunks = []

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log(f"Audio warning: {status}")

        # Checking an Event is lock-free, so a slow UI or network thread can
        # never stall the realtime audio thread here.
        if self._paused.is_set():
            self._bus.set_level(0.0)
            return

        if self._samples >= self._max_samples:
            self._overflowed = True
            return

        mono = indata.reshape(-1).copy()
        self._chunks.append(mono)
        self._samples += mono.size

        level = float(np.sqrt(np.mean(np.square(mono.astype(np.float32)))) / 32768.0)
        self._bus.set_level(min(1.0, level * 24))
