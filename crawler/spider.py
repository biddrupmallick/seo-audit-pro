import asyncio
import time
import re
from urllib.parse import urljoin, urlparse, urldefrag
from typing import List, Dict, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from config import (
    MAX_PAGES,
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}


@dataclass
class CrawledPage:
    url: str
    status_code: int = 0
    response_time: float = 0.0
    page_size: int = 0
    final_url: str = ""
    redirect_chain: List[str] = field(default_factory=list)
    content_type: str = ""
    html: str = ""
    error: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)


def normalize_url(url: str) -> str:
    """Remove fragment, normalize trailing slash behavior."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = parsed._replace(path=path, fragment="").geturl()
    return normalized


def is_internal_link(base_url: str, link: str) -> bool:
    """Check if a link is internal to the base domain (including subdomains)."""
    base_parsed = urlparse(base_url)
    link_parsed = urlparse(link)
    if not link_parsed.netloc:
        return True
    base_domain = base_parsed.netloc.lstrip("www.")
    link_domain = link_parsed.netloc.lstrip("www.")
    return link_domain == base_domain or link_domain.endswith("." + base_domain)


def extract_links(html: str, base_url: str) -> List[str]:
    """Extract all internal links from HTML."""
    try:
        soup = BeautifulSoup(html, "lxml")
        links = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            full_url = urljoin(base_url, href)
            full_url = normalize_url(full_url)
            if is_internal_link(base_url, full_url):
                parsed = urlparse(full_url)
                if parsed.scheme in ("http", "https"):
                    links.append(full_url)
        return links
    except Exception:
        return []


def parse_sitemap_xml(xml_text: str, base_url: str) -> tuple[List[str], List[str]]:
    """
    Parse a sitemap XML and return (page_urls, child_sitemap_urls).
    Handles both sitemapindex and urlset formats.
    """
    page_urls: List[str] = []
    child_sitemaps: List[str] = []
    try:
        root = ET.fromstring(xml_text)
        # Strip namespace for easy tag matching
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if tag == "sitemapindex":
            for sitemap in root:
                loc_tag = sitemap.tag.split("}")[-1] if "}" in sitemap.tag else sitemap.tag
                if loc_tag == "sitemap":
                    for child in sitemap:
                        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if child_tag == "loc" and child.text:
                            child_sitemaps.append(child.text.strip())
        elif tag == "urlset":
            for url_el in root:
                url_tag = url_el.tag.split("}")[-1] if "}" in url_el.tag else url_el.tag
                if url_tag == "url":
                    for child in url_el:
                        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if child_tag == "loc" and child.text:
                            page_url = child.text.strip()
                            if is_internal_link(base_url, page_url):
                                page_urls.append(page_url)
    except ET.ParseError:
        pass
    return page_urls, child_sitemaps


class Spider:
    def __init__(
        self,
        root_url: str,
        max_pages: int = MAX_PAGES,
        progress_callback: Optional[Callable] = None,
    ):
        self.root_url = normalize_url(root_url)
        self.base_url = root_url
        self.max_pages = max_pages
        self.progress_callback = progress_callback
        self.visited: Set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results: List[CrawledPage] = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def _discover_sitemap_urls(self, client: httpx.AsyncClient) -> List[str]:
        """
        Try to fetch sitemap.xml and sitemap_index.xml and return all discovered URLs.
        Recursively follows sitemap index files.
        """
        discovered: List[str] = []
        parsed = urlparse(self.root_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        sitemap_candidates = [
            f"{base}/sitemap_index.xml",
            f"{base}/sitemap.xml",
        ]

        # Also check robots.txt for sitemap directives
        try:
            r = await client.get(f"{base}/robots.txt", follow_redirects=True)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        if sm_url not in sitemap_candidates:
                            sitemap_candidates.insert(0, sm_url)
        except Exception:
            pass

        visited_sitemaps: Set[str] = set()
        pending_sitemaps = list(sitemap_candidates)

        while pending_sitemaps:
            sm_url = pending_sitemaps.pop(0)
            if sm_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sm_url)

            try:
                r = await client.get(sm_url, follow_redirects=True)
                if r.status_code != 200:
                    continue
                content_type = r.headers.get("content-type", "")
                text = r.text
                # Must look like XML
                if not text.strip().startswith("<"):
                    continue
                page_urls, child_sitemaps = parse_sitemap_xml(text, self.root_url)
                discovered.extend(page_urls)
                for child_sm in child_sitemaps:
                    if child_sm not in visited_sitemaps:
                        pending_sitemaps.append(child_sm)
            except Exception:
                continue

        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique: List[str] = []
        for u in discovered:
            norm = normalize_url(u)
            if norm not in seen:
                seen.add(norm)
                unique.append(norm)
        return unique

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> CrawledPage:
        """Fetch a single page and return CrawledPage."""
        page = CrawledPage(url=url)
        redirect_chain = []
        start_time = time.monotonic()

        try:
            response = await client.get(url, follow_redirects=True)
            elapsed = time.monotonic() - start_time

            for r in response.history:
                redirect_chain.append(str(r.url))

            page.status_code = response.status_code
            page.response_time = round(elapsed, 3)
            page.final_url = str(response.url)
            page.redirect_chain = redirect_chain
            page.content_type = response.headers.get("content-type", "")
            page.headers = dict(response.headers)

            if "text/html" in page.content_type:
                try:
                    page.html = response.text
                    page.page_size = len(response.content)
                except Exception as e:
                    page.error = f"Decode error: {e}"
                    page.page_size = len(response.content)
            else:
                page.page_size = int(response.headers.get("content-length", len(response.content)))

        except httpx.TimeoutException:
            page.error = "Timeout"
            page.status_code = 0
        except httpx.SSLError as e:
            page.error = f"SSL Error: {e}"
            page.status_code = 0
        except httpx.ConnectError as e:
            page.error = f"Connection Error: {e}"
            page.status_code = 0
        except Exception as e:
            page.error = str(e)
            page.status_code = 0

        return page

    async def worker(self, client: httpx.AsyncClient):
        """Worker coroutine that processes URLs from the queue."""
        while True:
            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                break

            try:
                if len(self.results) >= self.max_pages:
                    self.queue.task_done()
                    continue

                async with self.semaphore:
                    page = await self.fetch_page(client, url)

                self.results.append(page)

                if self.progress_callback:
                    await self.progress_callback(
                        len(self.results), self.max_pages, url
                    )

                # Extract and enqueue new links only for HTML 200 pages
                if page.html and page.status_code == 200:
                    links = extract_links(page.html, self.root_url)
                    for link in links:
                        norm = normalize_url(link)
                        if norm not in self.visited and len(self.results) < self.max_pages:
                            self.visited.add(norm)
                            await self.queue.put(norm)

            except Exception as e:
                error_page = CrawledPage(url=url, error=str(e))
                self.results.append(error_page)
            finally:
                self.queue.task_done()

    async def crawl(self) -> List[CrawledPage]:
        """Main crawl entry point. Seeds from sitemap first, then follows links."""
        limits = httpx.Limits(
            max_keepalive_connections=MAX_CONCURRENT_REQUESTS,
            max_connections=MAX_CONCURRENT_REQUESTS * 2,
        )
        timeout = httpx.Timeout(REQUEST_TIMEOUT)

        async with httpx.AsyncClient(
            headers=BROWSER_HEADERS,
            timeout=timeout,
            limits=limits,
            verify=False,
            follow_redirects=True,
        ) as client:
            # Phase 1: Discover URLs from sitemap
            sitemap_urls = await self._discover_sitemap_urls(client)

            # Seed queue: sitemap URLs first, then root URL
            seed_urls = [self.root_url] + [u for u in sitemap_urls if u != self.root_url]

            for url in seed_urls:
                norm = normalize_url(url)
                if norm not in self.visited:
                    self.visited.add(norm)
                    await self.queue.put(norm)

            # Phase 2: Crawl all queued URLs
            workers = [
                asyncio.create_task(self.worker(client))
                for _ in range(MAX_CONCURRENT_REQUESTS)
            ]
            await self.queue.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        return self.results
