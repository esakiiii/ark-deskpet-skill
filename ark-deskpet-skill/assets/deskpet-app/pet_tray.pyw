"""System-tray process. Spawned by ``pet_launcher`` while the AI host is
running. Provides show / hide / autostart / quit menu actions.

The autostart implementation is delegated to ``_platform.set_autostart``,
which writes to the platform-appropriate per-user location:

- Windows: ``HKEY_CURRENT_USER\\...\\Run`` value
- macOS:   ``~/Library/LaunchAgents/<label>.plist``
- Linux:   ``~/.config/autostart/<name>.desktop``
"""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from _platform import (
    autostart_active,
    pythonw_binary,
    set_autostart as platform_set_autostart,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAY_PID_FILE = os.path.join(BASE_DIR, "tray.pid")
TRAY_STOP_FLAG = os.path.join(BASE_DIR, "tray_stop.flag")
WATCHER_EXIT_FLAG = os.path.join(BASE_DIR, "watcher_exit.flag")
SHOW_FLAG = os.path.join(BASE_DIR, "pet_show.flag")
HIDE_FLAG = os.path.join(BASE_DIR, "pet_hide.flag")
SHUTDOWN_FLAG = os.path.join(BASE_DIR, "pet_shutdown.flag")
DISABLED_FLAG = os.path.join(BASE_DIR, "pet_disabled.flag")
PYW_PATH = pythonw_binary(BASE_DIR)
WATCHER_PATH = os.path.join(BASE_DIR, "pet_launcher.pyw")


def write_flag(path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass


def remove_flag(path):
    try:
        os.remove(path)
    except OSError:
        pass


def make_icon():
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(30, 120, 70))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(8, 8, 48, 48)
    painter.setPen(QColor(255, 255, 255))
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "A")
    painter.end()
    return QIcon(pix)


def show_pet():
    remove_flag(DISABLED_FLAG)
    write_flag(SHOW_FLAG)


def hide_pet():
    write_flag(HIDE_FLAG)


def close_pet():
    write_flag(DISABLED_FLAG)
    write_flag(SHUTDOWN_FLAG)


def autostart_enabled():
    return autostart_active()


def set_autostart(enabled):
    return platform_set_autostart(
        bool(enabled),
        python_path=PYW_PATH,
        launcher_path=WATCHER_PATH,
        project_dir=BASE_DIR,
    )


def quit_watcher():
    write_flag(WATCHER_EXIT_FLAG)
    QApplication.instance().quit()


def main():
    with open(TRAY_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(make_icon(), app)
        tray.setToolTip("明日方舟 桌宠 (WorkBuddy)")
        menu = QMenu()
        show_action = QAction("显示桌宠", menu, triggered=show_pet)
        close_action = QAction("隐藏桌宠", menu, triggered=close_pet)
        autostart_action = QAction("开机自启动", menu, checkable=True)
        autostart_action.setChecked(autostart_enabled())
        autostart_action.toggled.connect(set_autostart)
        exit_action = QAction("退出", menu, triggered=quit_watcher)
        menu.addAction(show_action)
        menu.addAction(close_action)
        menu.addSeparator()
        menu.addAction(autostart_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        tray.setContextMenu(menu)
        tray.show()

        timer = QTimer()
        timer.timeout.connect(
            lambda: (
                remove_flag(TRAY_STOP_FLAG),
                QApplication.instance().quit(),
            )
            if os.path.exists(TRAY_STOP_FLAG)
            else None
        )
        timer.start(1000)
        app.exec()
    finally:
        remove_flag(TRAY_PID_FILE)


if __name__ == "__main__":
    main()
