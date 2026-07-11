"""
Parse uploaded Excel (.xlsx) or CSV files into business dicts.

Required columns: gmb_url, name, website, category, state, rating, reviews
Optional columns: owner_name, address, phone, reviews_text, owner_info

All column names are flexible (case-insensitive, spaces/underscores interchangeable).
owner_info: free-text about the owner — AI extracts owner_name and owner_email from it.
"""
import csv
import io
import json
import re
from typing import List, Dict, Any

import openpyxl
from analyzers.ollama_client import chat


COLUMN_ALIASES = {
    "gmb_url": ["gmb_url", "gmb url", "google_maps_url", "maps_url", "google maps url", "url", "maps url"],
    "name": ["name", "business_name", "business name", "company", "company name"],
    "owner_name": ["owner_name", "owner", "owner name", "contact", "contact name"],
    "category": ["category", "niche", "business_type", "business type", "type"],
    "state": ["state", "state_name", "location", "region"],
    "rating": ["rating", "star_rating", "stars", "avg_rating", "average rating"],
    "reviews": ["reviews", "review_count", "num_reviews", "number of reviews", "total reviews"],
    "address": ["address", "full_address", "street address"],
    "phone": ["phone", "phone_number", "telephone", "tel"],
    "website": ["website", "url", "web", "site", "website_url"],
    "reviews_text": ["reviews_text", "review_text", "reviews text", "customer reviews", "comments", "review comments"],
    "owner_info": ["owner_info", "owner_text", "owner info", "owner details", "owner_details", "about_owner", "about owner"],
}


def _extract_email(text: str) -> str:
    """Reliable regex extraction for email addresses."""
    # Require lowercase-only TLD and word boundary to avoid matching trailing words
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-z]{2,}(?=[\s,;\"'\)<>\]|]|$)", text)
    return match.group(0).rstrip(".") if match else ""


def _extract_name_regex_fallback(text: str) -> str:
    """Basic regex fallback when Ollama is unavailable."""
    m = re.search(
        r"(?:owner|proprietor|manager|contact)\b.*?\bis\s+((?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text)
    if m:
        return m.group(1).strip()
    return ""


def extract_owner_info_single(biz: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract owner name and email from a single business's owner_info text.
    Uses Ollama for name, regex for email. Returns {"owner_name": ..., "owner_email": ...}.
    """
    info_text = biz.get("owner_info", "")
    result = {"owner_name": biz.get("owner_name", ""), "owner_email": biz.get("owner_email", "")}

    if not info_text:
        return result

    # Always regex for email — fast and reliable
    if not result["owner_email"]:
        result["owner_email"] = _extract_email(info_text)

    # Ollama for name if not already set
    if not result["owner_name"]:
        prompt = f"""Extract the owner or manager's full name from this text.
Return ONLY a JSON object: {{"owner_name": "Full Name"}}
If no name found, return {{"owner_name": ""}}
No explanation, no markdown.

Text: \"\"\"{info_text}\"\"\""""
        try:
            raw = chat([{"role": "user", "content": prompt}], max_tokens=100, temperature=0)
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                result["owner_name"] = data.get("owner_name", "").strip()
        except Exception:
            result["owner_name"] = _extract_name_regex_fallback(info_text)

    return result


def enrich_owner_info(businesses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch enrich all businesses with owner info (used as fallback/non-pipeline path)."""
    for biz in businesses:
        if biz.get("owner_info"):
            extracted = extract_owner_info_single(biz)
            if not biz.get("owner_name"):
                biz["owner_name"] = extracted["owner_name"]
            if not biz.get("owner_email"):
                biz["owner_email"] = extracted["owner_email"]
    return businesses


def _normalise_header(header: str) -> str:
    return header.strip().lower().replace("-", "_").replace(" ", "_")


def _map_columns(headers: List[str]) -> Dict[str, int]:
    normalised = [_normalise_header(h) for h in headers]
    mapping = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            alias_n = alias.replace(" ", "_")
            if alias_n in normalised:
                mapping[canon] = normalised.index(alias_n)
                break
    return mapping


def _row_to_dict(row: List[Any], col_map: Dict[str, int]) -> Dict[str, Any]:
    def get(key):
        idx = col_map.get(key)
        if idx is None or idx >= len(row):
            return ""
        val = row[idx]
        return str(val).strip() if val is not None else ""

    rating = get("rating")
    try:
        rating = float(rating)
    except Exception:
        rating = None

    reviews = get("reviews")
    try:
        reviews = int(float(reviews))
    except Exception:
        reviews = None

    owner_info_text = get("owner_info")
    # Email can be extracted immediately via regex; name needs Ollama (done in enrich_owner_info)
    owner_email = _extract_email(owner_info_text) if owner_info_text else ""

    return {
        "gmb_url": get("gmb_url"),
        "name": get("name"),
        "owner_name": get("owner_name"),
        "owner_email": owner_email,
        "category": get("category"),
        "state": get("state"),
        "rating": rating,
        "reviews": reviews,
        "address": get("address"),
        "phone": get("phone"),
        "website": get("website"),
        "reviews_text": get("reviews_text"),
        "owner_info": owner_info_text,
    }


def parse_excel(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse uploaded file bytes. Returns raw business dicts (call enrich_owner_info separately)."""
    if filename.lower().endswith(".csv"):
        return _parse_csv(file_bytes)
    return _parse_xlsx(file_bytes)


def _parse_xlsx(file_bytes: bytes) -> List[Dict]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h) if h is not None else "" for h in rows[0]]
    col_map = _map_columns(headers)
    businesses = []
    for row in rows[1:]:
        row = list(row)
        biz = _row_to_dict(row, col_map)
        if biz["name"] or biz["website"] or biz["gmb_url"]:
            businesses.append(biz)
    return businesses


def _parse_csv(file_bytes: bytes) -> List[Dict]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    headers = rows[0]
    col_map = _map_columns(headers)
    businesses = []
    for row in rows[1:]:
        biz = _row_to_dict(row, col_map)
        if biz["name"] or biz["website"] or biz["gmb_url"]:
            businesses.append(biz)
    return businesses
