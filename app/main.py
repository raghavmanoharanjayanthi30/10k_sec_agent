"""FastAPI application for 10-K filing research."""

import os
import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .models import (
    ResearchRequest,
    JobCreated,
    JobStatus,
    HealthResponse,
    ResearchReport,
    Finding,
    Citation,
    CacheStats,
    ErrorResponse,
)
from .config import get_settings
from agents import research
from tools.cache import get_cache

# Load environment variables
load_dotenv()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# API Key authentication
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify the API key from request header.
    
    If API_KEY is not set in environment, authentication is disabled (development mode).
    """
    expected_key = os.getenv("API_KEY")
    
    # If no API key configured, allow all requests (development mode)
    if not expected_key:
        return "dev-mode"
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include 'X-API-Key' header.",
        )
    
    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )
    
    return api_key


# Initialize FastAPI app
app = FastAPI(
    title="10-K Filing Research Agent",
    description="Multi-agent system for SEC 10-K filing analysis",
    version="0.1.0",
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# In-memory job storage
# NOTE: For production, replace with Redis or a database for persistence
# and horizontal scaling. See README for details.
jobs: Dict[str, dict] = {}


@app.exception_handler(ValueError)
async def validation_exception_handler(request: Request, exc: ValueError):
    """Handle validation errors with proper response."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": "VALIDATION_ERROR"},
    )


async def run_research_job(job_id: str, question: str):
    """Background task to run research."""
    jobs[job_id]["status"] = "running"
    
    try:
        # Run the research agent
        result = await research(question)
        
        # Check for errors
        if result.get("error"):
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = result["error"]
            return
        
        # Extract report
        report_data = result.get("report", {})
        
        # Build response models
        findings = [
            Finding(
                topic=f.get("topic", ""),
                content=f.get("content", ""),
                source_item=f.get("source_item", ""),
            )
            for f in report_data.get("findings", [])
        ]
        
        citations = [
            Citation(
                source=c.get("source", ""),
                url=c.get("url") or "",
                item=c.get("item", ""),
                excerpt=c.get("excerpt", ""),
            )
            for c in result.get("citations", [])
        ]
        
        report = ResearchReport(
            question=report_data.get("question", question),
            company=report_data.get("company", ""),
            company_name=report_data.get("company_name", ""),
            summary=report_data.get("summary", ""),
            findings=findings,
            filing_date=report_data.get("filing_date") or "",
            filing_url=report_data.get("filing_url") or "",
        )
        
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = report
        jobs[job_id]["citations"] = citations
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.post("/research", response_model=JobCreated)
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def create_research_job(
    request: Request,
    payload: ResearchRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
):
    """
    Submit a research question about SEC 10-K filings.
    
    Returns a job_id that can be used to check status and get results.
    
    **Authentication**: Requires `X-API-Key` header (if API_KEY env var is set).
    
    **Rate limited**: 10 requests per minute per IP address.
    """
    job_id = str(uuid.uuid4())
    
    # Initialize job
    jobs[job_id] = {
        "status": "queued",
        "question": payload.question,
        "result": None,
        "citations": None,
        "error": None,
    }
    
    # Start background task
    background_tasks.add_task(run_research_job, job_id, payload.question)
    
    return JobCreated(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobStatus)
@limiter.limit("60/minute")  # 60 status checks per minute per IP
async def get_job_status(
    request: Request, 
    job_id: str,
    api_key: str = Depends(verify_api_key),
):
    """
    Check the status of a research job.
    
    Returns the result when the job is complete.
    
    **Authentication**: Requires `X-API-Key` header (if API_KEY env var is set).
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        result=job.get("result"),
        citations=job.get("citations"),
        error=job.get("error"),
    )


@app.get("/healthz", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    No authentication required.
    """
    return HealthResponse(status="healthy", version="0.1.0")


@app.get("/cache/stats", response_model=CacheStats)
@limiter.limit("30/minute")
async def cache_stats(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Get cache statistics.
    
    **Authentication**: Requires `X-API-Key` header (if API_KEY env var is set).
    """
    cache = get_cache()
    stats = cache.get_stats()
    return CacheStats(**stats)


@app.post("/cache/clear")
@limiter.limit("5/minute")
async def clear_cache(
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Clear the filing cache.
    
    **Authentication**: Requires `X-API-Key` header (if API_KEY env var is set).
    """
    cache = get_cache()
    count = cache.clear()
    return {"cleared": count, "message": f"Cleared {count} cache entries"}


# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
