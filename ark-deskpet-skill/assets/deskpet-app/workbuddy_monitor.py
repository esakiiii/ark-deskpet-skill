"""Lightweight status reader for the AI host the deskpet is paired with.

The original implementation read Codex's rollouts JSONL. This rewrite does not
assume a particular session format: it scans a configurable list of paths
(defaults to ``~/.workbuddy/memory`` and ``~/.codex/sessions`` for legacy
upgrades), picks the most recently modified text-like file, and tries to
extract a few best-effort signals (current task, model, progress, token usage,
elapsed time, last-finished timestamp).

If parsing fails or the file format is unknown, ``active`` is still computed
from the file's modification time, so the pet at least knows whether the host
has been "doing something" recently. All optional fields fall back to None.
"""

import datetime
import json
import os
import re
import time
from pathlib import Path

# Default directories to scan for "recent activity" signals.
# - ``~/.workbuddy/memory`` is where WorkBuddy writes workspace daily logs.
# - ``~/.codex/sessions`` is kept for users who migrated from the old skill.
DEFAULT_SESSION_PATHS = [
    "~/.workbuddy/memory",
    "~/.workbuddy",
    "~/.codex/sessions",
]

DEFAULT_ACTIVE_THRESHOLD = 8  # seconds since last edit => still "active"
MAX_TAIL_BYTES = 262144
MAX_TAIL_LINES = 200

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")


def _expand(path):
    return os.path.expanduser(os.path.expandvars(path))


def _read_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _session_paths():
    paths = list(DEFAULT_SESSION_PATHS)
    extra = _read_settings().get("session_paths")
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, str) and item.strip():
                paths.append(item.strip())
    # de-dupe while preserving order
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _active_threshold():
    cfg = _read_settings().get("active_threshold_seconds")
    if isinstance(cfg, (int, float)) and cfg > 0:
        return float(cfg)
    return DEFAULT_ACTIVE_THRESHOLD


def _candidate_files(root):
    """Return up to ~50 candidate files under root, newest first."""
    root = _expand(root)
    if not os.path.isdir(root):
        return []
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.startswith("."):
                continue
            full = os.path.join(dirpath, f)
            if os.path.isfile(full):
                out.append(full)
    out.sort(key=os.path.getmtime, reverse=True)
    return out[:50]


def _tail_lines(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            length = f.tell()
            start = max(0, length - MAX_TAIL_BYTES)
            f.seek(start)
            data = f.read().decode("utf-8", errors="replace")
        if start > 0:
            newline = data.find("\n")
            if newline != -1:
                data = data[newline + 1:]
    except OSError:
        return []
    return data.splitlines()[-MAX_TAIL_LINES:]


def _clean(text, limit=80):
    if not isinstance(text, str):
        return None
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > limit:
        text = text[: max(0, limit - 1)] + "…"
    return text


def _first_text(payload, keys):
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _extract_from_jsonl(lines):
    """Best-effort JSONL reader. Unknown schemas are skipped gracefully."""
    info = {
        "task": None,
        "model": None,
        "progress": None,
        "started_at": None,
        "tokens": None,
        "last_finished": None,
    }
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
        if not isinstance(payload, dict):
            continue
        ptype = payload.get("type") or obj.get("type")

        started = payload.get("started_at")
        if isinstance(started, (int, float)):
            info["started_at"] = float(started)
        completed = payload.get("completed_at")
        if isinstance(completed, (int, float)):
            info["last_finished"] = float(completed)

        # Token counts may live at several places depending on the schema.
        token = None
        info_field = payload.get("info")
        if isinstance(info_field, dict):
            usage = info_field.get("total_token_usage")
            if isinstance(usage, dict):
                token = usage.get("total_tokens")
            if token is None:
                token = info_field.get("total_tokens")
        if token is None:
            token = payload.get("total_tokens")
        if isinstance(token, (int, float)):
            info["tokens"] = int(token)

        text = _first_text(payload, ("message", "content", "text"))
        role = payload.get("role")
        if text and ptype in ("user_message", "user", "request"):
            info["task"] = text
        elif text and ptype in ("agent_message", "assistant", "model", "response"):
            info["progress"] = text

        # Model name
        model = payload.get("model") or payload.get("model_name")
        if isinstance(model, str) and model.strip():
            info["model"] = model
        thread = payload.get("thread_settings")
        if isinstance(thread, dict):
            tm = thread.get("model")
            if isinstance(tm, str) and tm.strip():
                info["model"] = tm
    return info


def _extract_from_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return None
    if isinstance(obj, list):
        try:
            lines = [json.dumps(x, ensure_ascii=False) for x in obj]
        except Exception:
            return None
        return _extract_from_jsonl(lines)
    if isinstance(obj, dict):
        return _extract_from_jsonl([json.dumps(obj, ensure_ascii=False)])
    return None


_HEADING_RE = re.compile(r"^#{1,6}\s*(.*?)\s*$")


def _extract_from_markdown(lines):
    info = {
        "task": None,
        "model": None,
        "progress": None,
        "started_at": None,
        "tokens": None,
        "last_finished": None,
    }
    section = ""
    for raw in lines[-80:]:
        line = raw.rstrip()
        if not line:
            continue
        m = _HEADING_RE.match(line)
        if m:
            section = m.group(1).strip().lower()
            continue
        if info["task"] is None and any(k in section for k in ("任务", "task")):
            info["task"] = line[:80]
        elif info["model"] is None and any(k in section for k in ("模型", "model")):
            info["model"] = line[:60]
        elif info["progress"] is None and any(k in section for k in ("进度", "progress", "进展", "当前")):
            info["progress"] = line[:120]
        elif info["tokens"] is None and any(k in section for k in ("token", "token usage")):
            digits = re.findall(r"\d[\d,.]*", line)
            if digits:
                try:
                    info["tokens"] = int(digits[0].replace(",", ""))
                except ValueError:
                    pass
    return info


def _info_for_file(path):
    name = path.lower()
    lines = _tail_lines(path)
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        return _extract_from_jsonl(lines)
    if name.endswith(".json"):
        info = _extract_from_json(path)
        return info or {
            "task": None,
            "model": None,
            "progress": None,
            "started_at": None,
            "tokens": None,
            "last_finished": None,
        }
    return _extract_from_markdown(lines)


def _format_last_finished(value):
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.datetime.fromtimestamp(value).strftime("%H:%M")
    except Exception:
        return None


def get_host_status():
    """Public entry. Returns a dict mirroring the original status shape.

    Fields: active, task, model, progress, elapsed, tokens, last_finished.
    """
    empty = {
        "active": False,
        "task": None,
        "model": None,
        "progress": None,
        "elapsed": None,
        "tokens": None,
        "last_finished": None,
    }
    threshold = _active_threshold()
    best_path = None
    best_mtime = -1.0
    for src in _session_paths():
        for path in _candidate_files(src):
            try:
                mt = os.path.getmtime(path)
            except OSError:
                continue
            if mt > best_mtime:
                best_mtime = mt
                best_path = path
    if not best_path:
        return empty
    try:
        info = _info_for_file(best_path)
    except Exception:
        info = None
    if not info:
        info = {
            "task": None,
            "model": None,
            "progress": None,
            "started_at": None,
            "tokens": None,
            "last_finished": None,
        }
    active = (time.time() - best_mtime) < threshold
    started_at = info.get("started_at")
    elapsed = (
        int(time.time() - started_at)
        if active and isinstance(started_at, (int, float))
        else None
    )
    return {
        "active": active,
        "task": _clean(info.get("task")),
        "model": info.get("model"),
        "progress": _clean(info.get("progress"), 120),
        "elapsed": elapsed,
        "tokens": info.get("tokens"),
        "last_finished": _format_last_finished(info.get("last_finished")),
    }
