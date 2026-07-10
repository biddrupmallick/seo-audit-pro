"""
Take mobile screenshot of a URL using Chrome headless.
"""
import base64
import os
import shutil
import subprocess
from typing import Dict, Any, Optional

from config import REPORTS_DIR

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _find_chrome() -> Optional[str]:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return shutil.which("google-chrome") or shutil.which("chromium")


CHROME_BIN = _find_chrome()


def _take_screenshot(url: str, out_path: str) -> bool:
    if not CHROME_BIN:
        return False
    try:
        result = subprocess.run([
            CHROME_BIN,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-notifications",
            "--disable-extensions",
            "--window-size=390,844",
            f"--screenshot={out_path}",
            "--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            url,
        ], capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(out_path)
    except Exception as e:
        print(f"Screenshot failed for {url}: {e}")
        return False


def _to_b64(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def capture_mobile_screenshots(client_url: str, competitor_url: Optional[str], job_id: str) -> Dict[str, Any]:
    """Capture client + optional competitor mobile screenshot. Returns base64 strings."""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    client_path = os.path.join(REPORTS_DIR, f"{job_id}_mob_client.png")
    client_b64 = None
    if _take_screenshot(client_url, client_path):
        client_b64 = _to_b64(client_path)

    comp_b64 = None
    if competitor_url:
        comp_path = os.path.join(REPORTS_DIR, f"{job_id}_mob_comp.png")
        if _take_screenshot(competitor_url, comp_path):
            comp_b64 = _to_b64(comp_path)

    return {
        "available": client_b64 is not None,
        "client": client_b64,
        "competitor": comp_b64,
        "client_url": client_url,
        "competitor_url": competitor_url or "",
    }
