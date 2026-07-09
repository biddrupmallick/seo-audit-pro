from typing import Dict, Any
from config import SCORING_WEIGHTS


def get_grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def get_grade_color(grade: str) -> str:
    """Return CSS color for a grade."""
    colors = {
        "A": "#22c55e",
        "B": "#84cc16",
        "C": "#eab308",
        "D": "#f97316",
        "F": "#ef4444",
    }
    return colors.get(grade, "#6b7280")


def calculate_scores(
    technical: Dict[str, Any],
    onpage: Dict[str, Any],
    schema: Dict[str, Any],
    aeo: Dict[str, Any],
    geo: Dict[str, Any],
    performance: Dict[str, Any],
    images: Dict[str, Any],
    local_seo: Dict[str, Any] = None,
    conversion: Dict[str, Any] = None,
    content: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Calculate weighted overall score and category scores."""

    if local_seo is None:
        local_seo = {}
    if conversion is None:
        conversion = {}
    if content is None:
        content = {}

    category_scores = {
        "technical": technical.get("score", 0),
        "onpage": onpage.get("score", 0),
        "schema": schema.get("score", 0),
        "aeo": aeo.get("score", 0),
        "geo": geo.get("score", 0),
        "performance": performance.get("score", 0),
        "local_seo": local_seo.get("score", 0),
        "conversion": conversion.get("score", 0),
        "content": content.get("score", 0),
    }

    # Image score influences onpage slightly
    image_score = images.get("score", 100)
    category_scores["onpage"] = round(
        category_scores["onpage"] * 0.8 + image_score * 0.2, 1
    )

    # Weighted overall score
    overall = sum(
        category_scores[cat] * weight
        for cat, weight in SCORING_WEIGHTS.items()
    )
    overall = round(overall, 1)
    overall = max(0.0, min(100.0, overall))

    grade = get_grade(overall)

    # Generate critical issues list
    critical_issues = []

    tech_summary = technical.get("summary", {})
    if tech_summary.get("broken_pages", 0) > 0:
        critical_issues.append({
            "category": "Technical",
            "issue": f"{tech_summary['broken_pages']} broken page(s) (4xx errors)",
            "severity": "critical",
            "impact": "high",
        })
    if tech_summary.get("server_errors", 0) > 0:
        critical_issues.append({
            "category": "Technical",
            "issue": f"{tech_summary['server_errors']} server error(s) (5xx)",
            "severity": "critical",
            "impact": "high",
        })
    if tech_summary.get("slow_pages", 0) > 0:
        critical_issues.append({
            "category": "Performance",
            "issue": f"{tech_summary['slow_pages']} slow page(s) (>3s response)",
            "severity": "warning",
            "impact": "medium",
        })

    onpage_summary = onpage.get("summary", {})
    if onpage_summary.get("missing_title", 0) > 0:
        critical_issues.append({
            "category": "On-Page SEO",
            "issue": f"{onpage_summary['missing_title']} page(s) missing title tags",
            "severity": "critical",
            "impact": "high",
        })
    if onpage_summary.get("missing_h1", 0) > 0:
        critical_issues.append({
            "category": "On-Page SEO",
            "issue": f"{onpage_summary['missing_h1']} page(s) missing H1 headings",
            "severity": "critical",
            "impact": "high",
        })
    if onpage_summary.get("missing_meta_description", 0) > 0:
        critical_issues.append({
            "category": "On-Page SEO",
            "issue": f"{onpage_summary['missing_meta_description']} page(s) missing meta descriptions",
            "severity": "warning",
            "impact": "medium",
        })
    if onpage_summary.get("duplicate_titles", 0) > 0:
        critical_issues.append({
            "category": "On-Page SEO",
            "issue": f"{onpage_summary['duplicate_titles']} duplicate title tag group(s)",
            "severity": "warning",
            "impact": "medium",
        })

    schema_summary = schema.get("summary", {})
    if schema_summary.get("schema_coverage_percent", 100) < 50:
        critical_issues.append({
            "category": "Schema",
            "issue": f"Only {schema_summary.get('schema_coverage_percent', 0)}% of pages have schema markup",
            "severity": "warning",
            "impact": "medium",
        })

    image_summary = images.get("summary", {})
    if image_summary.get("missing_alt", 0) > 0:
        critical_issues.append({
            "category": "Images",
            "issue": f"{image_summary['missing_alt']} image(s) missing alt text",
            "severity": "warning",
            "impact": "medium",
        })

    local_seo_summary = local_seo.get("summary", {})
    if not local_seo_summary.get("has_local_business_schema", True):
        critical_issues.append({
            "category": "Local SEO",
            "issue": "No LocalBusiness schema markup detected",
            "severity": "warning",
            "impact": "medium",
        })
    if not local_seo_summary.get("has_contact_page", True):
        critical_issues.append({
            "category": "Local SEO",
            "issue": "No contact page detected",
            "severity": "warning",
            "impact": "medium",
        })

    conversion_summary = conversion.get("summary", {})
    if conversion_summary.get("pages_with_cta", 1) == 0:
        critical_issues.append({
            "category": "Conversion",
            "issue": "No pages have detectable CTA (call-to-action) elements",
            "severity": "warning",
            "impact": "high",
        })

    content_summary = content.get("summary", {})
    thin_pages = content_summary.get("thin_content_pages", 0)
    if thin_pages > 0:
        critical_issues.append({
            "category": "Content",
            "issue": f"{thin_pages} page(s) have thin content (fewer than 300 words)",
            "severity": "warning",
            "impact": "medium",
        })

    # Sort by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    critical_issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    # Quick wins (easiest fixes with high impact)
    quick_wins = []

    if onpage_summary.get("missing_meta_description", 0) > 0:
        quick_wins.append({
            "action": f"Add meta descriptions to {onpage_summary['missing_meta_description']} page(s)",
            "effort": "low",
            "impact": "high",
            "category": "On-Page SEO",
        })
    if image_summary.get("missing_alt", 0) > 0:
        quick_wins.append({
            "action": f"Add alt text to {image_summary['missing_alt']} image(s)",
            "effort": "low",
            "impact": "medium",
            "category": "Images",
        })
    if onpage_summary.get("title_too_long", 0) > 0:
        quick_wins.append({
            "action": f"Shorten {onpage_summary['title_too_long']} title(s) to under 60 characters",
            "effort": "low",
            "impact": "medium",
            "category": "On-Page SEO",
        })
    if schema_summary.get("pages_without_schema", 0) > 0:
        quick_wins.append({
            "action": f"Add schema markup to {schema_summary['pages_without_schema']} page(s)",
            "effort": "medium",
            "impact": "high",
            "category": "Schema",
        })
    if tech_summary.get("http_only_pages", 0) > 0:
        quick_wins.append({
            "action": f"Redirect {tech_summary['http_only_pages']} HTTP page(s) to HTTPS",
            "effort": "low",
            "impact": "high",
            "category": "Technical",
        })
    if not local_seo_summary.get("has_local_business_schema", True):
        quick_wins.append({
            "action": "Add LocalBusiness JSON-LD schema with name, address, telephone and url",
            "effort": "low",
            "impact": "high",
            "category": "Local SEO",
        })
    if conversion_summary.get("pages_with_cta", 1) == 0:
        quick_wins.append({
            "action": "Add clear call-to-action buttons to key landing pages",
            "effort": "low",
            "impact": "high",
            "category": "Conversion",
        })
    if thin_pages > 0:
        quick_wins.append({
            "action": f"Expand {thin_pages} thin content page(s) to at least 300 words",
            "effort": "medium",
            "impact": "medium",
            "category": "Content",
        })

    return {
        "overall_score": overall,
        "grade": grade,
        "grade_color": get_grade_color(grade),
        "category_scores": {
            cat: {
                "score": score,
                "grade": get_grade(score),
                "grade_color": get_grade_color(get_grade(score)),
                "weight": SCORING_WEIGHTS.get(cat, 0),
            }
            for cat, score in category_scores.items()
        },
        "critical_issues": critical_issues[:10],
        "quick_wins": quick_wins[:5],
    }
