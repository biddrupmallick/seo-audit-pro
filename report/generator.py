import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import REPORTS_DIR
from report.branding import load_branding, validate_branding, get_report_sections

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _pluralize(count, singular, plural=None):
    if plural is None:
        plural = singular + 's'
    return f"{count} {singular if count == 1 else plural}"


def _render_html(job_id: str, context: dict) -> str:
    """Render Jinja2 template and save to a temp HTML file. Returns the file path."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["enumerate"] = enumerate
    env.globals["len"] = len
    env.globals["pluralize"] = _pluralize

    template = env.get_template("report.html")
    html_content = template.render(**context)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    html_path = os.path.join(REPORTS_DIR, f"{job_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return html_path


def _html_to_pdf_weasyprint(html_path: str, pdf_path: str) -> bool:
    """Use WeasyPrint to convert HTML → PDF. No headers/footers added."""
    try:
        from weasyprint import HTML, CSS
        HTML(filename=html_path).write_pdf(
            pdf_path,
            stylesheets=[CSS(string="@page { margin: 1.5cm; size: A4; }")],
        )
        return os.path.exists(pdf_path)
    except Exception as e:
        print(f"WeasyPrint PDF failed: {e}")
        return False


def generate_report(
    job_id: str,
    root_url: str,
    total_pages: int,
    scores: Dict[str, Any],
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
    ai_recommendations: Dict[str, Any] = None,
    revenue_impact: Dict[str, Any] = None,
    wayback: Dict[str, Any] = None,
    competitors: List[Dict[str, Any]] = None,
    cold_emails: Dict[str, Any] = None,
    progress: Dict[str, Any] = None,
    keywords: Dict[str, Any] = None,
    gbp: Dict[str, Any] = None,
    lead_score: Dict[str, Any] = None,
    trust_signals: Dict[str, Any] = None,
    mobile_screenshots: Dict[str, Any] = None,
    competitor_gap: Dict[str, Any] = None,
    roadmap: Dict[str, Any] = None,
    meta_rewrites: Dict[str, Any] = None,
) -> str:
    """Generate a PDF report using Chrome headless. Falls back to HTML if Chrome unavailable."""
    try:
        parsed = urlparse(root_url)
        domain = parsed.netloc or root_url
    except Exception:
        domain = root_url

    branding = load_branding()
    ok, bad_field = validate_branding(branding)
    if not ok:
        print(f"WARNING: Branding field '{bad_field}' is missing or placeholder. Fill in /settings before sharing reports.")

    # Normalize GBP nested structure → flat dict for template use
    _gbp_raw = gbp or {}
    _gbp_client = _gbp_raw.get('client') or {}
    _gbp_intel = _gbp_raw.get('review_intel') or {}
    _gbp_insights = _gbp_intel.get('insights') or {}
    gbp_flat = {
        'name':          _gbp_client.get('name', '') or _gbp_raw.get('name', ''),
        'rating':        _gbp_client.get('rating') or _gbp_raw.get('rating'),
        'reviews':       _gbp_client.get('review_count') or _gbp_raw.get('reviews') or _gbp_intel.get('count', 0),
        'profile_score': _gbp_client.get('score') or _gbp_raw.get('profile_score', 0) or 0,
        'review_gap':    _gbp_intel.get('review_gap', 0),
        'top_praise':    _gbp_insights.get('PRAISE_THEMES', '') or _gbp_insights.get('TOP_PRAISE', ''),
        'top_complaints':_gbp_insights.get('COMPLAINT_THEMES', '') or _gbp_insights.get('TOP_COMPLAINTS', ''),
        'key_insight':   _gbp_insights.get('TOP_ACTION', '') or _gbp_insights.get('KEY_INSIGHT', ''),
        'available':     _gbp_raw.get('available', False),
        'competitors':   [
            {
                'name':          c.get('name', ''),
                'rating':        c.get('rating'),
                'reviews':       c.get('reviews') or c.get('review_count'),
                'distance_miles':c.get('distance_miles'),
                'website':       c.get('website', ''),
                'praise':        c.get('praise', ''),
                'complaint':     c.get('complaint', ''),
            }
            for c in (_gbp_raw.get('competitors') or [])
        ],
    }

    # Use business name from GBP data if available, else clean up domain
    _gbp_name = gbp_flat.get("name", "") or (local_seo or {}).get("business_name", "")
    business_name = _gbp_name or domain.replace("www.", "").split(".")[0].replace("-", " ").replace("_", " ").title()

    crawl_failed = bool((scores or {}).get('crawl_failed', False) or total_pages < 2)
    _items = (revenue_impact or {}).get('items', [])
    revenue_low = sum(item.get('monthly_impact_low', item.get('monthly_low', 0)) for item in _items)
    revenue_high = sum(item.get('monthly_impact_high', item.get('monthly_high', 0)) for item in _items)

    gbp_score = gbp_flat.get('profile_score', 0) or 0
    gbp_reviews = gbp_flat.get('reviews', 0) or 0
    overall_score = (scores or {}).get('overall_score', 0) or 0
    if gbp_score >= 80 and gbp_reviews >= 100 and (crawl_failed or overall_score < 50):
        narrative = 'strong_gbp_weak_site'
    elif gbp_score >= 80 and gbp_reviews >= 100:
        narrative = 'strong_all'
    elif gbp_reviews < 20 or gbp_score < 40:
        narrative = 'weak_gbp'
    else:
        narrative = 'average'

    context = {
        "domain": domain,
        "root_url": root_url,
        "business_name": business_name,
        "report_date": datetime.now().strftime("%B %d, %Y"),
        "total_pages": total_pages,
        "scores": scores,
        "technical": technical,
        "onpage": onpage,
        "schema": schema,
        "aeo": aeo,
        "geo": geo,
        "performance": performance,
        "images": images,
        "local_seo": local_seo or {},
        "conversion": conversion or {},
        "content": content or {},
        "ai": ai_recommendations or {},
        "revenue_impact": revenue_impact or {},
        "wayback":      wayback or {},
        "competitors":  competitors or [],
        "cold_emails":  cold_emails or {},
        "progress":     progress or {},
        "keywords":     keywords or {},
        "gbp":               gbp_flat,
        "lead_score":        lead_score or {},
        "trust_signals":     trust_signals or {},
        "mobile_screenshots": mobile_screenshots or {},
        "competitor_gap":    competitor_gap or {},
        "roadmap":           roadmap or {},
        "meta_rewrites":     meta_rewrites or {},
        "branding":          branding,
        "report_sections":   get_report_sections(branding),
        "crawl_failed":      crawl_failed,
        "revenue_low":       revenue_low,
        "revenue_high":      revenue_high,
        "narrative":         narrative,
    }

    html_path = _render_html(job_id, context)
    pdf_path = os.path.join(REPORTS_DIR, f"{job_id}.pdf")
    if _html_to_pdf_weasyprint(html_path, pdf_path):
        return pdf_path
    print("WeasyPrint PDF failed, returning HTML.")
    return html_path


def get_report_path(job_id: str) -> str | None:
    """Find the report file for a given job_id (PDF preferred over HTML)."""
    pdf_path = os.path.join(REPORTS_DIR, f"{job_id}.pdf")
    html_path = os.path.join(REPORTS_DIR, f"{job_id}.html")
    if os.path.exists(pdf_path):
        return pdf_path
    if os.path.exists(html_path):
        return html_path
    return None


def generate_niche_report(
    job_id: str,
    business_name: str,
    owner_name: str,
    rating,
    review_count,
    reviews_text: str,
    website: str,
    phone: str,
    email: str,
    address: str,
    socials: Dict[str, str],
    competitors: List[Dict],
    load_speed: str = None,
    mobile_friendly: bool = None,
) -> str:
    """Generate an 8-page business-owner-friendly PDF using niche_report.html."""
    from analyzers.report_writer import calculate_presence_score, generate_report_content

    branding = load_branding()

    # Parse praise/complaints from reviews_text using simple heuristics
    top_praise = ""
    top_complaints = ""
    if reviews_text:
        import re
        praise_match = re.search(r'(?:praise|positive|customers love)[:\s]+([^\n.]{10,120})', reviews_text, re.I)
        complaint_match = re.search(r'(?:complaint|negative|issue)[:\s]+([^\n.]{10,120})', reviews_text, re.I)
        if praise_match:
            top_praise = praise_match.group(1).strip()
        if complaint_match:
            top_complaints = complaint_match.group(1).strip()
        if not top_praise and reviews_text:
            top_praise = reviews_text[:200].strip()

    presence_score = calculate_presence_score(
        website=website,
        rating=rating,
        review_count=review_count,
        email=email,
        phone=phone,
        socials=socials,
    )

    written = generate_report_content(
        business_name=business_name,
        owner_name=owner_name,
        rating=rating,
        review_count=review_count,
        reviews_text=reviews_text,
        top_praise=top_praise,
        top_complaints=top_complaints,
        website=website,
        phone=phone,
        email=email,
        address=address,
        socials=socials,
        competitors=competitors,
        presence_score=presence_score,
        load_speed=load_speed,
        mobile_friendly=mobile_friendly,
    )

    context = {
        "business_name":   business_name,
        "owner_name":      owner_name or "",
        "rating":          rating,
        "review_count":    review_count,
        "reviews_text":    reviews_text,
        "top_praise":      top_praise,
        "top_complaints":  top_complaints,
        "website":         website,
        "phone":           phone,
        "email":           email,
        "address":         address,
        "socials":         socials,
        "competitors":     competitors,
        "presence_score":  presence_score,
        "load_speed":      load_speed,
        "mobile_friendly": mobile_friendly,
        "content":         written,
        "branding":        branding,
        "report_date":     datetime.now().strftime("%B %d, %Y"),
    }

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["enumerate"] = enumerate
    env.globals["len"] = len

    template = env.get_template("niche_report.html")
    html_content = template.render(**context)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    html_path = os.path.join(REPORTS_DIR, f"{job_id}_niche.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    pdf_path = os.path.join(REPORTS_DIR, f"{job_id}_niche.pdf")
    if _html_to_pdf_weasyprint(html_path, pdf_path):
        return pdf_path
    return html_path
