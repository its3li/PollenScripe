"""Defaults that ship in the absence of a `.env`, since they are the shipped UX."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pith.config import Settings

ENV_VARS = (
    "GROQ_API_KEY",
    "GROQ_BASE_URL",
    "PITH_STOP_ON_ENTER",
    "PITH_FIX",
    "PITH_KEEP_CLIPBOARD",
    "PITH_LANGUAGE",
)

# Both spellings, so a `POLLENSCRIBE_` variable left over in the developer's own
# shell cannot quietly decide what the "shipped default" tests observe.
LEGACY_VARS = tuple(
    name.replace("PITH_", "POLLENSCRIBE_") for name in ENV_VARS if name.startswith("PITH_")
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_VARS + LEGACY_VARS:
        monkeypatch.delenv(name, raising=False)


class TestDefaults:
    def test_enter_stops_a_recording_out_of_the_box(self, clean_env):
        # Enter is bound only while recording and suppressed while bound, so the
        # bug that made it opt-in (a global unsuppressed hook sending a
        # half-typed message) can no longer happen with it on.
        assert Settings.from_env().stop_on_enter is True

    def test_cleanup_is_on_and_the_clipboard_is_restored(self, clean_env):
        settings = Settings.from_env()
        assert settings.fix_enabled is True
        assert settings.keep_clipboard is True

    def test_an_explicit_zero_still_wins(self, monkeypatch):
        monkeypatch.setenv("PITH_STOP_ON_ENTER", "0")
        assert Settings.from_env().stop_on_enter is False

    def test_a_missing_key_names_the_variable_to_set(self, clean_env):
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            Settings.from_env().require_api_key()


class TestLegacyNames:
    """A `.env` written for PollenScribe still configures Pith after the rename."""

    def test_the_old_prefix_is_still_read(self, clean_env, monkeypatch):
        monkeypatch.setenv("POLLENSCRIBE_FIX", "0")
        monkeypatch.setenv("POLLENSCRIBE_HISTORY_SIZE", "9")
        settings = Settings.from_env()
        assert settings.fix_enabled is False
        assert settings.history_size == 9

    def test_the_new_prefix_wins_when_both_are_set(self, clean_env, monkeypatch):
        monkeypatch.setenv("POLLENSCRIBE_LANGUAGE", "fr")
        monkeypatch.setenv("PITH_LANGUAGE", "ar")
        assert Settings.from_env().language == "ar"
