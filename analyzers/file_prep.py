"""
File Prep — convert a raw Excel file into a clean Niche Upload-ready Excel file.
Pattern-based field detection — no column position assumptions except gmb_col / name_col.
"""
import re
import io
from typing import Optional, Dict, Any, List, Tuple, Callable

import openpyxl
from openpyxl import Workbook

from analyzers.ollama_client import ask
from analyzers.text_cleaner import clean_review_text
from analyzers.website_email import scrape_website_contact_info
from analyzers.social_screenshot import find_email_from_socials

# ── Patterns ──────────────────────────────────────────────────────────────────

_GMB_RE          = re.compile(r'google\.com/maps', re.I)
_RATING_RE       = re.compile(r'^[1-5]\.\d$')
_REVIEWS_RE      = re.compile(r'^-?\d+\.0$|^-?\d+$')
_ADDRESS_RE      = re.compile(r'^\d+\s+\w')
_PHONE_DIGITS_RE = re.compile(r'\d')
_LAT_RE          = re.compile(r'!3d(-?\d+\.\d+)')
_LON_RE          = re.compile(r'!4d(-?\d+\.\d+)')
_OWNER_KEYWORDS  = re.compile(r'\b(owner|principal|contact|email|reach|manager)\b', re.I)
_EMAIL_RE        = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}')

_US_STATES = {
    "Alabama","Alaska","Arizona","Arkansas","California","Colorado","Connecticut",
    "Delaware","Florida","Georgia","Hawaii","Idaho","Illinois","Indiana","Iowa",
    "Kansas","Kentucky","Louisiana","Maine","Maryland","Massachusetts","Michigan",
    "Minnesota","Mississippi","Missouri","Montana","Nebraska","Nevada",
    "New Hampshire","New Jersey","New Mexico","New York","North Carolina",
    "North Dakota","Ohio","Oklahoma","Oregon","Pennsylvania","Rhode Island",
    "South Carolina","South Dakota","Tennessee","Texas","Utah","Vermont",
    "Virginia","Washington","West Virginia","Wisconsin","Wyoming",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_phone(raw: str) -> str:
    raw = str(raw).strip()
    if raw.startswith('='):
        raw = raw.lstrip('=').strip()
    digits = re.sub(r'[^\d+]', '', raw)
    return digits if len(digits) >= 7 else raw


def _extract_lat_lon(gmb_url: str) -> Tuple[Optional[float], Optional[float]]:
    lat_m = _LAT_RE.search(gmb_url)
    lon_m = _LON_RE.search(gmb_url)
    return (float(lat_m.group(1)) if lat_m else None,
            float(lon_m.group(1)) if lon_m else None)


def _is_rating(val: str) -> bool:
    return bool(_RATING_RE.match(val.strip()))


def _is_reviews(val: str, already_has_rating: bool) -> bool:
    val = val.strip()
    if not _REVIEWS_RE.match(val):
        return False
    num = abs(float(val))
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
    return 7 <= digits <= 15


def _is_owner_info(val: str) -> bool:
    return len(val.split()) >= 10 and bool(_OWNER_KEYWORDS.search(val))


def _ollama_extract(owner_info: str) -> Tuple[str, str]:
    prompt = f"""Extract the owner's full name and their personal/business email address from this text.
Reply in EXACTLY this format (two lines only):
OWNER_NAME: [full first and last name, or blank if not found]
EMAIL: [email address only if explicitly mentioned in the text, otherwise blank]

Text: \"\"\"{owner_info[:800]}\"\"\""""
    raw = ask(prompt, max_tokens=60, temperature=0)
    owner_name, email = "", ""
    for line in raw.splitlines():
        if line.startswith("OWNER_NAME:"):
            owner_name = line.partition(":")[2].strip()
        elif line.startswith("EMAIL:"):
            raw_email = line.partition(":")[2].strip()
            m = _EMAIL_RE.search(raw_email)
            email = m.group(0) if m else ""
    return owner_name, email


# ── Row parser ────────────────────────────────────────────────────────────────

def _parse_row(row_vals: List[Any], gmb_col: int, name_col: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "gmb_url": "", "name": "", "category": "", "address": "",
        "phone": "", "website": "", "rating": None, "reviews": None,
        "reviews_text": "", "owner_info": "", "lat": None, "lon": None,
        "state": "Alabama",
    }

    gmb_val  = str(row_vals[gmb_col]  or "").strip()
    name_val = str(row_vals[name_col] or "").strip()
    result["gmb_url"] = gmb_val
    result["name"]    = name_val

    if gmb_val:
        result["lat"], result["lon"] = _extract_lat_lon(gmb_val)

    skip  = {gmb_col, name_col}
    texts = []
    _JUNK_CELLS = {"website", "phone", "email", "address", "name", "category",
                   "closed", "open", "directions", "n/a"}

    for i, val in enumerate(row_vals):
        if i in skip or val is None:
            continue
        val_str = str(val).strip()
        if not val_str or val_str.lower() in _JUNK_CELLS or val_str.startswith("#"):
            continue

        if (not result["website"]
                and val_str.startswith(("http://", "https://"))
                and "google.com" not in val_str
                and "gstatic.com" not in val_str
                and "googleapis.com" not in val_str
                and not val_str.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))):
            result["website"] = val_str; skip.add(i); continue

        if not result["gmb_url"] and _GMB_RE.search(val_str):
            result["gmb_url"] = val_str
            result["lat"], result["lon"] = _extract_lat_lon(val_str)
            skip.add(i); continue

        if result["rating"] is None and _is_rating(val_str):
            result["rating"] = float(val_str); skip.add(i); continue

        if result["reviews"] is None and _is_reviews(val_str, result["rating"] is not None):
            result["reviews"] = abs(int(float(val_str))); skip.add(i); continue

        if not result["address"] and _is_address(val_str):
            result["address"] = val_str; skip.add(i); continue

        if not result["phone"] and _is_phone(val_str):
            result["phone"] = _clean_phone(val_str); skip.add(i); continue

        if len(val_str.split()) >= 10:
            texts.append((i, val_str))

    for i, val_str in texts:
        if not result["owner_info"] and _is_owner_info(val_str):
            result["owner_info"] = val_str; skip.add(i)
        elif not result["reviews_text"]:
            result["reviews_text"] = val_str; skip.add(i)

    for i, val in enumerate(row_vals):
        if i in skip or val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue
        if not result["category"] and 1 <= len(val_str.split()) <= 5 and not _is_phone(val_str) and val_str not in _US_STATES:
            result["category"] = val_str
            break

    return result


# ── Main processor ────────────────────────────────────────────────────────────

def process_file(
    file_bytes: bytes,
    gmb_col: int,
    name_col: int,
    progress_callback: Optional[Callable] = None,
) -> bytes:
    """
    Read raw Excel, process each row, return clean Excel bytes.
    progress_callback(current, total, message, row_result) called per row.
    row_result = {name, owner_name, email, email_source, rating, category, log_line}
    """
    wb_in      = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    wb_formula = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=False)
    ws_in      = wb_in.active
    ws_formula = wb_formula.active

    gmb_idx  = gmb_col  - 1
    name_idx = name_col - 1

    def _cell_value(r, c):
        val = ws_in.cell(r, c).value
        # If cell is empty or an Excel error, try reading the raw formula
        # e.g. =+12055551234 shows as #ERROR! with data_only=True
        if val is None or (isinstance(val, str) and val.startswith("#")):
            formula = ws_formula.cell(r, c).value
            if formula and str(formula).startswith("="):
                return str(formula)
        return val

    rows = []
    for r in range(2, ws_in.max_row + 1):
        vals = [_cell_value(r, c) for c in range(1, ws_in.max_column + 1)]
        if any(v for v in vals):
            rows.append(vals)

    total = len(rows)

    wb_out = Workbook()
    ws_out = wb_out.active
    ws_out.title = "Clean Data"
    ws_out.append([
        "Business Name", "Category", "Address", "Phone", "Website",
        "Rating", "Review Count", "Customer Reviews", "Owner Name", "Email",
        "Facebook", "Instagram", "Twitter", "LinkedIn",
        "YouTube", "TikTok", "Pinterest", "Yelp",
        "Latitude", "Longitude", "State", "GMB URL",
    ])

    for idx, row_vals in enumerate(rows, 1):
        parsed = _parse_row(row_vals, gmb_idx, name_idx)
        name = parsed["name"]
        if not name:
            total -= 1
            continue

        # Clean reviews_text
        if parsed["reviews_text"]:
            cleaned, _ = clean_review_text(parsed["reviews_text"])
            parsed["reviews_text"] = cleaned

        # Ollama extraction
        owner_name, ollama_email = "", ""
        if parsed["owner_info"]:
            owner_name, ollama_email = _ollama_extract(parsed["owner_info"])

        # Always scrape website — ground truth for email + socials
        site_info: Dict[str, str] = {}
        if parsed["website"]:
            try:
                site_info = scrape_website_contact_info(parsed["website"])
            except Exception:
                site_info = {}

        # Website email takes priority over Ollama (Ollama can hallucinate)
        email, email_source = "", "not_found"
        if site_info.get("email"):
            email = site_info["email"]
            email_source = "website"
        elif ollama_email:
            email = ollama_email
            email_source = "ollama"

        social_cols = ["facebook", "instagram", "twitter", "linkedin", "youtube", "tiktok", "pinterest", "yelp"]
        socials_found = [p for p in social_cols if site_info.get(p)]

        # Social screenshot fallback — try Facebook → Instagram → Yelp
        screenshot_platform = ""
        if not email and socials_found:
            social_urls = {p: site_info.get(p, "") for p in social_cols}
            email, screenshot_platform = find_email_from_socials(social_urls)
            if email:
                email_source = "social"

        # Build log line
        social_note = f" · {len(socials_found)} social{'s' if len(socials_found) != 1 else ''}" if socials_found else ""
        if email_source == "ollama":
            log_line = f"{name} — {owner_name} — email via Ollama{social_note}"
            log_type = "success"
        elif email_source == "website":
            log_line = f"{name} — {owner_name or '—'} — email from website{social_note}"
            log_type = "website"
        elif email_source == "social":
            log_line = f"{name} — {owner_name or '—'} — email from {screenshot_platform} screenshot{social_note}"
            log_type = "social"
        else:
            log_line = f"{name} — no email found{social_note}"
            log_type = "warning"
            if not owner_name:
                log_line = f"{name} — owner and email not found{social_note}"
                log_type = "error"

        row_result = {
            "name":                name,
            "owner_name":          owner_name,
            "email":               email,
            "email_source":        email_source,
            "screenshot_platform": screenshot_platform,
            "rating":              parsed["rating"],
            "category":            parsed["category"],
            "socials":             socials_found,
            "log_line":            log_line,
            "log_type":            log_type,
        }

        if progress_callback:
            progress_callback(idx, total, f"Processing {idx}/{total}: {name}", row_result)

        ws_out.append([
            parsed["name"], parsed["category"], parsed["address"],
            parsed["phone"], parsed["website"], parsed["rating"],
            parsed["reviews"], parsed["reviews_text"],
            owner_name, email,
            site_info.get("facebook",  ""),
            site_info.get("instagram", ""),
            site_info.get("twitter",   ""),
            site_info.get("linkedin",  ""),
            site_info.get("youtube",   ""),
            site_info.get("tiktok",    ""),
            site_info.get("pinterest", ""),
            site_info.get("yelp",      ""),
            parsed["lat"], parsed["lon"], parsed["state"],
            parsed["gmb_url"],
        ])

    out = io.BytesIO()
    wb_out.save(out)
    return out.getvalue()
