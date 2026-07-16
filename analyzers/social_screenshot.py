"""
Extract email from social media pages via screenshot + moondream vision model.
Fallback order: Facebook → Instagram → Yelp.

Uses Chrome headless (same as mobile_screenshot.py) to take the screenshot,
then sends it to moondream running in Ollama for email extraction.
"""
import base64
import os
import re
import subprocess
import tempfile
from typing import Dict, Tuple

from analyzers.ollama_client import _client

VISION_MODEL = "moondream"

_PROMPT = (
    "Look at this screenshot of a business page. "
    "Find any email address visible anywhere on the page — in the About section, "
    "contact info, bio, or anywhere else. "
    "Reply with ONLY the email address if you find one. "
    "If no email is visible, reply with exactly: none"
)

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Chrome binary locations (same list as mobile_screenshot.py)
_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _find_chrome():
    import shutil
    for path in _CHROME_PATHS:
        if os.path.exists(path):
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


_CHROME = _find_chrome()


def _take_screenshot(url: str) -> bytes:
    """Load URL in Chrome headless and return PNG bytes, or empty bytes on failure."""
    if not _CHROME:
        return b""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = subprocess.run([
            _CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-notifications",
            "--disable-extensions",
            "--window-size=1280,900",
            f"--screenshot={tmp_path}",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            url,
        ], capture_output=True, timeout=25)

        if result.returncode == 0 and os.path.exists(tmp_path):
            with open(tmp_path, "rb") as f:
                return f.read()
    except Exception as e:
        print(f"[social_screenshot] Chrome failed for {url}: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return b""


def _extract_email_via_moondream(image_bytes: bytes) -> str:
    """Send screenshot to moondream and return extracted email or empty string."""
    if not image_bytes:
        return ""
    try:
        img_b64 = base64.b64encode(image_bytes).decode()
        response = _client.generate(
            model=VISION_MODEL,
            prompt=_PROMPT,
            images=[img_b64],
            options={"num_predict": 60, "temperature": 0},
        )
        raw = response["response"].strip().lower()
        if raw == "none" or "@" not in raw:
            return ""
        match = _EMAIL_RE.search(raw)
        return match.group(0) if match else ""
    except Exception as e:
        print(f"[social_screenshot] moondream error: {e}")
        return ""


def find_email_from_socials(socials: Dict[str, str]) -> Tuple[str, str]:
    """
    Try Facebook → Instagram → Yelp to find an email via screenshot + moondream.

    Args:
        socials: dict with keys like 'facebook', 'instagram', 'yelp' → profile URLs

    Returns:
        (email, platform) — both empty strings if nothing found
    """
    for platform in ["facebook", "instagram", "yelp"]:
        url = socials.get(platform, "").strip()
        if not url:
            continue

        print(f"[social_screenshot] Trying {platform}: {url}")
        image_bytes = _take_screenshot(url)
        if not image_bytes:
            print(f"[social_screenshot] No screenshot for {platform}")
            continue

        email = _extract_email_via_moondream(image_bytes)
        if email:
            print(f"[social_screenshot] Found email on {platform}: {email}")
            return email, platform

        print(f"[social_screenshot] No email found on {platform}")

    return "", ""
