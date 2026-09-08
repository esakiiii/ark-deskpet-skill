#!/usr/bin/env python3
"""Create shortcuts for the deskpet on the current platform.

- Windows: ``打开桌宠.lnk`` / ``启动托盘.lnk`` on Desktop + Start Menu
  via PowerShell ``WScript.Shell``.
- macOS:   launcher scripts in the Dock via a small AppleScript alias
  (full ``.app`` generation is out of scope; we drop shell launchers in
  ``~/Applications`` and offer to add them to the Dock).
- Linux:   ``.desktop`` files in ``~/.local/share/applications`` so the
  launcher shows up in the application launcher.
"""

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _project_assets(project: Path):
    """Return (main_py, launcher_py) regardless of platform naming."""
    candidates = [
        ("main.py", "pet_launcher.pyw"),
        ("main.py", "pet_launcher.py"),
    ]
    for main_name, launch_name in candidates:
        if (project / main_name).is_file() and (project / launch_name).is_file():
            return project / main_name, project / launch_name
    sys.exit(
        "project .venv or app files not found at " + str(project)
        + " (expected main.py and pet_launcher.pyw)"
    )


def _venv_python(project: Path) -> Path:
    if IS_WINDOWS:
        return project / ".venv" / "Scripts" / "pythonw.exe"
    return project / ".venv" / "bin" / "python"


def create_windows(project: Path):
    pythonw = project / ".venv" / "Scripts" / "pythonw.exe"
    main_py, launcher_py = _project_assets(project)
    if not pythonw.is_file():
        sys.exit("project .venv or app files not found at " + str(project))

    ps_quote = lambda v: "'" + str(v).replace("'", "''") + "'"

    def shortcut_ps(ws, folder_expr, name, target, args, cwd):
        return (
            "$s = $ws.CreateShortcut((Join-Path ("
            + folder_expr
            + ") "
            + ps_quote(name + ".lnk")
            + ")); "
            "$s.TargetPath = " + ps_quote(str(target)) + "; "
            "$s.Arguments = " + ps_quote('"' + str(args) + '"') + "; "
            "$s.WorkingDirectory = " + ps_quote(str(cwd)) + "; "
            "$s.Save(); Write-Output $s.FullName; "
        )

    desktop = "([Environment]::GetFolderPath('Desktop'))"
    programs = "([Environment]::GetFolderPath('Programs'))"
    command = (
        "$oldD = Join-Path ([Environment]::GetFolderPath('Desktop')) "
        "'\u542f\u52a8\u76d1\u542c\u5668.lnk'; "
        "if (Test-Path $oldD) { Remove-Item $oldD -Force }; "
        "$oldP = Join-Path ([Environment]::GetFolderPath('Programs')) "
        "'\u542f\u52a8\u76d1\u542c\u5668.lnk'; "
        "if (Test-Path $oldP) { Remove-Item $oldP -Force }; "
        "$ws = New-Object -ComObject WScript.Shell; "
    )
    command += shortcut_ps("$ws", desktop, "打开桌宠", pythonw, main_py, project)
    command += shortcut_ps("$ws", programs, "打开桌宠", pythonw, main_py, project)
    command += shortcut_ps("$ws", desktop, "启动托盘", pythonw, launcher_py, project)
    command += shortcut_ps("$ws", programs, "启动托盘", pythonw, launcher_py, project)

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.exit(
            "shortcut creation failed: "
            + result.stderr.decode("utf-8", "replace")
        )
    print("shortcuts created (Windows .lnk)")


def create_macos(project: Path):
    """Drop shell launchers in ~/Applications and try to add to the Dock."""
    py = _venv_python(project)
    main_py, launcher_py = _project_assets(project)
    apps_dir = Path.home() / "Applications"
    apps_dir.mkdir(parents=True, exist_ok=True)

    def write_launcher(name: str, target: Path):
        out = apps_dir / f"{name}.command"
        out.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                cd "{project}"
                exec "{py}" "{target}"
                """),
            encoding="utf-8",
        )
        os.chmod(out, 0o755)
        return out

    open_pet = write_launcher("打开桌宠 (Ark Deskpet)", main_py)
    start_tray = write_launcher("启动托盘 (Ark Deskpet)", launcher_py)
    print(f"wrote {open_pet}")
    print(f"wrote {start_tray}")
    # Offer to pin to the Dock (best-effort; macOS may still gate this).
    script = textwrap.dedent(f"""\
        tell application "Dock" to make new alias with properties {{name:"打开桌宠 (Ark Deskpet)", POSIX file:"{open_pet}"}}
        tell application "Dock" to make new alias with properties {{name:"启动托盘 (Ark Deskpet)", POSIX file:"{start_tray}"}}
    """).strip()
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=5,
        )
        print("asked Dock to add launchers (open Finder -> ~/Applications if not visible)")
    except (OSError, subprocess.TimeoutExpired):
        print("couldn't auto-add to Dock; launch from Finder -> ~/Applications manually")


def create_linux(project: Path):
    py = _venv_python(project)
    main_py, launcher_py = _project_assets(project)
    apps_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)

    def write_desktop(name: str, target: Path):
        out = apps_dir / f"ark-deskpet-{name}.desktop"
        out.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={name} (Ark Deskpet)\n"
            f"Exec={py} {target}\n"
            f"Path={project}\n"
            "Terminal=false\n"
            "Categories=Game;Utility;\n",
            encoding="utf-8",
        )
        os.chmod(out, 0o755)
        return out

    a = write_desktop("打开桌宠", main_py)
    b = write_desktop("启动托盘", launcher_py)
    print(f"wrote {a}")
    print(f"wrote {b}")
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(
                ["update-desktop-database", str(apps_dir)],
                capture_output=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="deskpet project directory")
    args = parser.parse_args()
    project = Path(args.project).resolve()

    if IS_WINDOWS:
        create_windows(project)
    elif IS_MACOS:
        create_macos(project)
    elif IS_LINUX:
        create_linux(project)
    else:
        sys.exit("unsupported platform: " + sys.platform)


if __name__ == "__main__":
    main()
