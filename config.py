import os

# Ollama host — set OLLAMA_HOST env var to point to Colab/remote instance
# Example: export OLLAMA_HOST=https://xxxx.ngrok-free.app
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

MAX_PAGES = 200
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; SEOAuditBot/1.0)"
REPORTS_DIR = "reports"

# Scoring weights (must sum to 1.0)
SCORING_WEIGHTS = {
    "technical": 0.20,
    "onpage": 0.15,
    "schema": 0.10,
    "aeo": 0.10,
    "geo": 0.10,
    "performance": 0.08,
    "local_seo": 0.12,
    "conversion": 0.10,
    "content": 0.05,
}

# Thresholds
SLOW_PAGE_THRESHOLD = 3.0  # seconds
LARGE_PAGE_THRESHOLD = 1_048_576  # 1MB in bytes
LARGE_IMAGE_THRESHOLD = 512_000  # 500KB in bytes
TITLE_MIN_LENGTH = 10
TITLE_MAX_LENGTH = 60
META_DESC_MAX_LENGTH = 160
REDIRECT_CHAIN_THRESHOLD = 3

os.makedirs(REPORTS_DIR, exist_ok=True)
