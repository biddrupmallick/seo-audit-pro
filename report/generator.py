import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import REPORTS_DIR

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Locate Chrome/Chromium binary
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

def _find_chrome() -> str | None:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")

CHROME_BIN = _find_chrome()


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


def _html_to_pdf_chrome(html_path: str, pdf_path: str) -> bool:
    """Use Chrome headless to print HTML → PDF. Returns True on success."""
    if not CHROME_BIN:
        return False
    try:
        result = subprocess.run(
            [
                CHROME_BIN,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--run-all-compositor-stages-before-draw",
                "--print-to-pdf-no-header",
                f"--print-to-pdf={pdf_path}",
                f"file://{html_path}",
            ],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0 and os.path.exists(pdf_path)
    except Exception as e:
        print(f"Chrome PDF generation failed: {e}")
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
) -> str:
    """Generate a PDF report using Chrome headless. Falls back to HTML if Chrome unavailable."""
    try:
        parsed = urlparse(root_url)
        domain = parsed.netloc or root_url
    except Exception:
        domain = root_url

    context = {
        "domain": domain,
        "root_url": root_url,
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
    }

    html_path = _render_html(job_id, context)
    abs_html_path = str(Path(html_path).resolve())

    if CHROME_BIN:
        pdf_path = os.path.join(REPORTS_DIR, f"{job_id}.pdf")
        if _html_to_pdf_chrome(abs_html_path, pdf_path):
            return pdf_path
        print("Chrome PDF failed, falling back to HTML.")

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
