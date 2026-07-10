import asyncio
import json
import os
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel, HttpUrl

from config import REPORTS_DIR
from crawler.spider import Spider
from analyzers.technical import analyze_technical
from analyzers.onpage import analyze_onpage
from analyzers.schema import analyze_schema
from analyzers.aeo import analyze_aeo
from analyzers.geo import analyze_geo
from analyzers.performance import analyze_performance
from analyzers.images import analyze_images
from analyzers.local_seo import analyze_local_seo
from analyzers.conversion import analyze_conversion
from analyzers.content import analyze_content
from analyzers.ai_recommendations import generate_ai_recommendations
from analyzers.revenue_impact import calculate_revenue_impact
from analyzers.wayback import analyze_wayback
from scoring.scorer import calculate_scores
from report.generator import generate_report, get_report_path

# ====== APP SETUP ======
app = FastAPI(
    title="SEO Audit Pro",
    description="Unlimited local SEO crawler and audit tool",
    version="1.0.0",
)

BASE_DIR = Path(__file__).parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ====== IN-MEMORY JOB STORE ======
# Structure: {job_id: {"status": str, "data": dict, "progress": int, "message": str, "ws": WebSocket}}
jobs: Dict[str, Dict[str, Any]] = {}
# WebSocket connections per job
ws_connections: Dict[str, WebSocket] = {}


# ====== MODELS ======
class AnalyzeRequest(BaseModel):
    url: str


# ====== ROUTES ======
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze")
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Start a new SEO analysis job."""
    url = request.url.strip()

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "url": url,
        "created_at": datetime.now().isoformat(),
        "progress": 0,
        "message": "Queued",
        "data": None,
        "error": None,
    }

    background_tasks.add_task(run_analysis, job_id, url)

    return {"job_id": job_id, "status": "started"}


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for live progress updates."""
    await websocket.accept()
    ws_connections[job_id] = websocket

    try:
        # If job already done, send result immediately
        if job_id in jobs:
            job = jobs[job_id]
            if job["status"] == "complete":
                await websocket.send_json({
                    "type": "complete",
                    "data": job["data"],
                })
                return
            elif job["status"] == "error":
                await websocket.send_json({
                    "type": "error",
                    "message": job.get("error", "Unknown error"),
                })
                return

        # Keep connection alive while job runs
        while True:
            try:
                # Check for messages from client (keepalive)
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            # Check job status
            if job_id not in jobs:
                await websocket.send_json({"type": "error", "message": "Job not found"})
                break

            job = jobs[job_id]
            if job["status"] == "complete":
                await websocket.send_json({
                    "type": "complete",
                    "data": job["data"],
                })
                break
            elif job["status"] == "error":
                await websocket.send_json({
                    "type": "error",
                    "message": job.get("error", "Unknown error"),
                })
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        ws_connections.pop(job_id, None)


@app.get("/report/{job_id}")
async def download_report(job_id: str):
    """Download the generated report (PDF or HTML)."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not complete yet")

    report_path = get_report_path(job_id)
    if not report_path:
        raise HTTPException(status_code=404, detail="Report file not found")

    if report_path.endswith(".pdf"):
        return FileResponse(
            report_path,
            media_type="application/pdf",
            filename=f"seo-audit-{job_id[:8]}.pdf",
        )
    else:
        return FileResponse(
            report_path,
            media_type="text/html",
            filename=f"seo-audit-{job_id[:8]}.html",
        )


@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the current status of a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id].copy()
    # Don't return full data in status check
    job.pop("data", None)
    return job


# ====== BACKGROUND ANALYSIS TASK ======
async def send_progress(job_id: str, percent: int, message: str):
    """Send a progress update via WebSocket."""
    jobs[job_id]["progress"] = percent
    jobs[job_id]["message"] = message

    if job_id in ws_connections:
        try:
            await ws_connections[job_id].send_json({
                "type": "progress",
                "percent": percent,
                "message": message,
            })
        except Exception:
            # WebSocket may have closed
            pass


async def run_analysis(job_id: str, url: str):
    """Main background task: crawl + analyze + generate report."""
    try:
        jobs[job_id]["status"] = "running"
        await send_progress(job_id, 2, f"Starting crawl of {url}…")

        # ====== CRAWL ======
        crawled_pages = []
        pages_found = [0]

        async def progress_cb(count, max_pages, current_url):
            pages_found[0] = count
            pct = min(45, int((count / max_pages) * 45))
            short_url = current_url[:60] + "…" if len(current_url) > 60 else current_url
            await send_progress(job_id, pct, f"Crawling page {count}: {short_url}")

        spider = Spider(url, progress_callback=progress_cb)
        crawled_pages = await spider.crawl()

        total_pages = len(crawled_pages)
        await send_progress(job_id, 47, f"Crawled {total_pages} pages. Running analyzers…")

        # ====== ANALYZE ======
        await send_progress(job_id, 50, "Analyzing technical SEO…")
        technical = await asyncio.to_thread(analyze_technical, crawled_pages)

        await send_progress(job_id, 57, "Analyzing on-page SEO…")
        onpage = await asyncio.to_thread(analyze_onpage, crawled_pages)

        await send_progress(job_id, 63, "Analyzing schema markup…")
        schema = await asyncio.to_thread(analyze_schema, crawled_pages)

        await send_progress(job_id, 69, "Analyzing AEO readiness…")
        aeo = await asyncio.to_thread(analyze_aeo, crawled_pages)

        await send_progress(job_id, 74, "Analyzing GEO readiness…")
        geo = await asyncio.to_thread(analyze_geo, crawled_pages)

        await send_progress(job_id, 79, "Analyzing performance…")
        performance = await asyncio.to_thread(analyze_performance, crawled_pages)

        await send_progress(job_id, 83, "Analyzing images…")
        images = await asyncio.to_thread(analyze_images, crawled_pages)

        await send_progress(job_id, 85, "Analyzing local SEO…")
        local_seo = await asyncio.to_thread(analyze_local_seo, crawled_pages)

        await send_progress(job_id, 87, "Analyzing conversion optimization…")
        conversion = await asyncio.to_thread(analyze_conversion, crawled_pages)

        await send_progress(job_id, 89, "Analyzing content quality…")
        content = await asyncio.to_thread(analyze_content, crawled_pages)

        await send_progress(job_id, 91, "Calculating scores…")
        scores = calculate_scores(technical, onpage, schema, aeo, geo, performance, images, local_seo, conversion, content)

        await send_progress(job_id, 91, "Checking Wayback Machine history…")
        wayback = await analyze_wayback(parsed_domain)

        await send_progress(job_id, 92, "Calculating revenue impact…")
        revenue_impact = await asyncio.to_thread(
            calculate_revenue_impact,
            total_pages, scores,
            technical, onpage, schema, aeo, geo,
            performance, images, local_seo, conversion, content,
        )

        await send_progress(job_id, 93, "Generating AI recommendations… (this may take a minute)")
        parsed_domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        ai_recommendations = await asyncio.to_thread(
            generate_ai_recommendations,
            parsed_domain, total_pages, scores,
            technical, onpage, schema, aeo, geo,
            performance, images, local_seo, conversion, content,
        )

        await send_progress(job_id, 96, "Generating PDF report…")
        report_path = await asyncio.to_thread(
            generate_report,
            job_id,
            url,
            total_pages,
            scores,
            technical,
            onpage,
            schema,
            aeo,
            geo,
            performance,
            images,
            local_seo,
            conversion,
            content,
            ai_recommendations,
            revenue_impact,
            wayback,
        )

        await send_progress(job_id, 98, "Finalizing report…")

        # Build result payload (serializable data for WebSocket)
        result_data = {
            "job_id": job_id,
            "root_url": url,
            "total_pages": total_pages,
            "report_path": report_path,
            "scores": _make_serializable(scores),
            "technical": _make_serializable({
                "score": technical.get("score", 0),
                "summary": technical.get("summary", {}),
                "issues_4xx": technical.get("issues_4xx", [])[:20],
                "redirect_chains": technical.get("redirect_chains", [])[:10],
                "slow_pages": technical.get("slow_pages", [])[:10],
                "http_pages": technical.get("http_pages", [])[:10],
            }),
            "onpage": _make_serializable({
                "score": onpage.get("score", 0),
                "summary": onpage.get("summary", {}),
            }),
            "schema": _make_serializable({
                "score": schema.get("score", 0),
                "summary": schema.get("summary", {}),
                "all_schema_types_found": schema.get("all_schema_types_found", []),
                "missing_schema_types": schema.get("missing_schema_types", [])[:10],
                "has_about_page": False,
            }),
            "aeo": _make_serializable({
                "score": aeo.get("score", 0),
                "summary": aeo.get("summary", {}),
            }),
            "geo": _make_serializable({
                "score": geo.get("score", 0),
                "summary": geo.get("summary", {}),
                "has_about_page": geo.get("has_about_page", False),
                "has_contact_page": geo.get("has_contact_page", False),
                "brand_name": geo.get("brand_name", ""),
            }),
            "performance": _make_serializable({
                "score": performance.get("score", 0),
                "summary": performance.get("summary", {}),
            }),
            "images": _make_serializable({
                "score": images.get("score", 0),
                "summary": images.get("summary", {}),
            }),
            "local_seo": _make_serializable({
                "score": local_seo.get("score", 0),
                "summary": local_seo.get("summary", {}),
                "has_contact_page": local_seo.get("has_contact_page", False),
                "has_google_maps": local_seo.get("has_google_maps", False),
                "has_local_business_schema": local_seo.get("has_local_business_schema", False),
                "has_nap_info": local_seo.get("has_nap_info", False),
                "has_review_schema": local_seo.get("has_review_schema", False),
                "has_opening_hours": local_seo.get("has_opening_hours", False),
                "location_optimized_pages": local_seo.get("location_optimized_pages", 0),
                "missing_local_signals": local_seo.get("missing_local_signals", []),
            }),
            "conversion": _make_serializable({
                "score": conversion.get("score", 0),
                "summary": conversion.get("summary", {}),
                "pages_missing_cta": conversion.get("pages_missing_cta", [])[:15],
            }),
            "content": _make_serializable({
                "score": content.get("score", 0),
                "summary": content.get("summary", {}),
                "thin_content_pages": content.get("thin_content_pages", [])[:15],
            }),
            "revenue_impact": _make_serializable(revenue_impact),
            "wayback": _make_serializable(wayback),
        }

        # Store full data in job
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["data"] = result_data

        await send_progress(job_id, 100, "Analysis complete! Preparing results…")

        # Send complete message
        if job_id in ws_connections:
            try:
                await ws_connections[job_id].send_json({
                    "type": "complete",
                    "data": result_data,
                })
            except Exception:
                pass

    except Exception as e:
        error_msg = str(e)
        tb = traceback.format_exc()
        print(f"[Job {job_id}] Error: {error_msg}\n{tb}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = error_msg

        if job_id in ws_connections:
            try:
                await ws_connections[job_id].send_json({
                    "type": "error",
                    "message": f"Analysis failed: {error_msg}",
                })
            except Exception:
                pass


def _make_serializable(obj):
    """Recursively ensure all values are JSON-serializable."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    else:
        return str(obj)


# ====== STARTUP ======
@app.on_event("startup")
async def startup_event():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    print("=" * 60)
    print("  SEO Audit Pro is running!")
    print("  Open: http://localhost:8000")
    print("=" * 60)


# ====== ENTRY POINT ======
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
