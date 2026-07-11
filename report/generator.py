import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import REPORTS_DIR
from report.branding import load_branding

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _render_html(job_id: str, context: dict) -> str:
    """Render Jinja2 template and save to a temp HTML file. Returns the file path."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["enumerate"] = enumerate
    env.globals["len"] = len

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
            stylesheets=[CSS(string="@page { margin: 1cm; size: A4; }")],
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

    # Use business name from GBP data if available, else clean up domain
    _gbp_name = (gbp or {}).get("name", "") or (local_seo or {}).get("business_name", "")
    business_name = _gbp_name or domain.replace("www.", "").split(".")[0].replace("-", " ").replace("_", " ").title()

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
        "gbp":               gbp or {},
        "lead_score":        lead_score or {},
        "trust_signals":     trust_signals or {},
        "mobile_screenshots": mobile_screenshots or {},
        "competitor_gap":    competitor_gap or {},
        "roadmap":           roadmap or {},
        "meta_rewrites":     meta_rewrites or {},
        "branding":          load_branding(),
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
