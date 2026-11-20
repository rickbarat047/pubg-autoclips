"""Text normalisation and IGN matching helpers (pure functions, easily tested)."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Characters commonly misread by OCR in gamer tags.
_CONFUSIONS = str.maketrans({
    "0": "o", "O": "o", "o": "o",
    "1": "l", "I": "l", "L": "l", "l": "l", "|": "l", "!": "l",
    "5": "s", "S": "s", "s": "s",
    "8": "b", "B": "b", "b": "b",
    "6": "g", "G": "g", "g": "g",
    "2": "z", "Z": "z", "z": "z",
    "4": "a", "A": "a", "a": "a",
    "7": "t", "T": "t", "t": "t",
    "9": "g",
})

# PUBG kill feed decorations that should not affect matching.
_SEPARATORS = set("[](){}<>-_–—·•|=+*.:,/'\"\\~ ")


def normalize_text(text: str, aggressive: bool = True) -> str:
    """Lower-case, strip decorations and (optionally) map OCR confusions."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    out = []
    for ch in text:
        if ch in _SEPARATORS:
            continue
        out.append(_CONFUSIONS.get(ch, ch) if aggressive else ch)
    return "".join(out)


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s\[\]()<>\-_|]+", str(text)) if t]


def ign_match_score(ocr_text: str, ign: str) -> float:
    """Return a 0..1 similarity between OCR text and the configured IGN.

    The score is the best match of the normalised IGN against any token or
    the full normalised kill-feed line.  It tolerates surrounding text such
    as the victim name or weapon icons.
    """
    target = normalize_text(ign)
    if not target:
        return 0.0
    norm = normalize_text(ocr_text)
    if not norm:
        return 0.0
    if target == norm:
        return 1.0
    if target in norm:
        # e.g. "Player1 killed Player2" — presence is strong evidence.
        return 0.95

    best = 0.0
    for token in _tokens(ocr_text):
        ntok = normalize_text(token)
        if not ntok:
            continue
        if ntok == target:
            return 1.0
        # Substring matching is only meaningful for sufficiently long tokens;
        # otherwise every short word inside a name would look like a match.
        min_token = max(3, len(target) // 2)
        if len(ntok) >= min_token and (target in ntok or ntok in target):
            best = max(best, 0.9)
        else:
            ratio = SequenceMatcher(None, target, ntok).ratio()
            # Require high similarity, and ignore very short tokens entirely.
            if len(target) >= 4 and len(ntok) >= 3 and ratio >= 0.75:
                best = max(best, ratio)
    return best


def is_match(ocr_text: str, ign: str, threshold: float = 0.82) -> bool:
    return ign_match_score(ocr_text, ign) >= threshold


def classify_feed_line(text: str, ign: str, threshold: float = 0.82) -> str:
    """Classify a kill-feed line relative to the player's IGN.

    Returns one of: 'confirmed', 'possible', 'unrelated'.
    OCR alone cannot reliably distinguish kills from knocks; the caller must
    not upgrade 'possible' to a confirmed kill without further evidence.
    """
    score = ign_match_score(text, ign)
    if score >= threshold:
        return "confirmed"
    if score >= max(0.45, threshold - 0.25):
        return "possible"
    return "unrelated"


def looks_like_knock(text: str) -> bool:
    """Detect explicit knock indicators when the feed text exposes them."""
    t = normalize_text(text, aggressive=False)
    indicators = ("knocked", "knock", "down", "dbno", "bleeding")
    return any(ind in t for ind in indicators)
