import json
import re
from typing import List, Dict, Any, Set
from bs4 import BeautifulSoup
from crawler.spider import CrawledPage


KNOWN_SCHEMA_TYPES = {
    "Organization",
    "LocalBusiness",
    "Product",
    "FAQPage",
    "Article",
    "NewsArticle",
    "BlogPosting",
    "BreadcrumbList",
    "Review",
    "AggregateRating",
    "HowTo",
    "VideoObject",
    "Event",
    "Person",
    "WebPage",
    "WebSite",
    "SiteNavigationElement",
    "SearchAction",
    "ContactPage",
    "AboutPage",
}

# Required fields for common schema types
REQUIRED_FIELDS = {
    "Organization": ["name"],
    "LocalBusiness": ["name", "address"],
    "Product": ["name"],
    "FAQPage": ["mainEntity"],
    "Article": ["headline", "author"],
    "NewsArticle": ["headline", "author"],
    "BreadcrumbList": ["itemListElement"],
    "HowTo": ["name", "step"],
    "VideoObject": ["name", "description", "thumbnailUrl", "uploadDate"],
    "Event": ["name", "startDate", "location"],
    "Review": ["itemReviewed", "reviewRating"],
    "AggregateRating": ["ratingValue", "reviewCount"],
}


def extract_schema_from_html(html: str) -> List[Dict[str, Any]]:
    """Extract all JSON-LD structured data from a page."""
    schemas = []
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or script.get_text()
                if not raw or not raw.strip():
                    continue
                data = json.loads(raw.strip())
                if isinstance(data, list):
                    schemas.extend(data)
                elif isinstance(data, dict):
                    # Handle @graph
                    if "@graph" in data:
                        schemas.extend(data["@graph"])
                    else:
                        schemas.append(data)
            except (json.JSONDecodeError, Exception):
                pass
    except Exception:
        pass
    return schemas


def get_schema_types(schemas: List[Dict]) -> List[str]:
    """Extract @type values from schema objects."""
    types = []
    for schema in schemas:
        st = schema.get("@type", "")
        if isinstance(st, list):
            types.extend(st)
        elif isinstance(st, str):
            types.append(st)
    return types


def check_schema_errors(schema: Dict) -> List[str]:
    """Check for missing required fields in a schema object."""
    errors = []
    schema_type = schema.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else ""

    if schema_type in REQUIRED_FIELDS:
        for field in REQUIRED_FIELDS[schema_type]:
            if field not in schema:
                errors.append(f"Missing required field '{field}' in {schema_type}")
    return errors


def analyze_schema(pages: List[CrawledPage]) -> Dict[str, Any]:
    """Analyze schema markup across all pages."""
    html_pages = [p for p in pages if p.html and 200 <= p.status_code < 300]

    pages_with_schema = []
    pages_without_schema = []
    all_schema_types: Set[str] = set()
    schema_errors = []
    page_schema_data = []

    for page in html_pages:
        schemas = extract_schema_from_html(page.html)
        types = get_schema_types(schemas)
        errors = []
        for s in schemas:
            errors.extend(check_schema_errors(s))

        entry = {
            "url": page.url,
            "schema_count": len(schemas),
            "schema_types": list(set(types)),
            "errors": errors,
            "schemas": schemas[:5],  # Store up to 5 schemas per page to save memory
        }
        page_schema_data.append(entry)

        if schemas:
            pages_with_schema.append(entry)
            all_schema_types.update(types)
        else:
            pages_without_schema.append({"url": page.url})

        if errors:
            schema_errors.append({
                "url": page.url,
                "errors": errors,
            })

    # Determine which schema types are missing site-wide
    missing_schema_types = list(KNOWN_SCHEMA_TYPES - all_schema_types)

    total = len(html_pages)
    schema_coverage = (len(pages_with_schema) / total * 100) if total > 0 else 0

    # Score
    score = 100.0
    if total > 0:
        # Deduct for pages without schema
        score -= (len(pages_without_schema) / total) * 40
        # Deduct for schema errors
        score -= min(30, len(schema_errors) * 5)
        # Bonus for schema variety (up to 10 points)
        variety_bonus = min(10, len(all_schema_types) * 1.5)
        score = min(100.0, score + variety_bonus)
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score, 1),
        "total_pages": total,
        "pages_with_schema": len(pages_with_schema),
        "pages_without_schema": pages_without_schema,
        "schema_coverage_percent": round(schema_coverage, 1),
        "all_schema_types_found": sorted(list(all_schema_types)),
        "missing_schema_types": sorted(missing_schema_types),
        "schema_errors": schema_errors,
        "page_schema_data": page_schema_data,
        "summary": {
            "pages_with_schema": len(pages_with_schema),
            "pages_without_schema": len(pages_without_schema),
            "schema_types_count": len(all_schema_types),
            "schema_errors": len(schema_errors),
            "schema_coverage_percent": round(schema_coverage, 1),
        },
    }
