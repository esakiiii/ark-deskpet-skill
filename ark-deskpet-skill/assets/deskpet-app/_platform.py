"""Cross-platform helpers for the deskpet runtime.

This module isolates the four parts of the codebase that need to differ
between Windows, macOS, and Linux:

- ``pythonw_binary``         - per-platform venv python path
- ``list_process_names``     - snapshot of currently-running process basenames
- ``set_autostart``          - register / unregister autostart at login
- ``is_foreground_fullscreen``- detect the frontmost window covering the screen

Every other file should call into this module instead of importing
``winreg`` / ``ctypes.windll`` directly.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_UNIX = IS_MACOS or IS_LINUX


def pythonw_binary(project_dir: str | os.PathLike) -> str:
    """Return the path to the project's venv interpreter.

    Windows uses ``pythonw.exe`` (no console window). macOS / Linux venvs only
    ship ``python`` (no ``pythonw`` symlink by default), but ``python`` works
    fine for GUI apps on those platforms.
    """
    base = Path(project_dir)
    if IS_WINDOWS:
        return str(base / ".venv" / "Scripts" / "pythonw.exe")
    return str(base / ".venv" / "bin" / "python")


def resource_dir(project_dir: str | os.PathLike) -> str:
    """Return the per-platform resource directory for the runtime."""
    base = Path(project_dir)
    if IS_WINDOWS:
        return str(base / ".venv" / "Lib" / "site-packages")
    # mac/linux both use lib/pythonX.Y/site-packages, but discovering the
    # actual version requires importing sys; bail to a sensible default.
    return str(base / ".venv" / "lib")


# ---------------------------------------------------------------------------
# Process listing
# ---------------------------------------------------------------------------

def list_process_names() -> set[str]:
    """Return a set of lowercase executable basenames of running processes.

    Works on Windows (via ``kernel32`` Toolhelp snapshot) and macOS / Linux
    (via ``ps -Ax -o comm=``).
    """
    if IS_WINDOWS:
        return _list_process_names_windows()
    return _list_process_names_unix()


def _list_process_names_windows() -> set[str]:
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    names: set[str] = set()
    snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPPROCESS, 0
    )
    if snapshot in (wintypes.HANDLE(-1).value, -1):
        return names
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(ProcessEntry32W)
    ok = ctypes.windll.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
    while ok:
        exe = entry.szExeFile
        if exe:
            names.add(exe.strip().lower())
        ok = ctypes.windll.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    ctypes.windll.kernel32.CloseHandle(snapshot)
    return names


def _list_process_names_unix() -> set[str]:
    # ``ps`` is universal on macOS and Linux. ``comm`` may be the kernel-trimmed
    # name on Linux (15 char limit); we still want to match full names, so
    # include the full command too in case the caller matches against the
    # shorter form.
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    names: set[str] = set()
    for line in result.stdout.splitlines():
        comm = line.strip()
        if not comm:
            continue
        # basename in case comm is a full path
        base = os.path.basename(comm).lower()
        if base:
            names.add(base)
    return names


# ---------------------------------------------------------------------------
# Autostart at login
# ---------------------------------------------------------------------------

AUTOSTART_WIN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_WIN_VALUE_NAME = "ArkDeskpetWatcher"
AUTOSTART_MAC_LABEL = "com.user.ark-deskpet"
AUTOSTART_LINUX_NAME = "ark-deskpet.desktop"


def autostart_active() -> bool:
    """Return True if the autostart entry currently exists."""
    if IS_WINDOWS:
        return _autostart_active_windows()
    if IS_MACOS:
        return _macos_launch_agent_path().exists()
    if IS_LINUX:
        return _linux_autostart_path().exists()
    return False


def _autostart_active_windows() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, AUTOSTART_WIN_REG_PATH, 0,
            winreg.KEY_READ,
        )
    except OSError:
        return False
    try:
        try:
            winreg.QueryValueEx(key, AUTOSTART_WIN_VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
    finally:
        winreg.CloseKey(key)


def set_autostart(enabled: bool, *, python_path: str, launcher_path: str,
                  project_dir: str | os.PathLike,
                  display_name: str = "Ark Deskpet Watcher") -> bool:
    """Register or deregister autostart for the project.

    ``python_path`` is the venv interpreter (``pythonw_binary`` output) and
    ``launcher_path`` is the watcher script (``pet_launcher.pyw``).
    Returns True if the operation succeeded.
    """
    if IS_WINDOWS:
        return _set_autostart_windows(enabled, python_path, launcher_path)
    if IS_MACOS:
        return _set_autostart_macos(enabled, python_path, launcher_path, project_dir,
                                    display_name)
    if IS_LINUX:
        return _set_autostart_linux(enabled, python_path, launcher_path, project_dir,
                                    display_name)
    return False


def _set_autostart_windows(enabled: bool, python_path: str,
                           launcher_path: str) -> bool:
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, AUTOSTART_WIN_REG_PATH,
            0, winreg.KEY_SET_VALUE,
        )
    except OSError:
        return False
    try:
        if enabled:
            command = f'"{python_path}" "{launcher_path}"'
            winreg.SetValueEx(
                key, AUTOSTART_WIN_VALUE_NAME, 0, winreg.REG_SZ, command
            )
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_WIN_VALUE_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseHandle(key)
    return True


def _macos_launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{AUTOSTART_MAC_LABEL}.plist"


def _set_autostart_macos(enabled: bool, python_path: str, launcher_path: str,
                         project_dir, display_name: str) -> bool:
    plist_path = _macos_launch_agent_path()
    if enabled:
        try:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                '<dict>\n'
                f'    <key>Label</key>\n    <string>{AUTOSTART_MAC_LABEL}</string>\n'
                '    <key>ProgramArguments</key>\n'
                '    <array>\n'
                f'        <string>{python_path}</string>\n'
                f'        <string>{launcher_path}</string>\n'
                '    </array>\n'
                '    <key>RunAtLoad</key>\n    <true/>\n'
                '    <key>WorkingDirectory</key>\n'
                f'    <string>{project_dir}</string>\n'
                '</dict>\n</plist>\n',
                encoding="utf-8",
            )
        except OSError:
            return False
        subprocess.run(
            ["launchctl", "load", "-w", str(plist_path)],
            capture_output=True, timeout=5,
        )
    else:
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True, timeout=5,
        )
        try:
            plist_path.unlink()
        except OSError:
            pass
    return True


def _linux_autostart_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / AUTOSTART_LINUX_NAME


def _set_autostart_linux(enabled: bool, python_path: str, launcher_path: str,
                         project_dir, display_name: str) -> bool:
    desktop_path = _linux_autostart_path()
    if enabled:
        try:
            desktop_path.parent.mkdir(parents=True, exist_ok=True)
            icon = "\nIcon=utilities-system-monitor" if shutil.which("xdg-desktop-icon") else ""
            desktop_path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={display_name}\n"
                f"Exec={shlex.quote(python_path)} {shlex.quote(launcher_path)}\n"
                f"Path={project_dir}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                f"{icon}\n",
                encoding="utf-8",
            )
        except OSError:
            return False
    else:
        try:
            desktop_path.unlink()
        except OSError:
            pass
    return True


# ---------------------------------------------------------------------------
# Foreground fullscreen detection
# ---------------------------------------------------------------------------

def is_foreground_fullscreen() -> bool:
    """Return True if the frontmost window covers the primary screen."""
    if IS_WINDOWS:
        return _is_fullscreen_windows()
    if IS_MACOS:
        return _is_fullscreen_macos()
    if IS_LINUX:
        return _is_fullscreen_linux()
    return False


def _is_fullscreen_windows() -> bool:
    import ctypes
    from ctypes import wintypes

    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        # We can't easily get the caller's HWND here; the caller (main.py)
        # pre-checks visibility against its own window. Approximate the screen
        # size using GetSystemMetrics.
        SM_CXSCREEN, SM_CYSCREEN = 0, 1
        sw = user32.GetSystemMetrics(SM_CXSCREEN)
        sh = user32.GetSystemMetrics(SM_CYSCREEN)
        return (
            rect.left <= 0
            and rect.top <= 0
            and rect.right >= sw
            and rect.bottom >= sh
        )
    except OSError:
        return False


def _is_fullscreen_macos() -> bool:
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
            CGDisplayBounds,
            kCGMainDisplayID,
        )
        from AppKit import NSWorkspace
    except ImportError:
        return False
    try:
        screen_bounds = CGDisplayBounds(CGMainDisplayID())
        screen_w = screen_bounds.size.width
        screen_h = screen_bounds.size.height
        screen_x = screen_bounds.origin.x
        screen_y = screen_bounds.origin.y
        front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not front_app:
            return False
        front_pid = front_app.processIdentifier()
        info = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | 0x4,  # kCGWindowListExcludeDesktopElements = 0x4
            kCGNullWindowID,
        )
    except Exception:
        return False
    if not info:
        return False
    for win in info:
        if int(win.get("kCGWindowOwnerPID", 0)) != int(front_pid):
            continue
        bounds = win.get("kCGWindowBounds")
        if not bounds:
            continue
        try:
            x = float(bounds.get("X", 0))
            y = float(bounds.get("Y", 0))
            w = float(bounds.get("Width", 0))
            h = float(bounds.get("Height", 0))
        except (TypeError, ValueError):
            continue
        if w >= screen_w and h >= screen_h:
            return True
    return False


def _is_fullscreen_linux() -> bool:
    # Best-effort fallback: assume false. Linux fullscreen detection depends
    # on the window manager (KWin / Mutter / XFWM) and is non-trivial to do
    # cross-DE; users can disable the auto-hide setting if needed.
    return False
