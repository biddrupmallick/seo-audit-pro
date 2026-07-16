"""
File Prep — convert a raw Excel file into a clean Niche Upload-ready Excel file.

Column B = GMB URL (user-specified, 1-indexed = 2)
Column C = Name    (user-specified, 1-indexed = 3)
Everything else is detected by pattern within each row.
"""
import re
import io
from typing import Optional, Dict, Any, List, Tuple

import openpyxl
from openpyxl import Workbook

from analyzers.ollama_client import ask
from analyzers.text_cleaner import clean_review_text
from analyzers.website_email import get_best_contact_email

# ── Patterns ──────────────────────────────────────────────────────────────────

_GMB_RE     = re.compile(r'google\.com/maps', re.I)
_RATING_RE  = re.compile(r'^[1-5]\.\d$')
_REVIEWS_RE = re.compile(r'^-?\d+\.0$|^-?\d+$')
_ADDRESS_RE = re.compile(r'^\d+\s+\w')
_PHONE_RE   = re.compile(r'[\+\(]?[\d\s\-\(\)]{7,}')
_PHONE_DIGITS_RE = re.compile(r'\d')
_LAT_RE     = re.compile(r'!3d(-?\d+\.\d+)')
_LON_RE     = re.compile(r'!4d(-?\d+\.\d+)')
_OWNER_KEYWORDS = re.compile(r'\b(owner|principal|contact|email|reach|manager)\b', re.I)
_EMAIL_RE   = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_phone(raw: str) -> str:
    """Strip formula prefix and non-digit chars, return plain number."""
    raw = str(raw).strip()
    if raw.startswith('='):
        raw = raw.lstrip('=').strip()
    digits = re.sub(r'[^\d+]', '', raw)
    return digits if len(digits) >= 7 else raw


def _extract_lat_lon(gmb_url: str) -> Tuple[Optional[float], Optional[float]]:
    lat_m = _LAT_RE.search(gmb_url)
    lon_m = _LON_RE.search(gmb_url)
    lat = float(lat_m.group(1)) if lat_m else None
    lon = float(lon_m.group(1)) if lon_m else None
    return lat, lon


def _is_rating(val: str) -> bool:
    return bool(_RATING_RE.match(val.strip()))


def _is_reviews(val: str, already_has_rating: bool) -> bool:
    val = val.strip()
    if not _REVIEWS_RE.match(val):
        return False
    num = abs(float(val))
    # ratings are 1.0-5.0; review counts are usually much larger or whole numbers
    if already_has_rating and 1.0 <= num <= 5.0 and '.' in val:
        return False
    return True


def _is_address(val: str) -> bool:
    return bool(_ADDRESS_RE.match(val.strip()))


def _is_phone(val: str) -> bool:
    raw = str(val).strip()
    if raw.startswith('='):
        raw = raw.lstrip('=').strip()
    digits = len(_PHONE_DIGITS_RE.findall(raw))
    return digits >= 7 and digits <= 15


def _is_owner_info(val: str) -> bool:
    return len(val.split()) >= 10 and bool(_OWNER_KEYWORDS.search(val))


def _is_reviews_text(val: str, owner_info: Optional[str]) -> bool:
    # Long text that isn't owner_info
    if len(val.split()) < 10:
        return False
    if owner_info and val == owner_info:
        return False
    return True


def _ollama_extract(owner_info: str) -> Tuple[str, str]:
    """Extract owner_name and email from owner_info text using Ollama."""
    prompt = f"""Extract the owner name and email address from this text.
Reply in EXACTLY this format (two lines only):
OWNER_NAME: [full name or blank]
EMAIL: [email address or blank]

Text: \"\"\"{owner_info[:800]}\"\"\""""
    raw = ask(prompt, max_tokens=60, temperature=0)
    owner_name, email = "", ""
    for line in raw.splitlines():
        if line.startswith("OWNER_NAME:"):
            owner_name = line.partition(":")[2].strip()
        elif line.startswith("EMAIL:"):
            email = line.partition(":")[2].strip()
            if "@" not in email:
                email = ""
    return owner_name, email


# ── Row parser ────────────────────────────────────────────────────────────────

def _parse_row(row_vals: List[Any], gmb_col: int, name_col: int) -> Dict[str, Any]:
    """
    Parse a single row into structured fields.
    gmb_col and name_col are 0-indexed positions in row_vals.
    """
    result: Dict[str, Any] = {
        "gmb_url": "", "name": "", "category": "", "address": "",
        "phone": "", "website": "", "rating": None, "reviews": None,
        "reviews_text": "", "owner_info": "", "lat": None, "lon": None,
        "state": "Alabama",
    }

    # Fixed columns
    gmb_val = str(row_vals[gmb_col] or "").strip()
    name_val = str(row_vals[name_col] or "").strip()
    result["gmb_url"] = gmb_val
    result["name"] = name_val

    if gmb_val:
        result["lat"], result["lon"] = _extract_lat_lon(gmb_val)

    # Scan remaining cells by pattern
    skip = {gmb_col, name_col}
    texts = []  # collect long text candidates

    for i, val in enumerate(row_vals):
        if i in skip or val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue

        # Website
        if not result["website"] and val_str.startswith(("http://", "https://")) and "google.com" not in val_str:
            result["website"] = val_str
            skip.add(i)
            continue

        # GMB url catch (in case it's not in gmb_col)
        if not result["gmb_url"] and _GMB_RE.search(val_str):
            result["gmb_url"] = val_str
            result["lat"], result["lon"] = _extract_lat_lon(val_str)
            skip.add(i)
            continue

        # Rating
        if result["rating"] is None and _is_rating(val_str):
            result["rating"] = float(val_str)
            skip.add(i)
            continue

        # Reviews
        if result["reviews"] is None and _is_reviews(val_str, result["rating"] is not None):
            result["reviews"] = abs(int(float(val_str)))
            skip.add(i)
            continue

        # Address
        if not result["address"] and _is_address(val_str):
            result["address"] = val_str
            skip.add(i)
            continue

        # Phone
        if not result["phone"] and _is_phone(val_str):
            result["phone"] = _clean_phone(val_str)
            skip.add(i)
            continue

        # Long text — collect for owner_info / reviews_text disambiguation
        if len(val_str.split()) >= 10:
            texts.append((i, val_str))

    # Disambiguate long texts
    for i, val_str in texts:
        if not result["owner_info"] and _is_owner_info(val_str):
            result["owner_info"] = val_str
            skip.add(i)
        elif not result["reviews_text"]:
            result["reviews_text"] = val_str
            skip.add(i)

    # Category — short text not yet assigned, likely category
    for i, val in enumerate(row_vals):
        if i in skip or val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue
        if not result["category"] and 1 <= len(val_str.split()) <= 5 and not _is_phone(val_str):
            result["category"] = val_str
            break

    return result


# ── Main processor ────────────────────────────────────────────────────────────

def process_file(
    file_bytes: bytes,
    gmb_col: int,   # 1-indexed (column B = 2)
    name_col: int,  # 1-indexed (column C = 3)
    progress_callback=None,
) -> bytes:
    """
    Read raw Excel, process each row, return clean Excel bytes.
    progress_callback(current, total, message) called per row if provided.
    """
    wb_in = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws_in = wb_in.active

    gmb_idx  = gmb_col - 1   # convert to 0-indexed
    name_idx = name_col - 1

    # Collect data rows (skip header row 1)
    rows = []
    for r in range(2, ws_in.max_row + 1):
        vals = [ws_in.cell(r, c).value for c in range(1, ws_in.max_column + 1)]
        if any(v for v in vals):
            rows.append(vals)

    total = len(rows)

    # Build output workbook
    wb_out = Workbook()
    ws_out = wb_out.active
    ws_out.title = "Clean Data"

    headers = [
        "name", "category", "address", "phone", "website",
        "rating", "reviews", "reviews_text", "owner_name", "email",
        "lat", "lon", "state", "gmb_url", "owner_info"
    ]
    ws_out.append(headers)

    for idx, row_vals in enumerate(rows, 1):
        if progress_callback:
            progress_callback(idx, total, f"Processing row {idx}/{total}…")

        parsed = _parse_row(row_vals, gmb_idx, name_idx)

        # Clean reviews_text
        if parsed["reviews_text"]:
            cleaned, _ = clean_review_text(parsed["reviews_text"])
            parsed["reviews_text"] = cleaned

        # Ollama: extract owner_name + email from owner_info
        owner_name, email = "", ""
        if parsed["owner_info"]:
            owner_name, email = _ollama_extract(parsed["owner_info"])

        # Fallback: scrape website for email
        if not email and parsed["website"]:
            try:
                email = get_best_contact_email(parsed["website"])
            except Exception:
                email = ""

        ws_out.append([
            parsed["name"],
            parsed["category"],
            parsed["address"],
            parsed["phone"],
            parsed["website"],
            parsed["rating"],
            parsed["reviews"],
            parsed["reviews_text"],
            owner_name,
            email,
            parsed["lat"],
            parsed["lon"],
            parsed["state"],
            parsed["gmb_url"],
            parsed["owner_info"],
        ])

    out = io.BytesIO()
    wb_out.save(out)
    return out.getvalue()
