# SEO Audit Pro

A powerful, unlimited website SEO auditing tool — better than Screaming Frog's free tier with no 500-page limit.

## Features

- **No URL limit** — crawls up to 200 pages by default (configurable)
- **Sitemap discovery** — automatically reads sitemap.xml to find all pages
- **Technical SEO** — broken links, redirects, SSL, slow pages
- **On-Page SEO** — titles, meta descriptions, H1/H2 headings, canonicals
- **Schema Markup** — JSON-LD detection, missing schema types, validation
- **AEO (Answer Engine Optimization)** — FAQ sections, question headings, featured snippet signals
- **GEO (Generative Engine Optimization)** — E-E-A-T signals, AI readiness, brand consistency
- **Performance** — response times, page sizes, resource analysis
- **Image Analysis** — missing alt text, broken images
- **PDF/HTML Reports** — professional, client-ready reports with health scores
- **Live progress** — real-time crawl updates via WebSocket

## Tech Stack

- **Backend:** FastAPI + Python 3.11+
- **Crawler:** httpx (async) + BeautifulSoup4
- **Reports:** WeasyPrint + Jinja2
- **Frontend:** Vanilla HTML/CSS with WebSocket

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Open in browser
open http://localhost:8000
```

## Usage

1. Open `http://localhost:8000`
2. Paste any website URL
3. Click **Analyze Now**
4. Watch live progress as it crawls
5. Download the PDF report

## Configuration

Edit `config.py` to adjust:

```python
MAX_PAGES = 200              # Max pages to crawl
MAX_CONCURRENT_REQUESTS = 10 # Concurrent requests
REQUEST_TIMEOUT = 30         # Seconds per request
SLOW_PAGE_THRESHOLD = 3.0    # Seconds (flags slow pages)
LARGE_PAGE_THRESHOLD = 1MB   # Flags large pages
```

## Report Sections

1. Cover page with overall health score (0–100) and grade (A–F)
2. Executive Summary with top critical issues
3. Technical SEO
4. On-Page SEO
5. Schema Markup Analysis
6. AEO Readiness
7. GEO / AI Readiness
8. Performance Metrics
9. Image Analysis
10. Quick Wins
11. Prioritized Recommendations

## License

MIT
