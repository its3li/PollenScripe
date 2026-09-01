"""System tray icon and the floating status overlay."""

from __future__ import annotations

import math
import queue
import time

import pyperclip
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QSystemTrayIcon, QWidget

from .config import APP_NAME, ICON_FILE, TOGGLE_HOTKEY, UI_HOTKEY, resource_path
from .status import History, StatusBus

# Repaint at 33 ms only while something is actually moving: the meter while
# recording, the sweep while a request is out, the settle afterwards. At rest the
# timer drops to 100 ms and does nothing but drain the queues, so an overlay left
# open costs about 1.3% of a core less than it used to.
ACTIVE_INTERVAL_MS = 33
IDLE_INTERVAL_MS = 100

BAR_COUNT = 26
WAVE_FLOOR = 0.10

# Centre-weighted, so the meter tapers off at both ends instead of reading as a
# solid block once the input is loud.
ENVELOPE = tuple(
    0.42 + 0.58 * math.sin(math.pi * (index + 0.5) / BAR_COUNT) for index in range(BAR_COUNT)
)

# The shadow is painted inside the window, so the window is larger than the
# visible card by SHADOW on every side.
SHADOW = 14
CARD_W, CARD_H = 396, 116
WIDGET_W, WIDGET_H = CARD_W + SHADOW * 2, CARD_H + SHADOW * 2
RADIUS = 22

BUTTON_SIZE = 28
BUTTON_STEP = 34

CARD_FILL = QColor(15, 16, 20, 243)
CARD_BORDER = QColor(255, 255, 255, 28)
TITLE_INK = QColor(255, 255, 255, 246)
TIME_INK = QColor(255, 255, 255, 165)
DETAIL_INK = QColor(255, 255, 255, 142)
TRACK_INK = QColor(255, 255, 255, 15)
CLEAR = QColor(0, 0, 0, 0)

# Four widening rings instead of a QGraphicsDropShadowEffect, which would re-blur
# the whole card on every frame of the meter.
SHADOW_RINGS = tuple(
    (inset, QColor(0, 0, 0, alpha)) for inset, alpha in ((12, 18), (9, 14), (6, 11), (3, 7))
)

# The state text drives the accent colour, so a glance at the dot says what the
# app is doing without reading anything. Matched by prefix, longest first.
IDLE_ACCENT = QColor(139, 147, 161)
ACCENTS = (
    ("recording", QColor(255, 107, 94)),
    ("paused", QColor(255, 193, 94)),
    ("transcribing", QColor(110, 168, 255)),
    ("polishing", QColor(176, 140, 255)),
    ("pasted", QColor(74, 222, 128)),
    ("copied", QColor(74, 222, 128)),
    ("no speech", QColor(251, 191, 36)),
    ("cancelled", QColor(148, 156, 170)),
    ("microphone error", QColor(255, 90, 90)),
    ("error", QColor(255, 90, 90)),
)
BUSY_STATES = ("transcribing", "polishing")

BUTTON_STYLE = (
    "QPushButton { background: rgba(255, 255, 255, 20); color: rgba(255, 255, 255, 226); "
    "border: 1px solid rgba(255, 255, 255, 38); border-radius: 14px; "
    "font: 600 11px 'Segoe UI Symbol'; padding: 0px; }"
    "QPushButton:hover { background: rgba(255, 255, 255, 38); "
    "border-color: rgba(255, 255, 255, 72); }"
    "QPushButton:pressed { background: rgba(255, 255, 255, 14); }"
)

def load_tray_icon() -> QIcon:
    """Use the shipped icon, falling back to a drawn one if it is missing."""
    path = resource_path(ICON_FILE)
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return _drawn_icon()


def _drawn_icon() -> QIcon:
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
    def __init__(self, widget: "StatusWidget", history: History, on_quit) -> None:
        super().__init__(load_tray_icon())
        self.widget = widget
        self.history = history
        self.on_quit = on_quit
        self.setToolTip(f"{APP_NAME} — {TOGGLE_HOTKEY} to dictate, {UI_HOTKEY} to show/hide")

        self.menu = QMenu()
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(widget.toggle_visible)
        self.menu.addAction(show_action)

        self.history_menu = QMenu("Recent transcripts", self.menu)
        self.menu.addMenu(self.history_menu)

        self.menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(quit_action)

        # Rebuilt on open rather than pushed from the worker thread, which keeps
        # all Qt widget mutation on the UI thread.
        self.menu.aboutToShow.connect(self.refresh_history)
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)

    def refresh_history(self) -> None:
        self.history_menu.clear()
        items = self.history.items()
        if not items:
            empty = self.history_menu.addAction("Nothing yet")
            empty.setEnabled(False)
            return

        for text in items:
            label = text if len(text) <= 60 else f"{text[:57]}..."
            action = self.history_menu.addAction(label.replace("&", "&&"))
            action.triggered.connect(lambda _checked=False, value=text: pyperclip.copy(value))

    def on_activated(self, reason) -> None:
        triggers = (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        )
        if reason in triggers:
            self.widget.toggle_visible()

    def quit_app(self) -> None:
        self.on_quit()
        QApplication.quit()


class StatusWidget(QWidget):
    """A compact status card: state dot, elapsed clock, live meter, and a hint.

    Everything except the buttons is painted, so the whole card restyles from the
    constants above and the layout does not fight three nested QLayouts.
    """

    def __init__(self, bus: StatusBus, on_pause, on_cancel) -> None:
        super().__init__()
        self.bus = bus
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(WIDGET_W, WIDGET_H)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.state = "Ready"
        self.detail = ""
        self.kind = "idle"  # idle | live | paused | busy
        self.accent = IDLE_ACCENT
        self.halo = _fade(IDLE_ACCENT, 70)
        self.bar_ink = _fade(IDLE_ACCENT, 110)
        self.rest_ink = _fade(IDLE_ACCENT, 95)
        self.sweep_ink = _fade(IDLE_ACCENT, 150)

        self.wave_values = [WAVE_FLOOR] * BAR_COUNT
        self.smoothed_level = WAVE_FLOOR
        self.phase = 0.0
        self.sweep = 0.0
        self._elapsed_from = 0.0
        self._frozen_elapsed = 0.0
        self._dirty = True
        self._drag_offset: QPoint | None = None

        self.state_font = QFont("Segoe UI Variable Display", 12, QFont.Weight.DemiBold)
        self.clock_font = QFont("Consolas", 10)
        self.detail_font = QFont("Segoe UI Variable Text", 9)
        self.detail_metrics = QFontMetrics(self.detail_font)
        self.state_metrics = QFontMetrics(self.state_font)

        # Absolutely positioned rather than laid out: three fixed circles in the
        # header row, right-aligned, with the two session controls hidden at rest.
        self.pause_button = self._button("⏸", on_pause)
        self.stop_button = self._button("⏹", on_cancel)
        self.hide_button = self._button("✕", self.hide)
        for index, button in enumerate((self.hide_button, self.stop_button, self.pause_button)):
            button.move(SHADOW + CARD_W - 18 - BUTTON_SIZE - index * BUTTON_STEP, SHADOW + 15)
        self.pause_button.setVisible(False)
        self.stop_button.setVisible(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(IDLE_INTERVAL_MS)

    def _button(self, glyph: str, handler) -> QPushButton:
        button = QPushButton(glyph, self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet(BUTTON_STYLE)
        button.clicked.connect(handler)
        return button

    # -- window ---------------------------------------------------------------

    def show_overlay(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 30)
        self.show()
        self.raise_()

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show_overlay()

    def mousePressEvent(self, event) -> None:
        # Drag the card anywhere: it is frameless, so there is no title bar to grab.
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset = None

    # -- state ----------------------------------------------------------------

    def set_status_text(self, state: str, detail: str) -> None:
        """Adopt a new status, deriving the accent colour and clock from it."""
        previous = self.kind
        self.state = state
        self.detail = detail
        self._dirty = True  # A status change is worth one repaint even at rest.
        lowered = state.lower()
        self.accent = next((c for prefix, c in ACCENTS if lowered.startswith(prefix)), IDLE_ACCENT)

        if lowered.startswith("recording"):
            self.kind = "live"
            if previous == "paused":
                self._elapsed_from = time.monotonic() - self._frozen_elapsed
            elif previous != "live":
                self._elapsed_from = time.monotonic()
        elif lowered.startswith("paused"):
            self._frozen_elapsed = time.monotonic() - self._elapsed_from
            self.kind = "paused"
        elif lowered.startswith(BUSY_STATES):
            self.kind = "busy"
        else:
            self.kind = "idle"

        self.halo = _fade(self.accent, 70)
        self.bar_ink = _fade(self.accent, 225 if self.kind == "live" else 150)
        self.rest_ink = _fade(self.accent, 95)
        self.sweep_ink = _fade(self.accent, 150)
        session = self.kind in ("live", "paused")
        self.pause_button.setText("▶" if self.kind == "paused" else "⏸")
        self.pause_button.setVisible(session)
        self.stop_button.setVisible(session)

    def _elapsed(self) -> float:
        if self.kind == "paused":
            return self._frozen_elapsed
        return time.monotonic() - self._elapsed_from

    # -- animation ------------------------------------------------------------

    def tick(self) -> None:
        self._drain_commands()
        self._drain_status()

        if not self.isVisible():
            # Qt delivers no paint events to a hidden widget, so there is nothing
            # to animate for; just keep draining the queues slowly.
            self._set_interval(IDLE_INTERVAL_MS)
            return

        # Paused holds the bars exactly where the recording left them, so the meter
        # reads as held rather than dead, and costs nothing while it waits.
        animating = self.kind in ("live", "busy")
        settling = not animating and self.kind != "paused" and self._wave_is_moving()

        if self.kind == "live":
            self._advance_wave()
        elif animating or settling:
            self._settle_wave()

        if animating:
            self.phase += 0.18
            self.sweep = (self.sweep + 0.032) % 1.0
        if animating or settling or self._dirty:
            self._dirty = False
            self.update()

        self._set_interval(ACTIVE_INTERVAL_MS if animating or settling else IDLE_INTERVAL_MS)

    def _set_interval(self, interval: int) -> None:
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)

    def _drain_commands(self) -> None:
        while True:
            try:
                command = self.bus.commands.get_nowait()
            except queue.Empty:
                return

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

    def _drain_status(self) -> None:
        while True:
            try:
                state, detail = self.bus.status.get_nowait()
            except queue.Empty:
                return
            self.set_status_text(state, detail)

    def _wave_is_moving(self) -> bool:
        return any(abs(value - WAVE_FLOOR) > 0.005 for value in self.wave_values)

    def _advance_wave(self) -> None:
        self.phase += 0.55
        level = max(WAVE_FLOOR, min(1.0, self.bus.level()))
        self.smoothed_level += (level - self.smoothed_level) * 0.28
        base = max(0.14, min(1.0, self.smoothed_level))
        targets = (
            max(WAVE_FLOOR, min(1.0, base * envelope * (0.45 + 0.55 * (0.5 + 0.5 * math.sin(
                self.phase + index * 0.55
            )))))
            for index, envelope in enumerate(ENVELOPE)
        )
        self.wave_values = [
            current + (target - current) * 0.34
            for current, target in zip(self.wave_values, targets)
        ]

    def _settle_wave(self) -> None:
        self.wave_values = [
            current + (WAVE_FLOOR - current) * 0.20 for current in self.wave_values
        ]

    # -- painting -------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRect(SHADOW, SHADOW, CARD_W, CARD_H)
        self._paint_card(painter, card)
        self._paint_header(painter, card)
        self._paint_meter(painter, card)
        self._paint_hint(painter, card)

    def _paint_card(self, painter: QPainter, card: QRect) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        for inset, ink in SHADOW_RINGS:
            painter.setBrush(ink)
            painter.drawRoundedRect(
                card.adjusted(-inset, -inset + 5, inset, inset + 5), RADIUS + inset, RADIUS + inset
            )
        painter.setPen(CARD_BORDER)
        painter.setBrush(CARD_FILL)
        painter.drawRoundedRect(card, RADIUS, RADIUS)

    def _paint_header(self, painter: QPainter, card: QRect) -> None:
        row = QRect(card.left() + 20, card.top() + 14, card.width() - 40, 22)
        centre = QPointF(row.left() + 5.5, row.center().y() + 1)

        painter.setPen(Qt.PenStyle.NoPen)
        if self.kind == "live":
            # A breathing halo, so "recording" is legible from the corner of an eye.
            pulse = 5.5 + 4.0 * (0.5 + 0.5 * math.sin(self.phase * 0.55))
            painter.setBrush(self.halo)
            painter.drawEllipse(centre, pulse, pulse)
        painter.setBrush(self.accent)
        painter.drawEllipse(centre, 4.5, 4.5)

        clock = self._clock_text()
        # isHidden rather than isVisible: it reports this button's own state, so the
        # layout is right even when the card is being rendered off-screen.
        buttons_left = (
            self.pause_button.x() if not self.pause_button.isHidden() else self.hide_button.x()
        )
        if clock:
            painter.setFont(self.clock_font)
            painter.setPen(TIME_INK)
            painter.drawText(
                QRect(row.left(), row.top(), buttons_left - row.left() - 12, row.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                clock,
            )

        room = buttons_left - (row.left() + 20) - (56 if clock else 12)
        painter.setFont(self.state_font)
        painter.setPen(TITLE_INK)
        painter.drawText(
            QRect(row.left() + 20, row.top(), max(40, room), row.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.state_metrics.elidedText(
                self.state, Qt.TextElideMode.ElideRight, max(40, room)
            ),
        )

    def _clock_text(self) -> str:
        if self.kind not in ("live", "paused"):
            return ""
        seconds = int(self._elapsed())
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _paint_meter(self, painter: QPainter, card: QRect) -> None:
        track = QRect(card.left() + 20, card.top() + 46, card.width() - 40, 36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(TRACK_INK)
        painter.drawRoundedRect(track, 13, 13)

        centre_y = track.center().y() + 1
        if self.kind not in ("live", "paused") and not self._wave_is_moving():
            # At rest, 26 bars at the floor read as a dotted line; one continuous
            # line is quieter and makes the sweep below the only moving thing.
            painter.setBrush(self.rest_ink)
            rest = QRect(track.left() + 12, centre_y - 1, track.width() - 24, 3)
            painter.drawRoundedRect(rest, 1.5, 1.5)
        else:
            gap = track.width() / BAR_COUNT
            width = max(3, int(gap * 0.44))
            max_height = track.height() - 10
            painter.setBrush(self.bar_ink)
            for index, value in enumerate(self.wave_values):
                height = max(3, int(value * max_height))
                x = int(track.left() + index * gap + (gap - width) / 2)
                painter.drawRoundedRect(x, centre_y - height // 2, width, height, 2, 2)

        if self.kind == "busy":
            self._paint_sweep(painter, track)

    def _paint_sweep(self, painter: QPainter, track: QRect) -> None:
        """A highlight travelling across the meter while a request is in flight.

        The bars have nothing to say between "stop talking" and "text appears", and
        a frozen meter there read as a hang rather than as work in progress.
        """
        span = track.width() * 0.34
        left = track.left() - span + (track.width() + span) * self.sweep
        gradient = QLinearGradient(left, 0.0, left + span, 0.0)
        gradient.setColorAt(0.0, CLEAR)
        gradient.setColorAt(0.5, self.sweep_ink)
        gradient.setColorAt(1.0, CLEAR)

        # Filling the rounded path directly rather than clipping a rectangle to it:
        # Qt clips without antialiasing, which squared off the sweep's leading edge
        # against the track's corner every time it reached one.
        path = QPainterPath()
        path.addRoundedRect(track, 13, 13)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)

    def _paint_hint(self, painter: QPainter, card: QRect) -> None:
        rect = QRect(card.left() + 21, card.top() + 88, card.width() - 42, 16)
        painter.setFont(self.detail_font)
        painter.setPen(DETAIL_INK)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.detail_metrics.elidedText(
                self.detail or self._default_hint(), Qt.TextElideMode.ElideRight, rect.width()
            ),
        )

    def _default_hint(self) -> str:
        if self.kind in ("live", "paused"):
            return "Esc cancels"
        if self.kind == "busy":
            return ""  # The sweep is the message; a stale hotkey hint is not.
        return f"{TOGGLE_HOTKEY} to dictate"


def _fade(color: QColor, alpha: int) -> QColor:
    """A copy of `color` at `alpha`, computed on state changes rather than per frame."""
    faded = QColor(color)
    faded.setAlpha(alpha)
    return faded










