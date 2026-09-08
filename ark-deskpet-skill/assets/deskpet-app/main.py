import atexit
import json
import os
import random
import sys
import time

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

import workbuddy_monitor as host_monitor
from _platform import is_foreground_fullscreen, pythonw_binary, set_autostart as _platform_set_autostart

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PETS_DIR = os.path.join(BASE_DIR, "pets")
ERROR_LOG = os.path.join(BASE_DIR, "pet_error.log")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
PID_FILE = os.path.join(BASE_DIR, "pet.pid")
SHUTDOWN_FLAG = os.path.join(BASE_DIR, "pet_shutdown.flag")
DISABLED_FLAG = os.path.join(BASE_DIR, "pet_disabled.flag")
SHOW_FLAG = os.path.join(BASE_DIR, "pet_show.flag")
HIDE_FLAG = os.path.join(BASE_DIR, "pet_hide.flag")
WATCHER_PATH = os.path.join(BASE_DIR, "pet_launcher.pyw")
PYW_PATH = pythonw_binary(BASE_DIR)

PAD = 12
STATUS_H = 46
MIN_SCALE = 0.3
MAX_SCALE = 2.0

SPEED_OPTIONS = [
    ("0.5x", 0.5),
    ("0.75x", 0.75),
    ("1.0x", 1.0),
    ("1.25x", 1.25),
    ("1.5x", 1.5),
]

SUBTITLE_LEVELS = {
    "short": {
        "label": "简短",
        "task_limit": 14,
        "show_model": False,
        "show_progress": False,
    },
    "medium": {
        "label": "标准",
        "task_limit": 36,
        "show_model": True,
        "show_progress": False,
    },
    "long": {
        "label": "详细",
        "task_limit": 80,
        "show_model": True,
        "show_progress": True,
    },
}

DEFAULT_SETTINGS = {
    "speed": 1.0,
    "subtitle_length": "medium",
    "subtitle_size": 19,
    "bar_length": 100,
    "mini_mode": False,
    "auto_hide_fullscreen": False,
    "locked": True,
    "scale": 1.0,
    "pos_x": None,
    "pos_y": None,
    "pet": None,
    "pet_states": {},
    "autostart_with_host": False,
    "host_processes": None,
    "session_paths": None,
}


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data


def save_settings(data):
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def list_pets():
    pets = []
    if not os.path.isdir(PETS_DIR):
        return pets
    for name in sorted(os.listdir(PETS_DIR)):
        if os.path.isfile(os.path.join(PETS_DIR, name, "manifest.json")):
            pets.append(name)
    return pets


def resolve_active_pet(settings):
    pets = list_pets()
    name = settings.get("pet")
    if name in pets:
        return name
    return pets[0] if pets else None


_initial_settings = load_settings()
ACTIVE_PET = resolve_active_pet(_initial_settings)
FRAMES_DIR = os.path.join(PETS_DIR, ACTIVE_PET, "frames")
MANIFEST_PATH = os.path.join(PETS_DIR, ACTIVE_PET, "manifest.json")

with open(MANIFEST_PATH, encoding="utf-8") as f:
    MANIFEST = json.load(f)

FPS = int(MANIFEST["fps"])


def switch_pet(name):
    global ACTIVE_PET, FRAMES_DIR, MANIFEST_PATH, MANIFEST, FPS
    if name not in list_pets():
        return False
    ACTIVE_PET = name
    FRAMES_DIR = os.path.join(PETS_DIR, name, "frames")
    MANIFEST_PATH = os.path.join(PETS_DIR, name, "manifest.json")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        MANIFEST = json.load(f)
    FPS = int(MANIFEST["fps"])
    return True


def set_autostart(enabled):
    """Delegate to the platform-specific implementation in ``_platform``.

    Always also cleans up the legacy ``ArkDeskpetAutoStart.vbs`` shim from
    old Windows installs, regardless of whether we are turning autostart
    on or off.
    """
    if _legacy_vbs_cleanup_eligible():
        legacy = legacy_startup_entry_path()
        try:
            if os.path.exists(legacy):
                os.remove(legacy)
        except OSError:
            pass
    return _platform_set_autostart(
        bool(enabled),
        python_path=PYW_PATH,
        launcher_path=WATCHER_PATH,
        project_dir=BASE_DIR,
    )


def chatter_configured(settings):
    """True iff the user has supplied a DeepSeek API key."""

    return bool((settings.get("deepseek_api_key") or "").strip())


def _legacy_vbs_cleanup_eligible():
    """Only Windows hosts ever wrote the legacy VBS file."""
    import sys as _sys
    return _sys.platform == "win32"


def legacy_startup_entry_path():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
        "ArkDeskpetAutoStart.vbs",
    )


def remove_pid_file():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def remove_disabled_flag():
    try:
        os.remove(DISABLED_FLAG)
    except OSError:
        pass


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("明日方舟 桌宠 设置")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.speed_combo = QComboBox()
        for label, value in SPEED_OPTIONS:
            self.speed_combo.addItem(label, value)
        self.speed_combo.setCurrentIndex(
            self._index_for_value(settings.get("speed", 1.0))
        )

        self.subtitle_combo = QComboBox()
        for key, info in SUBTITLE_LEVELS.items():
            self.subtitle_combo.addItem(info["label"], key)
        self.subtitle_combo.setCurrentIndex(
            self._index_for_key(settings.get("subtitle_length", "medium"))
        )

        self.autostart_check = QCheckBox(
            "随 WorkBuddy 启动（登录后监听，检测到 WorkBuddy 再启动桌宠）"
        )
        self.autostart_check.setChecked(
            bool(settings.get("autostart_with_host", settings.get("autostart_with_codex", False)))
        )

        self.mini_check = QCheckBox("迷你模式（隐藏字幕条）")
        self.mini_check.setChecked(bool(settings.get("mini_mode", False)))
        self.fullscreen_check = QCheckBox("全屏应用时自动隐藏")
        self.fullscreen_check.setChecked(
            bool(settings.get("auto_hide_fullscreen", False))
        )
        self.dialogue_check = QCheckBox("启用本地对话（待机气泡 + 触发词匹配，零 API 消耗）")
        self.dialogue_check.setChecked(bool(settings.get("dialogue_enabled", True)))

        # ---- Chatter (DeepSeek) settings ------------------------------
        self.chatter_check = QCheckBox("启用聊天（右键菜单加 \"聊天...\"）")
        self.chatter_check.setChecked(bool(settings.get("chatter_enabled", False)))

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setText(settings.get("deepseek_api_key", "") or "")
        self.api_key_edit.setPlaceholderText("sk-...（去 https://platform.deepseek.com 申请）")

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText(
            settings.get("deepseek_base_url", "") or "https://api.deepseek.com/v1"
        )
        self.base_url_edit.setPlaceholderText("默认 https://api.deepseek.com/v1")

        self.model_edit = QLineEdit()
        self.model_edit.setText(settings.get("deepseek_model", "") or "deepseek-chat")
        self.model_edit.setPlaceholderText("默认 deepseek-chat")

        self.system_prompt_edit = QLineEdit()
        self.system_prompt_edit.setText(settings.get("deepseek_system_prompt", "") or "")
        self.system_prompt_edit.setPlaceholderText(
            "可选：例如 你是 Logos，干员。1-2 句内回答。"
        )

        api_key_row = QWidget()
        api_key_layout = QHBoxLayout(api_key_row)
        api_key_layout.setContentsMargins(0, 0, 0, 0)
        api_key_layout.addWidget(self.api_key_edit, 1)
        self.show_key_check = QCheckBox("显示")
        self.show_key_check.toggled.connect(self._toggle_key_visibility)
        api_key_layout.addWidget(self.show_key_check)

        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(14, 26)
        self.size_slider.setValue(int(settings.get("subtitle_size", 19)))
        self.size_value = QLabel(f"{self.size_slider.value()}px")
        self.size_slider.valueChanged.connect(
            lambda value: self.size_value.setText(f"{value}px")
        )
        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.size_slider, 1)
        size_layout.addWidget(self.size_value)

        self.bar_slider = QSlider(Qt.Horizontal)
        self.bar_slider.setRange(40, 100)
        self.bar_slider.setValue(int(settings.get("bar_length", 100)))
        self.bar_value = QLabel(f"{self.bar_slider.value()}%")
        self.bar_slider.valueChanged.connect(
            lambda value: self.bar_value.setText(f"{value}%")
        )
        bar_row = QWidget()
        bar_layout = QHBoxLayout(bar_row)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.addWidget(self.bar_slider, 1)
        bar_layout.addWidget(self.bar_value)

        form.addRow("动作倍速", self.speed_combo)
        form.addRow("字幕长度", self.subtitle_combo)
        form.addRow("字幕大小", size_row)
        form.addRow("字条长度", bar_row)
        form.addRow("", self.mini_check)
        form.addRow("", self.fullscreen_check)
        form.addRow("", self.dialogue_check)
        form.addRow("", self.autostart_check)
        layout.addLayout(form)

        layout.addWidget(self._separator_label("聊天（DeepSeek）"))
        chat_form = QFormLayout()
        chat_form.addRow("", self.chatter_check)
        chat_form.addRow("API Key", api_key_row)
        chat_form.addRow("Base URL", self.base_url_edit)
        chat_form.addRow("模型", self.model_edit)
        chat_form.addRow("System Prompt", self.system_prompt_edit)
        layout.addLayout(chat_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _separator_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-weight: 600; margin-top: 6px;")
        return label

    def _toggle_key_visibility(self, show):
        self.api_key_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)

    @staticmethod
    def _index_for_value(value):
        for i, (_, speed) in enumerate(SPEED_OPTIONS):
            if abs(speed - float(value)) < 1e-6:
                return i
        return 2

    @staticmethod
    def _index_for_key(key):
        keys = list(SUBTITLE_LEVELS.keys())
        return keys.index(key) if key in keys else 1

    def values(self):
        return {
            "speed": self.speed_combo.currentData(),
            "subtitle_length": self.subtitle_combo.currentData(),
            "subtitle_size": self.size_slider.value(),
            "bar_length": self.bar_slider.value(),
            "mini_mode": self.mini_check.isChecked(),
            "auto_hide_fullscreen": self.fullscreen_check.isChecked(),
            "autostart_with_host": self.autostart_check.isChecked(),
            "dialogue_enabled": self.dialogue_check.isChecked(),
            "chatter_enabled": self.chatter_check.isChecked(),
            "deepseek_api_key": self.api_key_edit.text().strip(),
            "deepseek_base_url": self.base_url_edit.text().strip(),
            "deepseek_model": self.model_edit.text().strip(),
            "deepseek_system_prompt": self.system_prompt_edit.text().strip(),
        }


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)

        self.settings = load_settings()
        self.pet_name = ACTIVE_PET
        pet_states = self.settings.get("pet_states") or {}
        pet_state = pet_states.get(self.pet_name, {})
        self.pet_state = pet_state
        self.speed = float(
            pet_state.get("speed", self.settings.get("speed", 1.0))
        )
        self.show_status = not bool(self.settings.get("mini_mode", False))
        self.auto_hide_fullscreen = bool(
            self.settings.get("auto_hide_fullscreen", False)
        )
        self.subtitle_length = self.settings.get("subtitle_length", "medium")
        self.subtitle_size = max(
            14, min(26, int(self.settings.get("subtitle_size", 19)))
        )
        self.bar_length = max(
            40, min(100, int(self.settings.get("bar_length", 100)))
        )
        self.locked = bool(self.settings.get("locked", True))

        self.state = "idle"
        self.frame_index = 0
        self.scale = max(
            MIN_SCALE,
            min(
                MAX_SCALE,
                float(
                    pet_state.get(
                        "scale", self.settings.get("scale", 1.0)
                    )
                ),
            ),
        )
        self.cache = {}
        self._state_cache = {"state": None, "frames": []}  # per-state decoded frames
        self.drag = False
        self.pre_drag_state = "idle"
        self.pre_drag_hold = False
        self.hold_state = False
        self.press_global = None
        self.press_window = None
        self.press_time = 0
        self.status_text = "WorkBuddy 待机"
        self.status_active = False
        self.tray_hidden = False
        self._chat_dialog = None
        self._last_task_signature = None  # tracks (task, last_finished) for chatter
        self._last_active = None  # tracks WorkBuddy idle<->active for status_reactions
        self._has_greeted = False  # one-shot greeting on first observation
        self._last_idle_trigger = 0.0

        # ---- Dialogue + speech bubble -----------------------------------
        self._init_dialogue()
        self._bubble = None  # created lazily on first show
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)

        self._idle_chatter_timer = QTimer(self)
        self._idle_chatter_timer.setInterval(60_000)  # 60s
        self._idle_chatter_timer.timeout.connect(self._on_idle_chatter)
        self._idle_chatter_timer.start()

        self.timer = QTimer(self)
        # PreciseTimer gives us tight 50ms ticks; default CoarseTimer
        # can wander by 5-10ms, which is 10-20% jitter at 20fps.
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.tick_ms())
        self.timer.timeout.connect(self.next_frame)
        self.timer.start()

        self.sit_timer = QTimer(self)
        self.sit_timer.setSingleShot(True)
        self.sit_timer.timeout.connect(
            lambda: self.set_state("sit", hold=True)
        )

        self.sleep_timer = QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.timeout.connect(
            lambda: self.set_state("sleep", hold=True)
        )

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(2000)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start()

        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.setInterval(2000)
        self.fullscreen_timer.timeout.connect(self.check_fullscreen)
        self.fullscreen_timer.start()

        self.set_state("idle")
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pos_x = pet_state.get("pos_x")
        if pos_x is None:
            pos_x = self.settings.get("pos_x")
        pos_y = pet_state.get("pos_y")
        if pos_y is None:
            pos_y = self.settings.get("pos_y")
        if pos_x is not None and pos_y is not None:
            pos_x = int(pos_x)
            pos_y = int(pos_y)
            pos_x = max(
                screen.x() - self.width() + 60,
                min(pos_x, screen.x() + screen.width() - 60),
            )
            pos_y = max(
                screen.y() - self.height() + 60,
                min(pos_y, screen.y() + screen.height() - 60),
            )
            self.move(pos_x, pos_y)
        else:
            self.move(
                screen.x() + (screen.width() - self.width()) // 2,
                screen.y() + screen.height() - self.height(),
            )
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.save_position)
        self.refresh_status()
        self.show()

    def tick_ms(self):
        return max(10, int(round(1000 / FPS / self.speed)))

    def state_info(self, name):
        return MANIFEST["states"][name]

    def apply_geometry(self):
        info = self.state_info(self.state)
        old_x, old_y = self.x(), self.y()
        old_w, old_h = self.width(), self.height()
        bx, by, bx2, by2 = info["bbox"]
        width = int((bx2 - bx + 1) * self.scale) + PAD * 2
        status_extra = STATUS_H if self.show_status else 0
        height = int((by2 - by + 1) * self.scale) + PAD * 2 + status_extra
        self.resize(width, height)
        bottom_center_x = old_x + old_w / 2
        bottom_y = old_y + old_h
        self.move(
            int(bottom_center_x - width / 2),
            int(bottom_y - height),
        )

    def set_state(self, name, hold=False):
        if name not in MANIFEST["states"]:
            return
        self.state = name
        self.hold_state = hold
        self.frame_index = 0
        self.cache.clear()
        # Force _load_state_cache to run on next paint so we get a fresh
        # batch of decoded frames for the new state.
        self._state_cache = {"state": None, "frames": []}
        self.apply_geometry()
        self.schedule_idle()
        self.update()

    def schedule_idle(self):
        self.sit_timer.stop()
        self.sleep_timer.stop()
        if self.state == "sleep":
            return
        self.sit_timer.start(40000 + random.randint(0, 20000))
        self.sleep_timer.start(90000)

    def frame_path(self, index):
        pad = str(index).zfill(4)
        return os.path.join(FRAMES_DIR, self.state, f"frame_{pad}.png")

    def frame_path(self, index):
        pad = str(index).zfill(4)
        return os.path.join(FRAMES_DIR, self.state, f"frame_{pad}.png")

    def current_image(self):
        """Return the QImage for the current frame, decoding on demand.

        Caches all frames of the *current* state in memory after the
        first paint. The old single-frame cache (size 5) thrashed for
        animations with more than 5 frames — every state here has
        16-171 frames, so the old cache nearly always missed and we
        paid 5-15ms of PNG decoding on every tick.
        """
        if self._state_cache.get("state") != self.state:
            self._load_state_cache(self.state)
        cache = self._state_cache.get("frames")
        if not cache:
            return QImage()
        return cache[self.frame_index % len(cache)]

    def _load_state_cache(self, state):
        """Load all frames of `state` into memory in a worker thread.

        A blocking first decode (current frame) lets us paint right
        away; the rest are decoded in the background and dropped into
        the cache when ready. This avoids a 1-2 second freeze on
        transitions to long states (sleep has 171 frames).
        """
        # Render the first frame right now so the user never sees a
        # blank pet; the rest will replace the cache as they decode.
        first = QImage(self.frame_path(0))
        self._state_cache = {
            "state": state,
            "frames": [first] if not first.isNull() else [],
        }
        self.frame_index = min(self.frame_index, max(0, len(self._state_cache["frames"]) - 1))
        self.update()
        # Schedule the rest in the background.
        if not first.isNull():
            self._start_state_preload(state)

    def _start_state_preload(self, state):
        """Kick off a background QThread to decode remaining frames."""
        from PySide6.QtCore import QThread, Signal

        count = self.state_info(state)["count"]
        if count <= 1:
            return  # already done

        preloader = _FramePreloader(state, count, self.frame_path)
        preloader.frame_ready.connect(self._on_preload_frame)
        preloader.finished.connect(preloader.deleteLater)
        # Keep a strong reference until it's done — without this the
        # thread's QObject gets garbage-collected mid-run.
        self._preloader = preloader
        preloader.start()

    def _on_preload_frame(self, state, index, image):
        """Slot called from the worker thread for each decoded frame."""
        if state != self.state:
            return  # user already switched states; drop on the floor
        cache = self._state_cache.setdefault("frames", [])
        if index < len(cache):
            # Already painted this index (frame 0); just upgrade it.
            cache[index] = image
        else:
            cache.append(image)
        # If we're currently looking at this frame, repaint.
        if index == self.frame_index:
            self.update()

    def frame_path(self, index):
        pad = str(index).zfill(4)
        return os.path.join(FRAMES_DIR, self.state, f"frame_{pad}.png")

    def next_frame(self):
        info = self.state_info(self.state)
        count = info["count"]
        if self.state == "sleep":
            if not self.hold_state and self.frame_index >= count - 1:
                self.update()
                return
            self.frame_index = (self.frame_index + 1) % count
        elif self.state in ("interact", "sit"):
            if not self.hold_state and self.frame_index >= count - 1:
                self.set_state("idle")
                return
            self.frame_index = (self.frame_index + 1) % count
        else:
            self.frame_index = (self.frame_index + 1) % count
        self.update()

    def paintEvent(self, event):
        info = self.state_info(self.state)
        bx, by, _, _ = info["bbox"]
        image = self.current_image()
        painter = QPainter(self)
        # FastPixmapTransform is ~3-5x faster than SmoothPixmapTransform
        # and at typical pet scale (0.5-1.0) the difference is invisible
        # to the eye. The old setting was the biggest single cause of
        # visible stutter on the 20fps ticker.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        status_extra = STATUS_H if self.show_status else 0
        if not image.isNull():
            target = QRectF(
                PAD - bx * self.scale,
                status_extra + PAD - by * self.scale,
                image.width() * self.scale,
                image.height() * self.scale,
            )
            painter.drawImage(target, image)

        if self.show_status:
            bar_width = max(
                120, int((self.width() - 12) * self.bar_length / 100.0)
            )
            bar = QRectF(6, 4, bar_width, STATUS_H - 8)
            if self.status_active:
                painter.setBrush(QColor(30, 120, 70, 190))
            else:
                painter.setBrush(QColor(25, 25, 25, 170))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar, 8, 8)

            font = QFont()
            font.setPixelSize(self.subtitle_size)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            elided = metrics.elidedText(
                self.status_text, Qt.ElideRight, int(bar.width() - 16)
            )
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                bar.adjusted(8, 0, -8, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                elided,
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag = False
            self.pre_drag_state = self.state
            self.pre_drag_hold = self.hold_state
            self.press_global = event.globalPosition().toPoint()
            self.press_window = self.pos()
            self.press_time = time.monotonic()

    def mouseMoveEvent(self, event):
        if self.press_global is None:
            return
        if self.locked:
            return
        current = event.globalPosition().toPoint()
        dx = current.x() - self.press_global.x()
        dy = current.y() - self.press_global.y()
        if not self.drag and (dx * dx + dy * dy) > 36:
            self.drag = True
            self.sit_timer.stop()
            self.sleep_timer.stop()
            if self.state != "move":
                self.set_state("move")
        if self.drag and not (event.buttons() & Qt.LeftButton):
            self.drag = False
            self.press_global = None
            self.press_window = None
            target = (
                self.pre_drag_state
                if self.pre_drag_state in MANIFEST["states"]
                else "idle"
            )
            self.set_state(target, hold=self.pre_drag_hold)
        elif self.drag:
            self.move(self.press_window.x() + dx, self.press_window.y() + dy)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.drag:
            self.drag = False
            self.press_global = None
            self.press_window = None
            target = (
                self.pre_drag_state
                if self.pre_drag_state in MANIFEST["states"]
                else "idle"
            )
            self.set_state(target, hold=self.pre_drag_hold)
            self.save_pet_state()
            return
        if self.press_global is None:
            return
        current = event.globalPosition().toPoint()
        moved = (current.x() - self.press_global.x()) ** 2 + (
            current.y() - self.press_global.y()
        ) ** 2
        held = time.monotonic() - self.press_time
        self.press_global = None
        self.press_window = None
        if held < 0.5 and moved < 36:
            self.set_state("interact")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_mini()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction(
            QAction(
                "坐下",
                self,
                triggered=lambda: self.set_state("sit", hold=True),
            )
        )
        menu.addAction(
            QAction(
                "放松",
                self,
                triggered=lambda: self.set_state("idle", hold=True),
            )
        )
        menu.addAction(
            QAction(
                "睡觉",
                self,
                triggered=lambda: self.set_state("sleep", hold=True),
            )
        )
        menu.addSeparator()
        pet_menu = menu.addMenu("桌宠库")
        for name in list_pets():
            action = QAction(name, self, checkable=True)
            action.setChecked(name == self.pet_name)
            action.triggered.connect(
                lambda checked=False, n=name: self.select_pet(n)
            )
            pet_menu.addAction(action)
        menu.addSeparator()
        mini_action = QAction("迷你模式（隐藏字幕）", self, checkable=True)
        mini_action.setChecked(not self.show_status)
        mini_action.triggered.connect(self.toggle_mini)
        menu.addAction(mini_action)
        full_action = QAction("全屏应用时自动隐藏", self, checkable=True)
        full_action.setChecked(self.auto_hide_fullscreen)
        full_action.triggered.connect(self.toggle_fullscreen_auto_hide)
        menu.addAction(full_action)
        menu.addSeparator()
        menu.addAction(
            QAction(
                "解锁拖动" if self.locked else "锁定拖动",
                self,
                triggered=self.toggle_lock,
            )
        )
        menu.addSeparator()
        if chatter_configured(self.settings):
            chat_label = (
                "聊天..." if self.settings.get("chatter_enabled", False)
                else "聊天...（未启用，先去设置勾选）"
            )
        else:
            chat_label = "聊天...（未配置 API Key）"
        chat_action = QAction(chat_label, self)
        chat_action.setEnabled(bool(self.settings.get("chatter_enabled", False)))
        chat_action.triggered.connect(self.open_chat)
        menu.addAction(chat_action)
        menu.addAction(QAction("设置...", self, triggered=self.open_settings))
        menu.addSeparator()
        menu.addAction(QAction("放大", self, triggered=self.scale_up))
        menu.addAction(QAction("缩小", self, triggered=self.scale_down))
        menu.addSeparator()
        menu.addAction(
            QAction("隐藏到托盘", self, triggered=self.hide_to_tray)
        )
        menu.addAction(
            QAction("完全退出", self, triggered=self.quit_pet)
        )
        menu.exec(event.globalPos())

    def scale_up(self):
        self.set_scale(self.scale + 0.1)

    def scale_down(self):
        self.set_scale(self.scale - 0.1)

    def set_scale(self, value):
        self.scale = max(MIN_SCALE, min(MAX_SCALE, round(value, 1)))
        self.apply_geometry()
        self.settings["scale"] = self.scale
        self.save_pet_state()
        self.update()

    def select_pet(self, name):
        if name == self.pet_name or not switch_pet(name):
            return
        self.save_pet_state()
        self.pet_name = name
        self.settings["pet"] = name
        pet_state = (self.settings.get("pet_states") or {}).get(name, {})
        self.scale = max(
            MIN_SCALE,
            min(
                MAX_SCALE,
                float(
                    pet_state.get(
                        "scale", self.settings.get("scale", 1.0)
                    )
                ),
            ),
        )
        self.speed = float(
            pet_state.get("speed", self.settings.get("speed", 1.0))
        )
        self.cache.clear()
        self.timer.setInterval(self.tick_ms())
        self.set_state("idle", hold=False)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pos_x = pet_state.get("pos_x")
        if pos_x is None:
            pos_x = self.settings.get("pos_x")
        pos_y = pet_state.get("pos_y")
        if pos_y is None:
            pos_y = self.settings.get("pos_y")
        if pos_x is not None and pos_y is not None:
            pos_x = max(
                screen.x() - self.width() + 60,
                min(int(pos_x), screen.x() + screen.width() - 60),
            )
            pos_y = max(
                screen.y() - self.height() + 60,
                min(int(pos_y), screen.y() + screen.height() - 60),
            )
            self.move(pos_x, pos_y)
        else:
            self.move(
                screen.x() + (screen.width() - self.width()) // 2,
                screen.y() + screen.height() - self.height(),
            )
        self.refresh_status()
        self.update()

    def save_pet_state(self):
        pet_states = self.settings.setdefault("pet_states", {})
        pet_states[self.pet_name] = {
            "scale": self.scale,
            "speed": self.speed,
            "pos_x": self.x(),
            "pos_y": self.y(),
        }
        self.settings["scale"] = self.scale
        self.settings["pos_x"] = self.x()
        self.settings["pos_y"] = self.y()
        save_settings(self.settings)

    def save_position(self):
        self.save_pet_state()

    def toggle_mini(self):
        self.show_status = not self.show_status
        self.settings["mini_mode"] = not self.show_status
        save_settings(self.settings)
        self.apply_geometry()
        self.update()

    def toggle_fullscreen_auto_hide(self):
        self.auto_hide_fullscreen = not self.auto_hide_fullscreen
        self.settings["auto_hide_fullscreen"] = self.auto_hide_fullscreen
        save_settings(self.settings)
        self.check_fullscreen()

    def check_fullscreen(self):
        if self.tray_hidden:
            return
        if not self.auto_hide_fullscreen:
            if not self.isVisible():
                self.show()
            return
        # macOS / Linux can't easily query the foreground window by HWND, so
        # ``is_foreground_fullscreen`` does its own per-platform check. On those
        # platforms we always assume the foreground is *not* our own window
        # (Qt widgets don't expose a stable HWND equivalent), so a simple
        # cover-the-screen test is sufficient.
        full = is_foreground_fullscreen()
        if full:
            self.hide()
        elif not self.isVisible():
            self.show()

    def hide_to_tray(self):
        self.tray_hidden = True
        self.hide()

    def show_from_tray(self):
        self.tray_hidden = False
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_pet(self):
        try:
            with open(DISABLED_FLAG, "w", encoding="utf-8") as f:
                f.write("1")
        except OSError:
            pass
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def toggle_lock(self):
        self.locked = not self.locked
        self.settings["locked"] = self.locked
        save_settings(self.settings)
        self.drag = False
        self.press_global = None
        self.press_window = None

    def open_chat(self):
        if not bool(self.settings.get("chatter_enabled", False)):
            QMessageBox.information(
                self,
                "明日方舟 桌宠",
                "聊天未启用。请先在 设置... 里勾选「启用聊天」，并填好 API Key。",
            )
            return
        if not chatter_configured(self.settings):
            QMessageBox.information(
                self,
                "明日方舟 桌宠",
                "尚未配置 DeepSeek API Key。请在 设置... 里填写后再试。",
            )
            return
        import chat_dialog
        if self._chat_dialog is None or not self._chat_dialog.isVisible():
            self._chat_dialog = chat_dialog.ChatDialog(
                self.settings, self, engine=self._engine
            )
        # Anchor the dialog near the pet so it doesn't fly off-screen.
        anchor = self.mapToGlobal(self.rect().topRight())
        self._chat_dialog.move(anchor.x() + 12, max(40, anchor.y() - 60))
        self._chat_dialog.show()
        self._chat_dialog.raise_()
        self._chat_dialog.activateWindow()

    def open_settings(self):
        self.settings["speed"] = self.speed
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.values()
        old_autostart = bool(self.settings.get("autostart_with_host", self.settings.get("autostart_with_codex", False)))
        merged = dict(self.settings)
        merged.update(data)
        self.settings = merged
        save_settings(merged)
        self.speed = float(data["speed"])
        self.subtitle_length = data["subtitle_length"]
        self.subtitle_size = int(data["subtitle_size"])
        self.bar_length = int(data["bar_length"])
        self.show_status = not bool(data["mini_mode"])
        self.auto_hide_fullscreen = bool(data["auto_hide_fullscreen"])
        self.timer.setInterval(self.tick_ms())
        new_autostart = bool(data["autostart_with_host"])
        if new_autostart != old_autostart:
            if not set_autostart(new_autostart):
                QMessageBox.warning(
                    self,
                    "明日方舟 桌宠",
                    "随 WorkBuddy 启动设置写入失败，请检查系统权限。",
                )
        # Drop the legacy key once we've replaced it.
        self.settings.pop("autostart_with_codex", None)
        # Refresh the live chat dialog if it is open.
        if self._chat_dialog is not None:
            self._chat_dialog._settings = self.settings
        self.save_pet_state()
        self.refresh_status()
        self.update()

    @staticmethod
    def _cut(text, limit):
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)] + "…"

    @staticmethod
    def _format_elapsed(seconds):
        seconds = int(seconds)
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}小时{minutes}分"
        if minutes:
            return f"{minutes}分{sec}秒"
        return f"{sec}秒"

    @staticmethod
    def _format_tokens(count):
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}k"
        return str(count)

    def refresh_status(self):
        if os.path.exists(HIDE_FLAG):
            try:
                os.remove(HIDE_FLAG)
            except OSError:
                pass
            self.hide_to_tray()
        if os.path.exists(SHOW_FLAG):
            try:
                os.remove(SHOW_FLAG)
            except OSError:
                pass
            self.show_from_tray()
        if os.path.exists(SHUTDOWN_FLAG):
            try:
                os.remove(SHUTDOWN_FLAG)
            except OSError:
                pass
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return
        status = host_monitor.get_host_status()
        self.status_active = bool(status.get("active"))
        level = SUBTITLE_LEVELS.get(
            self.subtitle_length, SUBTITLE_LEVELS["medium"]
        )
        if self.status_active:
            base = "WorkBuddy 运行中"
        else:
            base = "WorkBuddy 待机"
        parts = [base]
        if self.status_active:
            elapsed = status.get("elapsed")
            if elapsed is not None:
                parts.append(f"已运行 {self._format_elapsed(elapsed)}")
            tokens = status.get("tokens")
            if tokens is not None:
                parts.append(f"Token {self._format_tokens(tokens)}")
        task = status.get("task")
        if task:
            parts.append(self._cut(task, level["task_limit"]))
        if level["show_model"]:
            model = status.get("model")
            if model:
                parts.append(f"模型 {self._cut(model, 24)}")
        if level["show_progress"]:
            last_finished = status.get("last_finished")
            if last_finished:
                parts.append(f"上次完成 {last_finished}")
            progress = status.get("progress")
            if progress:
                parts.append(self._cut(progress, 80))
        self.status_text = " · ".join(parts)
        self.update()

        # Dialogue reactions to WorkBuddy lifecycle changes. Logos doesn't
        # announce every micro-task flip; he just notes when the doctor's
        # state itself changes (idle <-> active).
        if self._dialogue_enabled():
            was_active = bool(self._last_active)
            is_active = self.status_active
            self._last_active = is_active
            if was_active != is_active:
                key = "went_active" if is_active else "went_idle"
                line = self._engine.pick_reaction(key) or self._engine.fallback()
                if line:
                    self.show_bubble(line)
            # First observation ever: open with a greeting.
            if not self._has_greeted:
                self._has_greeted = True
                greet = self._engine.pick_weighted("greetings") or self._engine.fallback()
                if greet:
                    # Defer a beat so the pet finishes painting first.
                    QTimer.singleShot(800, lambda: self.show_bubble(greet, duration_ms=5000))

    # ---- Dialogue + speech bubble ---------------------------------------

    def _init_dialogue(self):
        import dialogue
        pet_dir = os.path.join(PETS_DIR, self.pet_name)
        self._engine = dialogue.build_engine_for_pet(pet_dir)
        # If this pet has no dialogue.json we still want self._engine to
        # exist so the rest of the code can call methods on it safely.
        if not self._engine.has_script:
            self._engine = dialogue.DialogueEngine(
                {
                    "idle": ["……", "嗯。"],
                    "fallback": ["嗯。"],
                }
            )

    def _dialogue_enabled(self) -> bool:
        return bool(self.settings.get("dialogue_enabled", True))

    def _on_idle_chatter(self):
        if not self._dialogue_enabled():
            return
        if not self.isVisible():
            return
        line = self._engine.pick_weighted("idle") or self._engine.fallback()
        if line:
            self.show_bubble(line)

    def show_bubble(self, text: str, duration_ms: int = 5000):
        """Show a speech bubble above the pet for `duration_ms` milliseconds.

        Auto-hides on its own; calling again while visible replaces the
        text. If a chat dialog is open, also drop the line into it as a
        passive remark from the operator.
        """
        if self._bubble is None:
            self._bubble = SpeechBubble(self)
        self._bubble.set_text(text)
        self._position_bubble()
        self._bubble.show()
        self._bubble.raise_()
        self._bubble_timer.start(duration_ms)
        if self._chat_dialog is not None and self._chat_dialog.isVisible():
            self._chat_dialog.append_operator_message(text)

    def _hide_bubble(self):
        if self._bubble is not None and self._bubble.isVisible():
            self._bubble.hide()

    def _position_bubble(self):
        if self._bubble is None:
            return
        self._bubble.adjustSize()
        # Anchor the bubble above the pet window, slightly to the left.
        bubble_w = self._bubble.width()
        x = max(0, self.x() + (self.width() - bubble_w) // 2)
        y = max(0, self.y() - self._bubble.height() - 8)
        self._bubble.move(x, y)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._bubble is not None and self._bubble.isVisible():
            self._position_bubble()


class _FramePreloader(QThread):
    """Decode frames of one state on a worker thread.

    Emits `frame_ready(state, index, image)` for each decoded frame, then
    `finished()`. The main thread ignores frames that belong to a state
    the user has already moved on from.
    """

    frame_ready = Signal(str, int, QImage)

    def __init__(self, state, count, path_fn):
        super().__init__()
        self._state = state
        self._count = count
        self._path_fn = path_fn

    def run(self):
        # Skip frame 0 — the main thread already decoded it synchronously
        # to avoid a blank-paint flash.
        for i in range(1, self._count):
            image = QImage(self._path_fn(i))
            if image.isNull():
                continue
            self.frame_ready.emit(self._state, i, image)


class SpeechBubble(QWidget):
    """Small frameless QLabel above the pet that displays a short line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(280)
        self._label.setStyleSheet(
            "QLabel {"
            " background-color: rgba(255, 255, 255, 230);"
            " color: #1a1a1a;"
            " border: 1px solid rgba(120, 120, 120, 200);"
            " border-radius: 8px;"
            " padding: 6px 10px;"
            " font-size: 13px;"
            "}"
        )

    def set_text(self, text: str):
        self._label.setText(text)
        self._label.adjustSize()
        self.resize(self._label.sizeHint().width() + 4, self._label.sizeHint().height() + 4)
        self._label.setGeometry(0, 0, self.width(), self.height())

    def showEvent(self, event):
        super().showEvent(event)
        # Lift the bubble to top so it isn't hidden behind the pet.
        self.raise_()

    def enterEvent(self, event):
        # Hovering pauses the auto-hide timer.
        if self.parent() is not None and hasattr(self.parent(), "_bubble_timer"):
            self.parent()._bubble_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Resuming on leave — restart the timer for the remainder of the
        # default duration so the bubble eventually fades.
        if self.parent() is not None and hasattr(self.parent(), "_bubble_timer"):
            self.parent()._bubble_timer.start(2500)
        super().leaveEvent(event)


def main():
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    atexit.register(remove_pid_file)
    remove_disabled_flag()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    PetWindow()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.ctime()}\n")
            import traceback

            traceback.print_exc(file=f)
        raise
