"""Offline dialogue engine for the deskpet.

Loads `pets/<character>/dialogue.json` and exposes two helpers:

- `pick(category)`        — return a random line from the named category.
                            Uses an in-memory `recently_said` deque so the
                            pet doesn't repeat the same line twice in a row.
- `match(user_text)`      — search all categories for triggers that the
                            user's text contains; return the best match
                            (or None).

The engine is intentionally tiny — no regex precompilation, no caching —
because a typical dialogue.json has < 100 lines and these calls run on
the Qt thread when the user clicks Send or when the idle timer fires.
"""

from __future__ import annotations

import json
import random
import re
from collections import deque
from pathlib import Path
from typing import List, Mapping, Optional


_RECENT_LIMIT = 6  # how many recent lines to avoid repeating


class DialogueEngine:
    """Wraps a single character script (one dialogue.json file)."""

    def __init__(self, script: Mapping[str, object], *, recent_limit: int = _RECENT_LIMIT):
        self._script = script or {}
        self._recent: deque = deque(maxlen=recent_limit)
        self._categories: List[str] = list(self._script.keys())

    # -- factories -------------------------------------------------------

    @classmethod
    def from_path(cls, path) -> "DialogueEngine":
        path = Path(path)
        if not path.is_file():
            return cls({"_missing": True})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls({"_missing": True})
        return cls(data)

    @classmethod
    def from_pet_dir(cls, pet_dir) -> "DialogueEngine":
        return cls.from_path(Path(pet_dir) / "dialogue.json")

    # -- public API ------------------------------------------------------

    @property
    def has_script(self) -> bool:
        return bool(self._categories) and not self._script.get("_missing")

    @property
    def categories(self) -> List[str]:
        return list(self._categories)

    def pick(self, category: str) -> Optional[str]:
        """Return a random line from `category`, or None if missing/empty."""
        bucket = self._script.get(category)
        line = self._pick_from_bucket(bucket)
        if line is not None:
            self._mark_recent(line)
        return line

    def pick_weighted(self, category: str) -> Optional[str]:
        """Like `pick` but supports {"text": "...", "weight": N} entries."""
        bucket = self._script.get(category)
        if not isinstance(bucket, list) or not bucket:
            return None
        candidates = []
        weights = []
        for entry in bucket:
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not text:
                continue
            candidates.append(text)
            weights.append(max(1, int(entry.get("weight", 1))))
        if not candidates:
            return None
        chosen = random.choices(candidates, weights=weights, k=1)[0]
        self._mark_recent(chosen)
        return chosen

    def match(self, user_text: str) -> Optional[str]:
        """Return the best matching line for `user_text`, or None.

        Searches every category whose entries are objects with a
        `triggers` list. The category with the highest trigger hit count
        wins; ties broken by the order declared in the script.
        """
        if not user_text:
            return None
        text_lower = user_text.lower()
        best_line = None
        best_score = 0
        for category in self._categories:
            bucket = self._script.get(category)
            if not isinstance(bucket, list):
                continue
            for entry in bucket:
                if not isinstance(entry, dict):
                    continue
                triggers = entry.get("triggers")
                text = entry.get("text")
                if not triggers or not text:
                    continue
                score = self._trigger_score(triggers, text_lower)
                if score > best_score:
                    best_score = score
                    best_line = text
        if best_line is not None:
            self._mark_recent(best_line)
        return best_line

    def fallback(self) -> Optional[str]:
        """Convenience: return a random fallback line if one is configured."""
        return self.pick("fallback")

    def pick_reaction(self, key: str) -> Optional[str]:
        """Pick a line from the nested `status_reactions.<key>` bucket.

        These sub-buckets are looked up by string key (e.g. "went_idle",
        "active_busy") so callers can route different lifecycle events to
        different sets of lines without having to declare one top-level
        category per event.
        """
        bucket = self._script.get("status_reactions")
        if not isinstance(bucket, dict):
            return None
        return self.pick_weighted(key) or self._pick_from_bucket(bucket.get(key))

    # -- internals -------------------------------------------------------

    def _pick_from_bucket(self, bucket) -> Optional[str]:
        if not isinstance(bucket, list) or not bucket:
            return None
        # Mix plain strings and {text: ...} objects uniformly.
        candidates = []
        for entry in bucket:
            if isinstance(entry, str):
                candidates.append(entry)
            elif isinstance(entry, dict) and entry.get("text"):
                candidates.append(entry["text"])
        if not candidates:
            return None
        # Avoid immediate repeats.
        pool = [c for c in candidates if c not in self._recent] or candidates
        return random.choice(pool)

    def _trigger_score(self, triggers, text_lower: str) -> int:
        score = 0
        for trig in triggers:
            if not isinstance(trig, str) or not trig:
                continue
            t = trig.lower()
            if self._trigger_hits(t, text_lower):
                score += len(t)  # longer triggers beat shorter ones
        return score

    @staticmethod
    def _trigger_hits(trig: str, text_lower: str) -> bool:
        """Return True if `trig` is meaningfully present in `text_lower`.

        - CJK triggers fall back to a plain substring check, since Chinese
          characters don't have word boundaries the way Latin text does.
        - Pure-ASCII triggers use a regex word-boundary match by default
          so that `hi` does not match `history`. Short ASCII triggers
          (<= 4 chars) additionally accept prefix matches so that
          `thank` still matches `thanks` — this is a common typing style
          in casual chat and doesn't cause false positives worth caring
          about for our small dictionary.
        """
        if not trig:
            return False
        if not trig.isascii():
            return trig in text_lower
        if re.search(r"\b" + re.escape(trig) + r"\b", text_lower) is not None:
            return True
        if len(trig) <= 6 and text_lower.startswith(trig):
            return True
        return False

    def _mark_recent(self, text: str) -> None:
        self._recent.append(text)


def build_engine_for_pet(pet_dir) -> DialogueEngine:
    """Module-level helper for callers that just want 'the engine for X'."""

    return DialogueEngine.from_pet_dir(pet_dir)
