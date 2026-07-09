import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import REPORTS_DIR

# Try to import WeasyPrint - it's optional due to system dependencies
WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML as WeasyHTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError, Exception):
    print("WARNING: WeasyPrint not available (system library missing). PDF generation will fallback to HTML.")


TEMPLATE_DIR = Path(__file__).parent / "templates"


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
) -> str:
    """
    Generate a PDF (or HTML fallback) report.
    Returns the path to the generated file.
    """
    # Parse domain from URL
    try:
        parsed = urlparse(root_url)
        domain = parsed.netloc or root_url
    except Exception:
        domain = root_url

    report_date = datetime.now().strftime("%B %d, %Y")

    # Set up Jinja2
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    # Add enumerate to Jinja2 globals
    env.globals["enumerate"] = enumerate
    env.globals["len"] = len

    template = env.get_template("report.html")

    # Sanitize data for template - convert any non-serializable values
    context = {
        "domain": domain,
        "root_url": root_url,
        "report_date": report_date,
        "total_pages": total_pages,
        "scores": scores,
        "technical": technical,
        "onpage": onpage,
        "schema": schema,
        "aeo": aeo,
        "geo": geo,
        "performance": performance,
        "images": images,
    }

    html_content = template.render(**context)

    os.makedirs(REPORTS_DIR, exist_ok=True)

    if WEASYPRINT_AVAILABLE:
        pdf_path = os.path.join(REPORTS_DIR, f"{job_id}.pdf")
        try:
            weasy = WeasyHTML(string=html_content, base_url=str(TEMPLATE_DIR))
            weasy.write_pdf(pdf_path)
            return pdf_path
        except Exception as e:
            print(f"WeasyPrint PDF generation failed: {e}. Falling back to HTML.")
            # Fall through to HTML generation

    # HTML fallback
    html_path = os.path.join(REPORTS_DIR, f"{job_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return html_path


def get_report_path(job_id: str) -> str | None:
    """Find the report file for a given job_id (PDF or HTML)."""
    pdf_path = os.path.join(REPORTS_DIR, f"{job_id}.pdf")
    html_path = os.path.join(REPORTS_DIR, f"{job_id}.html")
    if os.path.exists(pdf_path):
        return pdf_path
    if os.path.exists(html_path):
        return html_path
    return None
