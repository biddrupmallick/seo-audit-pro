import json
from pathlib import Path

BRANDING_FILE = Path(__file__).parent.parent / "branding.json"

DEFAULTS = {
    "agency_name": "Your Agency Name",
    "tagline": "SEO & Digital Growth Specialists",
    "email": "hello@youragency.com",
    "phone": "+1 (555) 000-0000",
    "website": "https://youragency.com",
    "logo_url": "",
    "accent_color": "#2563eb",
    "prepared_by": "Your Name",
    "footer_note": "This report is confidential and prepared exclusively for the recipient.",
}


def load_branding() -> dict:
    try:
        data = json.loads(BRANDING_FILE.read_text())
        return {**DEFAULTS, **data}
    except Exception:
        return DEFAULTS.copy()


def save_branding(data: dict):
    merged = {**DEFAULTS, **data}
    BRANDING_FILE.write_text(json.dumps(merged, indent=2))
    return merged
