"""Pith: press-to-talk dictation that pastes into whatever has focus.

The name is the job: you say it however it comes out, and what lands in the
text field is the pith — the substance, with the fillers and false starts gone.
"""

from __future__ import annotations

__all__ = ["main"]

__version__ = "2.0.0"


def main() -> int:
    # Imported lazily so `import pith` stays cheap and Qt-free.
    from .app import main as _main

    return _main()
