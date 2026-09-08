"""Floating chat dialog for the deskpet.

Streams a reply from `deepseek_client.chat_stream` into a `QTextBrowser`.
History is kept in memory only; nothing is persisted by default.

UI is deliberately compact (380 x 460) so it doesn't dwarf the pet.
"""

from __future__ import annotations

import threading
import time
from typing import List, Mapping

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

import deepseek_client


# Styling hooks — kept inline so the dialog works without a QSS file.
_USER_STYLE = "color: #1f5fb0; font-weight: 600;"
_BOT_STYLE = "color: #333333;"
_SYSTEM_STYLE = "color: #aa5500; font-style: italic;"
_ERR_STYLE = "color: #c0392b;"


class ChatDialog(QDialog):
    """A minimal chat surface wired to the DeepSeek streaming client."""

    closed = Signal()

    def __init__(self, settings, parent=None, engine=None):
        super().__init__(parent)
        self.setWindowTitle("桌宠 聊天")
        self.setMinimumSize(380, 460)
        self.resize(420, 520)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowStaysOnTopHint
            | Qt.WindowCloseButtonHint
        )

        self._settings = settings
        self._engine = engine
        self._history: List[dict] = []
        self._stop_event = threading.Event()
        self._streaming = False

        self._build_ui()
        self._append_system(
            "输入消息后按 Enter 发送给 "
            + deepseek_client.resolve_config(settings)["model"]
            + "。回复会一边生成一边显示。"
        )

    # -- UI ---------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.history_view = QTextBrowser()
        self.history_view.setOpenExternalLinks(True)
        history_font = QFont()
        history_font.setPointSize(11)
        self.history_view.setFont(history_font)
        layout.addWidget(self.history_view, 1)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("跟 Logos 说点什么…")
        self.input_edit.returnPressed.connect(self._on_send)
        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self._on_send)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.status_label)

    # -- Public API -------------------------------------------------------

    def append_operator_message(self, text: str) -> None:
        """Used by the pet window to surface its own idle chatter."""

        self._history.append({"role": "assistant", "content": text})
        self._render_message("桌宠", text, _BOT_STYLE)

    # -- Send flow --------------------------------------------------------

    def _on_send(self):
        if self._streaming:
            return
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()

        self._history.append({"role": "user", "content": text})
        self._render_message("你", text, _USER_STYLE)

        # Try the offline dialogue script first — short, instant, no API
        # spend. Fall through to DeepSeek only if nothing matched.
        matched = None
        engine = getattr(self, "_engine", None)
        if engine is not None and engine.has_script and self._settings.get(
            "dialogue_enabled", True
        ):
            matched = engine.match(text) or engine.fallback()
        if matched:
            self._history.append({"role": "assistant", "content": matched})
            self._render_message("桌宠", matched, _BOT_STYLE)
            return

        # Pre-seed the bot bubble so streaming text appears immediately.
        self._current_bot_html: List[str] = []
        self._render_message("桌宠", "", _BOT_STYLE, ensure_paragraph=False)
        # Move the cursor into the just-rendered paragraph so stream chunks
        # land in the right place.
        cursor = self.history_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.history_view.setTextCursor(cursor)

        self._set_streaming(True)
        self._stop_event = threading.Event()

        self._thread = deepseek_client.chat_stream(
            self._settings,
            self._history,
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            stop_event=self._stop_event,
        )

    # -- Stream callbacks (run on the worker thread) ---------------------

    def _on_token(self, token: str):
        # Hop back to the Qt thread to mutate the text widget.
        QDialog.__init__  # keep linters from trimming the import on refactor
        # Use a queued connection via signals would be cleaner, but we
        # already are inside a QObject-friendly widget — post via a
        # thread-safe Qt API: invokeMethod on a single-shot signal.
        from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
        QMetaObject.invokeMethod(
            self,
            "_append_token",
            _Qt.QueuedConnection,
            Q_ARG("QString", token),
        )

    def _on_done(self):
        from PySide6.QtCore import QMetaObject, Qt as _Qt
        QMetaObject.invokeMethod(self, "_mark_done", _Qt.QueuedConnection)

    def _on_error(self, message: str):
        from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
        QMetaObject.invokeMethod(
            self,
            "_append_error",
            _Qt.QueuedConnection,
            Q_ARG("QString", message),
        )

    # -- Qt-thread slots --------------------------------------------------

    def _append_token(self, token: str):
        if not hasattr(self, "_current_bot_buffer"):
            self._current_bot_buffer = ""
        self._current_bot_buffer += token
        if not hasattr(self, "_flush_timer") or self._flush_timer is None:
            from PySide6.QtCore import QTimer
            self._flush_timer = QTimer(self)
            self._flush_timer.setInterval(50)  # 20 fps — fast enough to
                                                # look live, gentle on Qt.
            self._flush_timer.timeout.connect(self._flush_pending_tokens)
            self._flush_timer.start()
        # First token after idle: flush immediately so the user sees
        # something happen instead of staring at a blank bubble for 50ms.
        if not getattr(self, "_first_token_pending", False):
            self._first_token_pending = True
            self._flush_pending_tokens()

    def _flush_pending_tokens(self):
        buf = getattr(self, "_current_bot_buffer", "")
        if not buf:
            self._first_token_pending = False
            return
        cursor = self.history_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(buf)
        self.history_view.setTextCursor(cursor)
        self.history_view.ensureCursorVisible()
        self._current_bot_buffer = ""
        self._first_token_pending = False
        # Once we've drained the buffer, stop the timer until the next
        # batch of tokens arrives.
        if self._flush_timer is not None:
            self._flush_timer.stop()

    def _mark_done(self):
        # Flush whatever is still pending so we don't lose the tail of the
        # response, then commit the final text into history.
        self._flush_pending_tokens()
        buf = getattr(self, "_current_bot_buffer", "")
        if buf:
            self._history.append({"role": "assistant", "content": buf})
            self._current_bot_buffer = ""
        self._set_streaming(False)
        self.status_label.setText("就绪")

    def _append_error(self, message: str):
        # Drop any pending stream buffer so the error message is the last
        # thing the user sees in the bubble.
        self._flush_pending_tokens()
        self._render_message("错误", message, _ERR_STYLE)
        if self._streaming:
            self._set_streaming(False)
        self.status_label.setText("出错")

    # -- Rendering helpers -----------------------------------------------

    def _render_message(self, who: str, text: str, style: str, *, ensure_paragraph: bool = True):
        cursor = self.history_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if ensure_paragraph:
            timestamp = time.strftime("%H:%M")
            html = (
                f'<div style="margin: 6px 0 2px 0;"><span style="{style}">'
                f"[{timestamp}] {who}：</span></div>"
                f'<div style="margin: 0 0 8px 0; white-space: pre-wrap; {style}">'
                f"{self._escape(text)}</div>"
            )
            cursor.insertHtml(html)
        else:
            cursor.insertHtml(
                f'<div style="margin: 0 0 8px 0; white-space: pre-wrap; {style}">'
                f"<span>{self._escape(text)}</span></div>"
            )
        self.history_view.setTextCursor(cursor)
        self.history_view.ensureCursorVisible()

    def _append_system(self, text: str):
        self._render_message("系统", text, _SYSTEM_STYLE)

    @staticmethod
    def _escape(text: str) -> str:
        amp = chr(38) + "amp"
        lt = chr(38) + "lt"
        gt = chr(38) + "gt"
        return (
            text.replace("&", amp)
            .replace("<", lt)
            .replace(">", gt)
            .replace("\n", "<br/>")
        )

    def _set_streaming(self, streaming: bool):
        self._streaming = streaming
        self.send_button.setEnabled(not streaming)
        self.input_edit.setReadOnly(streaming)
        if streaming:
            self.status_label.setText("正在生成…")

    # -- Lifecycle --------------------------------------------------------

    def reject(self):
        self._stop_event.set()
        super().reject()

    def closeEvent(self, event: QEvent):
        self._stop_event.set()
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
