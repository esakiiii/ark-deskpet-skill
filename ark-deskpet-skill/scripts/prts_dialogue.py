"""Scrape an Arknights operator's Chinese voice lines from PRTS Wiki.

PRTS renders the operator's 语音记录 section as a hidden JSON-of-DOM
table: every line is a `<div class="voice-data-item" data-title="..."
data-voice-index="..." data-place-type="...">` containing one
`<div class="voice-item-detail" data-kind-name="中文">...</div>` block.

This script:
  1. Resolves the operator's page title via opensearch + redirect-follow.
  2. Hits `api.php?action=parse&prop=text` to get the rendered HTML.
  3. Walks the voice-data-root subtree with a div-stack to find each
     voice-data-item's span, then extracts its metadata and Chinese text.
  4. Writes the result as a JSON list (one entry per voice line).

It does NOT mark up the lines into the deskpet's `dialogue.json` format;
that's a curation step, deliberately kept human-driven (see the docstring
for the rationale).

Output schema (one entry per voice line):

    {
      "title":       "<PRTS 触发场景名, e.g. 信赖提升后交谈1>",
      "index":       "<voice-index, e.g. 7>",
      "place":       "<place-type enum, e.g. HOME_SHOW>",
      "cond":        "<additional condition flag, usually empty>",
      "file":        "<CN_xxx.wav>",
      "text":        "<中文-普通话 原文>"
    }

Usage:

    python scripts/prts_dialogue.py "Logos" --out /tmp/logos_lines.json
    python scripts/prts_dialogue.py "艾雅法拉" --out /tmp/amya_lines.json

If the operator is reachable only under a Chinese/redirected title,
opensearch will pick the canonical page for you.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterable, List, Sequence


API_BASE = "https://prts.wiki/api.php"
LANG = "中文-普通话"  # the only language baked into the deskpet right now


def _get(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ark-deskpet/1.0 (local)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def resolve_page(operator: str) -> str:
    """Return the canonical PRTS page title for `operator`.

    Uses opensearch first (fast path that handles redirects) and falls back
    to direct page-id lookup. Returns the *raw* title (URL-encoded is the
    caller's job).
    """
    url = (
        API_BASE
        + "?action=opensearch&search="
        + urllib.parse.quote(operator)
        + "&limit=10&format=json"
    )
    data = json.loads(_get(url))
    titles: Sequence[str] = data[1] if len(data) > 1 else []
    if not titles:
        # Fallback: prefix-match search via list=search.
        search_url = (
            API_BASE
            + "?action=query&list=search&srsearch="
            + urllib.parse.quote(operator)
            + "&srlimit=20&format=json"
        )
        sr = json.loads(_get(search_url))
        hits = sr.get("query", {}).get("search", [])
        titles = [h.get("title", "") for h in hits]
    if not titles:
        raise SystemExit(f"PRTS: no page found for operator {operator!r}")

    # Prefer an exact (case-insensitive) match, then a title that contains
    # the query, then the first hit.
    exact = [t for t in titles if t.lower() == operator.lower()]
    if exact:
        return exact[0]
    contains = [t for t in titles if operator.lower() in t.lower()]
    if contains:
        return contains[0]
    return titles[0]


def fetch_rendered_html(title: str) -> str:
    """Hit action=parse&prop=text with redirects=1."""
    url = (
        API_BASE
        + "?action=parse&page="
        + urllib.parse.quote(title)
        + "&format=json&prop=text&utf8=1&redirects=1"
    )
    data = json.loads(_get(url))
    if "error" in data:
        raise SystemExit(f"PRTS parse error: {data['error']}")
    return data["parse"]["text"]["*"]


def _voice_root_span(html: str) -> str:
    """Slice `html` to the contents of the voice-data-root div.

    The voice lines are rendered client-side by VoiceTable.js from
    `#voice-data-root`. We only need to read the static SSR fallback HTML
    that the parser returns, which already contains every line as a
    `<div class="voice-data-item">` element.
    """
    start = html.find('<div id="voice-data-root"')
    if start < 0:
        raise SystemExit("voice-data-root not found in HTML (page format changed?)")
    end = len(html)
    for end_marker in (
        '<div class="mw-heading mw-heading2"',
        '<div class="printfooter"',
        '<div id="mw-navigation"',
    ):
        j = html.find(end_marker, start)
        if 0 < j < end:
            end = j
    return html[start:end]


def _iter_voice_items(voice_html: str) -> Iterable[tuple[int, int]]:
    """Yield (start, end) byte spans of every voice-data-item subtree.

    Uses a `<div ...>` / `</div>` token walker so it stays correct even
    when items have differently structured inner markup across the wiki's
    rollout.
    """
    open_tag = '<div class="voice-data-item"'
    pos = 0
    while True:
        s = voice_html.find(open_tag, pos)
        if s < 0:
            return
        depth = 0
        nxt = s
        while nxt < len(voice_html):
            # Token walker: each step is either the next `<div` (open) or
            # the next `</div>` (close). Treats both as matching tokens.
            o = voice_html.find('<div', nxt)
            c = voice_html.find('</div>', nxt)
            if c < 0:
                return
            if 0 <= o < c:
                depth += 1
                nxt = o + len('<div')
            else:
                depth -= 1
                nxt = c + len('</div>')
                if depth == 0:
                    yield s, nxt
                    pos = nxt
                    break
        else:
            return


def _attr(chunk: str, name: str) -> str:
    import re
    m = re.search(rf'data-{re.escape(name)}="([^"]*)"', chunk)
    return m.group(1) if m else ""


def _decode_text(raw: str) -> str:
    raw = raw.strip()
    raw = raw.replace("<br/>", "\n").replace("<br>", "\n")
    # Strip any remaining inline tags (the script content is text-only).
    import re
    raw = re.sub(r"<[^>]+>", "", raw)
    return html_mod.unescape(raw).strip()


def parse_voice_lines(html_text: str) -> List[dict]:
    voice_html = _voice_root_span(html_text)
    items: List[dict] = []
    for s, e in _iter_voice_items(voice_html):
        chunk = voice_html[s:e]
        import re
        cn_m = re.search(
            r'<div class="voice-item-detail" data-kind-name="中文"[^>]*>(.*?)</div>',
            chunk,
            flags=re.S,
        )
        text = _decode_text(cn_m.group(1)) if cn_m else ""
        # Skip entries with no Chinese text (e.g. locale fallbacks).
        if not text:
            continue
        entry = {
            "title": _attr(chunk, "title"),
            "index": _attr(chunk, "voice-index"),
            "place": _attr(chunk, "place-type"),
            "cond": _attr(chunk, "cond"),
            "file": _attr(chunk, "voice-filename"),
            "text": text,
        }
        items.append(entry)
    # Stable order: PRTS' voice-index, falling back to insertion order.
    items.sort(key=lambda r: int(r["index"]) if r["index"].isdigit() else 9999)
    return items


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("operator", help="Operator name (Chinese, English, alias).")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("work/dialogue_raw.json"),
        help="Where to write the JSON dump (default: work/dialogue_raw.json).",
    )
    ap.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indent=2 (default is compact).",
    )
    args = ap.parse_args(argv)

    title = resolve_page(args.operator)
    html_text = fetch_rendered_html(title)
    items = parse_voice_lines(html_text)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    indent = 2 if args.pretty else None
    args.out.write_text(
        json.dumps(items, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )

    print(
        f"PRTS: {args.operator!r} -> page {title!r}, "
        f"{len(items)} Chinese voice lines written to {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
