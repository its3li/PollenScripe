"""Pasting into the focused window, with clipboard save and restore."""

from __future__ import annotations

import ctypes
import threading
import time

import keyboard
import pyperclip

from .status import log

user32 = ctypes.WinDLL("user32", use_last_error=True)

CF_UNICODETEXT = 13


def get_foreground_window() -> int | None:
    return user32.GetForegroundWindow() or None


def is_foreground_window(hwnd: int | None) -> bool:
    return bool(hwnd and user32.IsWindow(hwnd) and user32.GetForegroundWindow() == hwnd)


def clipboard_has_text() -> bool:
    """True when the clipboard holds text we can meaningfully save and restore."""
    try:
        return bool(user32.IsClipboardFormatAvailable(CF_UNICODETEXT))
    except Exception:
        return False


def apply_leading_space(text: str, enabled: bool) -> str:
    """Prepend one space so dictation appends cleanly to half-typed text.

    Whether a space is wanted depends on what is already in the target field, and
    Windows offers no reliable way to read that from another process, so this is
    an explicit user setting rather than a guess. Punctuation-initial text never
    gets a space, since that would read as a typo.
    """
    if not enabled or not text:
        return text
    if text[0].isspace() or text[0] in ".,!?;:)]}'\"":
        return text
    return f" {text}"


def paste_text(text: str, hwnd: int | None, keep_clipboard: bool, restore_ms: int) -> bool:
    """Paste `text` into `hwnd`, or leave it on the clipboard if focus moved.

    Returns True when the text was pasted, False when it was only copied.
    """
    # Re-check focus immediately before pasting: the API round trip gave the user
    # time to switch windows, and pasting into the wrong app is worse than not
    # pasting at all.
    if hwnd and not is_foreground_window(hwnd):
        pyperclip.copy(text)
        return False

    had_text = clipboard_has_text()
    previous = ""
    if had_text:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            had_text = False
    elif keep_clipboard:
        log("Clipboard held non-text content; it could not be preserved.")

    pyperclip.copy(text)
    keyboard.press_and_release("ctrl+v")

    if keep_clipboard and had_text:
        _restore_clipboard_later(previous, restore_ms)

    return True


def _restore_clipboard_later(previous: str, delay_ms: int) -> None:
    """Put the old clipboard back, off the critical path.

    There is no notification when a target app finishes reading the clipboard, so
    this is a delay rather than a handshake. The old 30 ms was short enough that
    slower apps regularly pasted the restored value instead of the transcript;
    the wait now happens on a background thread, so a longer, safer delay costs
    the user nothing.
    """

    def worker() -> None:
        time.sleep(delay_ms / 1000)
        try:
            pyperclip.copy(previous)
        except Exception as exc:
            log(f"Could not restore the previous clipboard: {exc}")

    threading.Thread(target=worker, daemon=True).start()
