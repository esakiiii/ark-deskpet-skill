"""DeepSeek chat client for the deskpet.

Uses DeepSeek's OpenAI-compatible REST API. Runs in a worker thread so
the Qt event loop keeps rendering while the model streams tokens.

Configuration (all read from the project's `settings.json`):

    {
        "deepseek_api_key": "sk-...",
        "deepseek_base_url": "https://api.deepseek.com/v1",   # optional
        "deepseek_model": "deepseek-chat",                     # optional
        "deepseek_system_prompt": "你是 Log\nos，干员名：Logos。保持简短，1-2 句。"
    }
"""

from __future__ import annotations

import json
import os
import threading
from typing import Callable, Iterable, List, Mapping, Optional

try:
    import requests
except ImportError:  # pragma: no cover - the skill ships with requests anyway
    requests = None


DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekError(RuntimeError):
    """Raised for any DeepSeek-side failure the caller should surface."""


def resolve_config(settings: Mapping[str, str]) -> dict:
    """Pull the DeepSeek-related fields out of a settings dict.

    Empty / missing fields are returned as empty strings so the caller can
    show a friendly "please configure" message instead of crashing.
    """

    return {
        "api_key": (settings.get("deepseek_api_key") or "").strip(),
        "base_url": (settings.get("deepseek_base_url") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        "model": (settings.get("deepseek_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "system_prompt": (settings.get("deepseek_system_prompt") or "").strip(),
    }


def chat_stream(
    settings: Mapping[str, str],
    messages: List[Mapping[str, str]],
    on_token: Callable[[str], None],
    on_done: Callable[[], None],
    on_error: Callable[[str], None],
    *,
    timeout: float = 60.0,
    stop_event: Optional[threading.Event] = None,
) -> threading.Thread:
    """Spawn a worker thread that streams a chat completion back.

    `on_token(text)` is called for each delta; `on_done()` runs once the
    stream closes cleanly; `on_error(message)` runs on any failure. The
    `stop_event` lets callers cancel mid-stream (e.g. closing the window).
    """

    cfg = resolve_config(settings)
    if not cfg["api_key"]:
        on_error("尚未配置 DeepSeek API Key。右键桌宠 → 设置... → 聊天 填写。")
        on_done()
        return _noop_thread()

    if requests is None:
        on_error("本机缺少 requests 库，请运行 setup_env.py 重装依赖。")
        on_done()
        return _noop_thread()

    payload_messages: List[dict] = []
    if cfg["system_prompt"]:
        payload_messages.append({"role": "system", "content": cfg["system_prompt"]})
    payload_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)

    body = {
        "model": cfg["model"],
        "messages": payload_messages,
        "stream": True,
        "temperature": 0.6,
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = cfg["base_url"].rstrip("/") + "/chat/completions"

    thread = threading.Thread(
        target=_run_stream,
        args=(url, headers, body, timeout, on_token, on_done, on_error, stop_event),
        daemon=True,
    )
    thread.start()
    return thread


def _run_stream(url, headers, body, timeout, on_token, on_done, on_error, stop_event):
    try:
        with requests.post(
            url,
            headers=headers,
            json=body,
            stream=True,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                snippet = resp.text[:240] if resp.text else ""
                on_error(f"DeepSeek 返回 {resp.status_code}：{snippet}")
                on_done()
                return
            for raw_line in resp.iter_lines(decode_unicode=True):
                if stop_event is not None and stop_event.is_set():
                    on_error("(已中断)")
                    on_done()
                    return
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = chunk["choices"][0]["delta"]
                except (KeyError, IndexError, TypeError):
                    continue
                content = delta.get("content") if isinstance(delta, dict) else None
                if content:
                    on_token(content)
        on_done()
    except requests.exceptions.Timeout:
        on_error("DeepSeek 请求超时，请稍后再试。")
        on_done()
    except requests.exceptions.RequestException as exc:
        on_error(f"网络错误：{exc}")
        on_done()
    except Exception as exc:  # noqa: BLE001
        on_error(f"未知错误：{exc}")
        on_done()


def _noop_thread() -> threading.Thread:
    """Return a finished thread so the caller's `join()` pattern still works."""

    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    return t
