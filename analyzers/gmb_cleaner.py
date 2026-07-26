"""
GMB Cleaner — turn a raw Google Maps scrape (CSV or Excel) into a clean file with
gmb_url, name, rating, reviews, category, address, phone, website, lat, lon.

The first 5 columns (gmb url, name, rating, reviews, category) are already labelled
correctly by the scraper. Everything after that is untitled DOM class names
(W4Efsd, doJOZc, ah5Ghc...) whose column position shifts row to row depending on
which optional fields Google rendered for that listing, so address/phone/website
are found by pattern instead of position — reusing the same detectors as File Prep.
"""
import csv
import io
from typing import List, Dict, Any, Optional

import openpyxl
from openpyxl import Workbook

from analyzers.file_prep import _extract_lat_lon, _is_address, _is_phone, _is_website, _clean_phone

_CATEGORY_JUNK = {"·", "-", "—", "n/a", "website", "directions", "closed", "open"}


def _is_usable_category(s: str) -> bool:
    s = s.strip()
    if not s or s.lower() in _CATEGORY_JUNK:
        return False
    return any(c.isalpha() for c in s)


def _to_float(raw: str) -> Optional[float]:
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _read_csv_rows(file_bytes: bytes) -> List[List[Any]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def _read_xlsx_rows(file_bytes: bytes) -> List[List[Any]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    return list(ws.iter_rows(values_only=True))


def _parse_row(row: List[Any]) -> Optional[Dict[str, Any]]:
    def cell(i: int) -> str:
        return str(row[i]).strip() if i < len(row) and row[i] is not None else ""

    gmb_url = cell(0)
    name = cell(1)
    if not gmb_url or not name:
        return None

    rating = _to_float(cell(2))
    reviews_raw = _to_float(cell(3))
    reviews = abs(int(reviews_raw)) if reviews_raw is not None else None

    category = cell(4)
    if not _is_usable_category(category):
        category = ""

    lat, lon = _extract_lat_lon(gmb_url)

    address = phone = website = ""
    for raw_cell in row[5:]:
        if raw_cell is None:
            continue
        s = str(raw_cell).strip()
        if not s or s.startswith("#"):
            continue
        if not address and _is_address(s):
            address = s
        elif not phone and _is_phone(s):
            phone = _clean_phone(s)
        elif not website and _is_website(s):
            website = s

    return {
        "gmb_url": gmb_url, "name": name, "rating": rating, "reviews": reviews,
        "category": category, "address": address, "phone": phone,
        "website": website, "lat": lat, "lon": lon,
    }


def clean_gmb_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Parse a raw Google Maps scrape export and return deduped, clean business rows + stats."""
    if filename.lower().endswith(".csv"):
        rows = _read_csv_rows(file_bytes)
    else:
        rows = _read_xlsx_rows(file_bytes)

    if not rows:
        return {"businesses": [], "stats": {
            "total_rows": 0, "dropped_blank_or_noname": 0,
            "duplicates_removed": 0, "clean_rows": 0, "phone_recovered": 0,
        }}

    data_rows = rows[1:]  # first row is the header
    total_rows = len(data_rows)

    businesses = []
    seen_urls = set()
    dropped_blank = 0
    duplicates_removed = 0
    phone_recovered = 0

    for row in data_rows:
        row = list(row)
        if not any(str(c).strip() for c in row if c is not None):
            dropped_blank += 1
            continue

        biz = _parse_row(row)
        if biz is None:
            dropped_blank += 1
            continue

        if biz["gmb_url"] in seen_urls:
            duplicates_removed += 1
            continue
        seen_urls.add(biz["gmb_url"])

        if biz["phone"]:
            phone_recovered += 1
        businesses.append(biz)

    stats = {
        "total_rows": total_rows,
        "dropped_blank_or_noname": dropped_blank,
        "duplicates_removed": duplicates_removed,
        "clean_rows": len(businesses),
        "phone_recovered": phone_recovered,
    }
    return {"businesses": businesses, "stats": stats}


EXPORT_HEADERS = ["GMB URL", "Name", "Rating", "Reviews", "Category", "Address", "Phone", "Website", "Lat", "Lon"]


def build_export_excel(businesses: List[Dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Clean Data"
    ws.append(EXPORT_HEADERS)
    for b in businesses:
        ws.append([
            b["gmb_url"], b["name"], b["rating"], b["reviews"], b["category"],
            b["address"], b["phone"], b["website"], b["lat"], b["lon"],
        ])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
