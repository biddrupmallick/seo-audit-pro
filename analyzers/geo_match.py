"""
Geo-matching: extract lat/lon from GMB URLs and find nearest competitors
using the Haversine formula. No external API needed.
"""
import re
import math
from typing import Optional, List, Dict, Any


def extract_latlon(gmb_url: str) -> Optional[tuple]:
    """Extract (lat, lon) from any Google Maps URL format."""
    if not gmb_url:
        return None

    # Format 1: !3d<lat>!4d<lon> (place data URLs)
    m = re.search(r'!3d(-?\d+\.\d+).*?!4d(-?\d+\.\d+)', gmb_url)
    if m:
        return float(m.group(1)), float(m.group(2))

    # Format 2: /@<lat>,<lon>,<zoom>z
    m = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', gmb_url)
    if m:
        return float(m.group(1)), float(m.group(2))

    # Format 3: ?q=<lat>,<lon>
    m = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', gmb_url)
    if m:
        return float(m.group(1)), float(m.group(2))

    # Format 4: ll=<lat>,<lon>
    m = re.search(r'll=(-?\d+\.\d+),(-?\d+\.\d+)', gmb_url)
    if m:
        return float(m.group(1)), float(m.group(2))

    return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_competitors(businesses: List[Dict], n: int = 3) -> List[Dict]:
    """
    For each business, find its n nearest others in the same category.
    Adds 'latlon', 'nearest_competitors' keys to each business dict.
    Returns the enriched list.
    """
    # Extract coords
    for biz in businesses:
        biz["latlon"] = extract_latlon(biz.get("gmb_url", ""))

    # Match competitors
    for biz in businesses:
        if not biz["latlon"]:
            biz["nearest_competitors"] = []
            continue

        lat1, lon1 = biz["latlon"]
        cat = (biz.get("category") or "").lower().strip()

        distances = []
        for other in businesses:
            if other is biz or not other.get("latlon"):
                continue
            # Same category preferred but not required
            other_cat = (other.get("category") or "").lower().strip()
            lat2, lon2 = other["latlon"]
            dist = haversine_miles(lat1, lon1, lat2, lon2)
            distances.append({
                "name": other.get("name", ""),
                "website": other.get("website", ""),
                "distance_miles": round(dist, 2),
                "rating": other.get("rating"),
                "reviews": other.get("reviews"),
                "same_category": cat == other_cat,
            })

        # Sort: same category first, then by distance
        distances.sort(key=lambda x: (not x["same_category"], x["distance_miles"]))
        biz["nearest_competitors"] = distances[:n]

    return businesses
