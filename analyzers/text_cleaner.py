"""
Clean raw Google Maps review text pasted from the browser.
Strips reviewer names, metadata, UI elements, and blank entries.
"""
import re
from typing import Tuple, Dict, Any

_NOISE_RE = re.compile(
    r'^(Like|Share|More|Sort|All)$'
    r'|^Local Guide\s*·.*'
    r'|^\d+\s+(review|photo|year|month|week|day)s?(\s+ago)?$'
    r'|^\d+\s+reviews?(\s*·\s*\d+\s+photos?)?$'
    r'|^(a|an)\s+(year|month|week|day|hour|minute)\s+ago$'
    r'|^Edited\s+.*ago$'
    r'|^\d+$',
    re.IGNORECASE,
)

_OWNER_HEADER_RE = re.compile(r'^Response from the owner\b.*\bago$', re.IGNORECASE)


def _is_noise(line: str) -> bool:
    return bool(_NOISE_RE.match(line.strip()))


def _is_owner_header(line: str) -> bool:
    return bool(_OWNER_HEADER_RE.match(line.strip()))


def _ends_sentence(line: str) -> bool:
    return line.rstrip()[-1:] in '.!?…”’"'


def _merge_wrapped_lines(lines: list) -> list:
    """Rejoin a review that got line-wrapped mid-sentence (no trailing
    punctuation followed by a lowercase continuation)."""
    merged: list = []
    for line in lines:
        if merged and not _ends_sentence(merged[-1]) and line[:1].islower():
            merged[-1] = merged[-1] + ' ' + line
        else:
            merged.append(line)
    return merged


def _has_content(line: str) -> bool:
    return len(line.strip().split()) >= 5


def _extract_topics(lines: list) -> Tuple[list, int]:
    """Pull the keyword/count block from the top (e.g. 'repairs\\n2\\nquality of work\\n2')."""
    topics = []
    i = 0
    while i < len(lines) and lines[i].strip() in ('Sort', 'All', ''):
        i += 1
    while i < len(lines) - 1:
        word = lines[i].strip()
        nxt = lines[i + 1].strip()
        if word and nxt.isdigit() and len(word.split()) <= 4:
            topics.append(word)
            i += 2
        else:
            break
    return topics, i


def clean_review_text(raw: str) -> Tuple[str, Dict[str, Any]]:
    """
    Clean raw Google Maps review text.
    Returns (cleaned_text, stats_dict).
    """
    lines = raw.splitlines()
    original_chars = len(raw)

    topics, start = _extract_topics(lines)

    review_lines = []
    skip_next_as_owner_reply = False
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        if _is_owner_header(line):
            skip_next_as_owner_reply = True
            continue
        if skip_next_as_owner_reply:
            skip_next_as_owner_reply = False
            continue
        if _is_noise(line):
            continue
        if not _has_content(line):
            continue
        review_lines.append(line)

    review_lines = _merge_wrapped_lines(review_lines)

    # Deduplicate by first 60 chars
    seen: set = set()
    unique = []
    for r in review_lines:
        key = r[:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    parts = []
    if topics:
        parts.append(f"Common topics: {', '.join(topics)}")
    parts.extend(unique)

    cleaned = "\n---\n".join(parts)

    return cleaned, {
        "original_chars": original_chars,
        "cleaned_chars": len(cleaned),
        "chars_saved": original_chars - len(cleaned),
        "reviews_found": len(unique),
        "topics": topics,
    }
