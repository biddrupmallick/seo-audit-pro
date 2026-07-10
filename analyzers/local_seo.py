import re
import json
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage

# Phone number patterns
PHONE_PATTERNS = [
    re.compile(r"\+?1?\s*[\(\-\.]?\d{3}[\)\-\.\s]\s*\d{3}[\-\.\s]\d{4}", re.IGNORECASE),
    re.compile(r"\(\d{3}\)\s*\d{3}[\-\.]\d{4}", re.IGNORECASE),
    re.compile(r"\b\d{3}[\-\.]\d{3}[\-\.]\d{4}\b", re.IGNORECASE),
    re.compile(r"\+\d{1,3}\s*\(?\d{2,4}\)?\s*\d{3,4}[\-\s]\d{3,4}", re.IGNORECASE),
]

# Address/street patterns
ADDRESS_PATTERNS = [
    re.compile(r"\b\d{1,5}\s+[A-Za-z0-9\s\.\,]+\b(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Way|Wy|Circle|Cir|Highway|Hwy|Parkway|Pkwy)\b", re.IGNORECASE),
    re.compile(r"\b(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Way|Wy)\s*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\b", re.IGNORECASE),
]

# LocalBusiness schema types
LOCAL_BUSINESS_TYPES = {
    "LocalBusiness", "Restaurant", "Store", "MedicalBusiness", "HealthAndBeautyBusiness",
    "AutoDealer", "Bakery", "BarOrPub", "Brewery", "CafeOrCoffeeShop", "CasualDiningRestaurant",
    "Dentist", "DryCleaningOrLaundry", "ElectronicsStore", "FastFoodRestaurant",
    "FinancialService", "FoodEstablishment", "GroceryStore", "HardwareStore", "HVACBusiness",
    "HomeAndConstructionBusiness", "HotelOrMotel", "LegalService", "LiquorStore",
    "Locksmith", "LodgingBusiness", "MedicalOrganization", "MovieRentalStore", "MovieTheater",
    "MovingCompany", "MusicStore", "NailSalon", "Notary", "OfficeEquipmentStore",
    "Optician", "PetStore", "Pharmacy", "Physician", "Plumber", "PoliceStation",
    "PostOffice", "RealEstateAgent", "SelfStorage", "ShoeStore", "ShoppingCenter",
    "SportingGoodsStore", "TattooParlorOrBodyPiercingShop", "TireShop", "TouristInformationCenter",
    "TravelAgency", "VeterinaryCare", "WholesaleStore", "Winery",
}

# Location keyword patterns (generic city/town indicators)
LOCATION_URL_PATTERNS = [
    re.compile(r"/location[s]?/", re.IGNORECASE),
    re.compile(r"/area[s]?/", re.IGNORECASE),
    re.compile(r"/service[-_]area/", re.IGNORECASE),
    re.compile(r"/city/", re.IGNORECASE),
    re.compile(r"/region/", re.IGNORECASE),
]

# Common location words in titles and H1s
LOCATION_WORDS_PATTERN = re.compile(
    r"\b(?:city|town|county|district|borough|village|state|province|region|area|local|near|nearby|"
    r"neighborhood|neighbourhood|zip|postal|metro|metropolitan)\b",
    re.IGNORECASE,
)


def _find_phone(text: str) -> str:
    """Return first phone number found in text, or empty string."""
    for pattern in PHONE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return ""


def _has_address(text: str) -> bool:
    """Check if text contains an address pattern."""
    for pattern in ADDRESS_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _extract_schema_types(html: str) -> List[str]:
    """Extract all @type values from JSON-LD scripts."""
    types = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = []
                if isinstance(data, dict):
                    if "@graph" in data:
                        items = data["@graph"]
                    else:
                        items = [data]
                elif isinstance(data, list):
                    items = data
                for item in items:
                    if isinstance(item, dict):
                        t = item.get("@type", "")
                        if isinstance(t, list):
                            types.extend(t)
                        elif t:
                            types.append(t)
            except Exception:
                pass
    except Exception:
        pass
    return types


def _check_local_business_schema(html: str) -> Dict[str, Any]:
    """Check for LocalBusiness schema and its required fields."""
    result = {
        "has_local_business_schema": False,
        "has_opening_hours": False,
        "has_review_schema": False,
        "schema_type": None,
        "missing_required_fields": [],
    }
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = []
                if isinstance(data, dict):
                    if "@graph" in data:
                        items = data["@graph"]
                    else:
                        items = [data]
                elif isinstance(data, list):
                    items = data

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    schema_type = item.get("@type", "")
                    if isinstance(schema_type, list):
                        type_set = set(schema_type)
                    else:
                        type_set = {schema_type}

                    if type_set & LOCAL_BUSINESS_TYPES:
                        result["has_local_business_schema"] = True
                        result["schema_type"] = list(type_set & LOCAL_BUSINESS_TYPES)[0]

                        # Check required fields
                        missing = []
                        if not item.get("name"):
                            missing.append("name")
                        if not item.get("address"):
                            missing.append("address")
                        if not item.get("telephone"):
                            missing.append("telephone")
                        if not item.get("url"):
                            missing.append("url")
                        result["missing_required_fields"] = missing

                        if item.get("openingHours") or item.get("openingHoursSpecification"):
                            result["has_opening_hours"] = True

                    # Check review/aggregate rating schema
                    if "Review" in type_set or "AggregateRating" in type_set:
                        result["has_review_schema"] = True

                    # Also check for nested aggregateRating
                    if item.get("aggregateRating"):
                        result["has_review_schema"] = True

            except Exception:
                pass
    except Exception:
        pass
    return result


def analyze_page_local_seo(page: CrawledPage) -> Dict[str, Any]:
    """Analyze a single page for local SEO signals."""
    url = page.url
    html = page.html or ""

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {
            "url": url,
            "phone": "",
            "has_address": False,
            "has_google_maps": False,
            "is_contact_page": False,
            "location_keyword": "",
            "is_location_page": False,
        }

    page_text = soup.get_text(" ", strip=True)

    # Phone detection
    phone = _find_phone(page_text)

    # Address detection
    has_address = _has_address(page_text)

    # Google Maps embed
    has_google_maps = False
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if "google.com/maps" in src or "maps.googleapis.com" in src or "maps.google.com" in src:
            has_google_maps = True
            break

    # Contact page detection
    url_lower = url.lower()
    is_contact_page = False
    if "/contact" in url_lower or "/contact-us" in url_lower or "/get-in-touch" in url_lower:
        is_contact_page = True
    else:
        h1_tags = [h.get_text(strip=True).lower() for h in soup.find_all("h1")]
        if any("contact" in h for h in h1_tags):
            is_contact_page = True

    # Location page detection
    is_location_page = False
    location_keyword = ""
    for pattern in LOCATION_URL_PATTERNS:
        m = pattern.search(url)
        if m:
            is_location_page = True
            location_keyword = m.group(0).strip("/")
            break

    # Check title and H1 for location words
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
    title_h1_text = title + " " + " ".join(h1_tags)

    if LOCATION_WORDS_PATTERN.search(title_h1_text):
        is_location_page = True
        if not location_keyword:
            m = LOCATION_WORDS_PATTERN.search(title_h1_text)
            location_keyword = m.group(0) if m else ""

    return {
        "url": url,
        "phone": phone,
        "has_address": has_address,
        "has_google_maps": has_google_maps,
        "is_contact_page": is_contact_page,
        "location_keyword": location_keyword,
        "is_location_page": is_location_page,
    }


def enhance_with_gbp(local_seo: Dict[str, Any], biz_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-reference crawled local SEO signals with GBP data from Excel."""
    if not biz_data:
        return local_seo

    rating = biz_data.get("rating")
    reviews = biz_data.get("reviews") or 0
    gbp_phone = (biz_data.get("phone") or "").strip()
    competitors = biz_data.get("nearest_competitors") or []
    missing = list(local_seo.get("missing_local_signals", []))

    if rating is not None:
        local_seo["gbp_rating"] = rating
        if rating < 4.0:
            missing.append(f"GBP rating is {rating}★ — below 4.0 hurts local pack ranking")

    local_seo["gbp_reviews"] = reviews
    if reviews < 10:
        missing.append(f"Only {reviews} reviews — aim for 50+ to compete in local pack")

    if gbp_phone:
        site_phones = [p.get("phone", "") for p in local_seo.get("nap_pages", []) if p.get("phone")]
        gbp_digits = re.sub(r"\D", "", gbp_phone)[-7:]
        if site_phones:
            phone_match = any(gbp_digits in re.sub(r"\D", "", p) for p in site_phones)
            local_seo["nap_phone_consistent"] = phone_match
            if not phone_match:
                missing.append("Phone on website doesn't match GBP phone — NAP inconsistency hurts local SEO")
        elif not local_seo.get("has_nap_info"):
            missing.append("Phone not found on website — add GBP phone to every page footer")

    if competitors:
        comp_counts = [c.get("reviews") or 0 for c in competitors]
        top = max(comp_counts)
        gap = max(0, top - reviews)
        local_seo["review_gap"] = gap
        local_seo["top_competitor_reviews"] = top
        local_seo["months_to_close_gap"] = round(gap / 4) if gap > 0 else 0
        if gap > 20:
            missing.append(f"Review gap: nearest competitor has {top} reviews vs {reviews} — {gap} behind")

    local_seo["missing_local_signals"] = missing

    score = local_seo.get("score", 0)
    if rating is not None:
        if rating >= 4.5:
            score = min(100, score + 10)
        elif rating >= 4.0:
            score = min(100, score + 5)
        else:
            score = max(0, score - 10)
    if reviews >= 100:
        score = min(100, score + 10)
    elif reviews >= 50:
        score = min(100, score + 5)
    elif reviews < 10:
        score = max(0, score - 10)
    local_seo["score"] = round(score, 1)

    return local_seo


def analyze_local_seo(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze Local SEO signals across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    if not html_pages:
        return {
            "score": 0.0,
            "has_contact_page": False,
            "has_google_maps": False,
            "has_local_business_schema": False,
            "has_nap_info": False,
            "has_review_schema": False,
            "has_opening_hours": False,
            "location_optimized_pages": 0,
            "pages_with_phone": 0,
            "pages_with_address": 0,
            "missing_local_signals": ["No pages crawled"],
            "nap_pages": [],
            "location_pages": [],
            "summary": {
                "has_contact_page": False,
                "has_google_maps": False,
                "has_local_business_schema": False,
                "has_nap_info": False,
                "location_optimized_pages": 0,
                "missing_signals_count": 1,
            },
        }

    page_results = []
    has_contact_page = False
    has_google_maps = False
    has_local_business_schema = False
    has_review_schema = False
    has_opening_hours = False
    pages_with_phone = 0
    pages_with_address = 0
    location_optimized_pages = 0

    nap_pages = []
    location_pages = []

    for page in html_pages:
        result = analyze_page_local_seo(page)
        page_results.append(result)

        if result["is_contact_page"]:
            has_contact_page = True
        if result["has_google_maps"]:
            has_google_maps = True
        if result["phone"]:
            pages_with_phone += 1
        if result["has_address"]:
            pages_with_address += 1
        if result["is_location_page"]:
            location_optimized_pages += 1
            location_pages.append({
                "url": result["url"],
                "location_keyword": result["location_keyword"],
            })

        if result["phone"] or result["has_address"]:
            nap_pages.append({
                "url": result["url"],
                "phone": result["phone"],
                "has_address": result["has_address"],
            })

        # Check schema for this page
        schema_info = _check_local_business_schema(page.html)
        if schema_info["has_local_business_schema"]:
            has_local_business_schema = True
        if schema_info["has_review_schema"]:
            has_review_schema = True
        if schema_info["has_opening_hours"]:
            has_opening_hours = True

    has_nap_info = pages_with_phone > 0 or pages_with_address > 0

    # Build missing signals list
    missing_local_signals = []
    if not has_local_business_schema:
        missing_local_signals.append("No LocalBusiness schema markup")
    if not has_google_maps:
        missing_local_signals.append("No Google Maps embed")
    if not has_contact_page:
        missing_local_signals.append("No contact page detected")
    if not has_nap_info:
        missing_local_signals.append("No NAP (Name, Address, Phone) info found")
    if not has_review_schema:
        missing_local_signals.append("No Review or AggregateRating schema")
    if not has_opening_hours:
        missing_local_signals.append("No opening hours schema")
    if location_optimized_pages == 0:
        missing_local_signals.append("No location-optimized pages detected")

    # Score calculation
    score = 0.0
    if has_local_business_schema:
        score += 25
    if has_contact_page:
        score += 15
    if has_google_maps:
        score += 15
    if has_nap_info:
        score += 15
    if has_review_schema:
        score += 10
    if has_opening_hours:
        score += 10
    if location_optimized_pages > 0:
        score += min(10, location_optimized_pages * 2)

    score = round(min(100.0, score), 1)

    return {
        "score": score,
        "has_contact_page": has_contact_page,
        "has_google_maps": has_google_maps,
        "has_local_business_schema": has_local_business_schema,
        "has_nap_info": has_nap_info,
        "has_review_schema": has_review_schema,
        "has_opening_hours": has_opening_hours,
        "location_optimized_pages": location_optimized_pages,
        "pages_with_phone": pages_with_phone,
        "pages_with_address": pages_with_address,
        "missing_local_signals": missing_local_signals,
        "nap_pages": nap_pages[:30],
        "location_pages": location_pages[:30],
        "summary": {
            "has_contact_page": has_contact_page,
            "has_google_maps": has_google_maps,
            "has_local_business_schema": has_local_business_schema,
            "has_nap_info": has_nap_info,
            "location_optimized_pages": location_optimized_pages,
            "missing_signals_count": len(missing_local_signals),
        },
    }
