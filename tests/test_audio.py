"""Unit tests for the parts of Pith that need neither a mic nor a key."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pith.audio import FLAC_NAME, WAV_NAME, encode_for_upload, trim_silence
from pith.paste import apply_leading_space

SAMPLE_RATE = 16_000


def tone(samples: int, amplitude: int = 6000) -> np.ndarray:
    t = np.arange(samples, dtype=np.float32)
    return (amplitude * np.sin(t * 0.05)).astype(np.int16)


def silence(samples: int) -> np.ndarray:
    return np.zeros(samples, dtype=np.int16)


class TestTrimSilence:
    def test_empty_input_is_returned_unchanged(self):
        assert trim_silence(np.empty(0, dtype=np.int16), 500, 250).size == 0

    def test_silence_only_returns_empty_so_no_speech_is_detectable(self):
        # This is what lets app.py skip the upload entirely rather than sending a
        # silent clip and surfacing an API error.
        assert trim_silence(silence(SAMPLE_RATE), 500, 250).size == 0

    def test_speech_in_the_middle_keeps_speech_plus_padding(self):
        audio = np.concatenate([silence(SAMPLE_RATE), tone(SAMPLE_RATE), silence(SAMPLE_RATE)])
        trimmed = trim_silence(audio, 500, 250)

        padding = SAMPLE_RATE // 4
        assert trimmed.size == pytest.approx(SAMPLE_RATE + 2 * padding, abs=64)
        assert np.abs(trimmed).max() == np.abs(audio).max()

    def test_padding_is_clamped_at_the_edges(self):
        trimmed = trim_silence(tone(SAMPLE_RATE), 500, 5000)
        assert trimmed.size == SAMPLE_RATE

    def test_threshold_above_the_signal_finds_nothing(self):
        assert trim_silence(tone(SAMPLE_RATE, amplitude=100), 500, 250).size == 0


class TestEncodeForUpload:
    def test_small_clip_uses_wav_for_latency(self):
        payload, name = encode_for_upload(tone(SAMPLE_RATE), 600 * 1024)
        assert name == WAV_NAME
        assert payload.getbuffer().nbytes > 0

    def test_large_clip_uses_flac_for_size(self):
        audio = tone(SAMPLE_RATE * 60)
        payload, name = encode_for_upload(audio, 600 * 1024)

        assert name == FLAC_NAME
        # Lossless, but it must actually be smaller than the raw PCM to be worth
        # the encode time.
        assert payload.getbuffer().nbytes < audio.nbytes

    def test_falls_back_to_wav_when_soundfile_is_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "soundfile", None)
        payload, name = encode_for_upload(tone(SAMPLE_RATE * 60), 600 * 1024)

        assert name == WAV_NAME
        assert payload.getbuffer().nbytes > 0

    def test_payload_is_a_rewound_stream(self):
        payload, _ = encode_for_upload(tone(SAMPLE_RATE), 600 * 1024)
        assert isinstance(payload, io.BytesIO)
        assert payload.tell() == 0


class TestApplyLeadingSpace:
    def test_disabled_changes_nothing(self):
        assert apply_leading_space("hello", False) == "hello"

    def test_enabled_prepends_one_space(self):
        assert apply_leading_space("hello", True) == " hello"

    def test_empty_text_is_untouched(self):
        assert apply_leading_space("", True) == ""

    @pytest.mark.parametrize("text", [".", ",", "!", "?", "'ve been here"])
    def test_punctuation_never_gets_a_space(self, text):
        # A space before a comma reads as a typo, not a join.
        assert apply_leading_space(text, True) == text

    def test_existing_whitespace_is_not_doubled(self):
        assert apply_leading_space(" hello", True) == " hello"
