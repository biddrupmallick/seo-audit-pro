"""
Parse uploaded Excel (.xlsx) or CSV files into business dicts.
Expected columns (case-insensitive, order doesn't matter):
  gmb_url, name, owner_name, category, state, rating, reviews,
  address, phone, website, reviews_text
"""
import csv
import io
from typing import List, Dict, Any

import openpyxl


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
}


def _normalise_header(header: str) -> str:
    return header.strip().lower().replace("-", "_").replace(" ", "_")


def _map_columns(headers: List[str]) -> Dict[str, int]:
    """Map canonical column names to column indices."""
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

    return {
        "gmb_url": get("gmb_url"),
        "name": get("name"),
        "owner_name": get("owner_name"),
        "category": get("category"),
        "state": get("state"),
        "rating": rating,
        "reviews": reviews,
        "address": get("address"),
        "phone": get("phone"),
        "website": get("website"),
        "reviews_text": get("reviews_text"),
    }


def parse_excel(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """Parse uploaded file bytes. Returns list of business dicts."""
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
