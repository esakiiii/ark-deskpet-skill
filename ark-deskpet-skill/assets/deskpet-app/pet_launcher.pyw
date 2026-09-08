"""Lifecycle watcher for the deskpet. Polls the host process list and keeps
the pet + tray alive while the AI host (WorkBuddy etc.) is running.
"""

import json
import os
import signal
import subprocess
import sys
import time

from _platform import (
    IS_MACOS,
    IS_WINDOWS,
    list_process_names,
    pythonw_binary,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYW_PATH = pythonw_binary(BASE_DIR)
MAIN_PATH = os.path.join(BASE_DIR, "main.py")
TRAY_PATH = os.path.join(BASE_DIR, "pet_tray.pyw")
PID_FILE = os.path.join(BASE_DIR, "pet.pid")
WATCHER_PID_FILE = os.path.join(BASE_DIR, "watcher.pid")
TRAY_PID_FILE = os.path.join(BASE_DIR, "tray.pid")
SHUTDOWN_FLAG = os.path.join(BASE_DIR, "pet_shutdown.flag")
DISABLED_FLAG = os.path.join(BASE_DIR, "pet_disabled.flag")
TRAY_STOP_FLAG = os.path.join(BASE_DIR, "tray_stop.flag")
WATCHER_EXIT_FLAG = os.path.join(BASE_DIR, "watcher_exit.flag")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
POLL_SECONDS = 3

# Default host process names; can be overridden via settings.json -> host_processes.
DEFAULT_HOST_NAMES = {
    # Windows executable basenames.
    "workbuddy.exe",
    "workbuddyhelper.exe",
    "workbuddyclient.exe",
    # macOS / Linux app / process basenames.
    "workbuddy",
    "workbuddy helper",
    "workbuddyclient",
    "workbuddy helper (renderer)",
}


def read_pid(path):
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def pid_alive(pid):
    """Return True if ``pid`` is still a live process."""
    if pid is None or pid <= 0:
        return False
    try:
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        # macOS / Linux: signal 0 is a no-op that returns ESRCH if no process.
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False


def load_host_names():
    """Return the merged set of host process names + per-user overrides."""
    names = set(DEFAULT_HOST_NAMES)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    extra = data.get("host_processes") if isinstance(data, dict) else None
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str) and item.strip():
                names.add(item.strip().lower())
    return names


def pet_running():
    return pid_alive(read_pid(PID_FILE))


def tray_running():
    return pid_alive(read_pid(TRAY_PID_FILE))


def launch(path, args):
    """Spawn a child process detached from the launcher."""
    if IS_WINDOWS:
        # CREATE_NO_WINDOW hides the console flash on Windows.
        subprocess.Popen(
            [path] + args,
            cwd=BASE_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        # start_new_session detaches the child from the watcher's tty so
        # closing the launcher doesn't kill the pet.
        subprocess.Popen(
            [path] + args,
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def launch_pet():
    launch(PYW_PATH, [MAIN_PATH])


def start_tray():
    if not tray_running():
        launch(PYW_PATH, [TRAY_PATH])


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


def terminate_pid(pid):
    try:
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes

            PROCESS_TERMINATE = 0x0001
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                kernel32.TerminateProcess(handle, 0)
                kernel32.CloseHandle(handle)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError, PermissionError):
        pass


def close_pet():
    if not pet_running():
        return True
    write_flag(SHUTDOWN_FLAG)
    deadline = time.time() + 6
    while time.time() < deadline:
        if not pet_running():
            return True
        time.sleep(0.3)
    pid = read_pid(PID_FILE)
    if pid is not None:
        terminate_pid(pid)
    return not pet_running()


def stop_tray():
    if not tray_running():
        return True
    write_flag(TRAY_STOP_FLAG)
    deadline = time.time() + 4
    while time.time() < deadline:
        if not tray_running():
            return True
        time.sleep(0.2)
    pid = read_pid(TRAY_PID_FILE)
    if pid is not None:
        terminate_pid(pid)
    return not tray_running()


def host_running():
    return bool(set(list_process_names()) & load_host_names())


def disabled():
    return os.path.exists(DISABLED_FLAG)


def watcher_already_running():
    return pid_alive(read_pid(WATCHER_PID_FILE))


def main():
    if watcher_already_running():
        return
    write_pid(WATCHER_PID_FILE)
    was_host = False
    try:
        while True:
            if os.path.exists(WATCHER_EXIT_FLAG):
                remove_flag(WATCHER_EXIT_FLAG)
                close_pet()
                stop_tray()
                break
            host = host_running()
            if host:
                if not was_host:
                    remove_flag(DISABLED_FLAG)
                if not tray_running():
                    start_tray()
                if not pet_running() and not disabled():
                    launch_pet()
            else:
                if pet_running():
                    close_pet()
                if tray_running():
                    stop_tray()
            was_host = host
            time.sleep(POLL_SECONDS)
    finally:
        remove_pid(WATCHER_PID_FILE)


def write_pid(path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def remove_pid(path):
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
