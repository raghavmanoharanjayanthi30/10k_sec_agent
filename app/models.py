"""Pydantic models for API requests and responses."""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# Constants for validation
MAX_QUESTION_LENGTH = 1000
MIN_QUESTION_LENGTH = 10
BLOCKED_PATTERNS = [
    r"ignore\s+(previous|all|above)",
    r"system\s*prompt",
    r"you\s+are\s+now",
    r"forget\s+(everything|all)",
    r"<script",
    r"javascript:",
]
INVALID_CHARS_PATTERN = r"[<>{}\\]"


# Request models

class ResearchRequest(BaseModel):
    """Request to start a research job."""
    question: str = Field(
        ..., 
        description="Research question about SEC filings",
        min_length=MIN_QUESTION_LENGTH,
        max_length=MAX_QUESTION_LENGTH,
    )
    company: Optional[str] = Field(
        None, 
        description="Optional company ticker hint",
        max_length=10,
    )
    
    @field_validator('question')
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate and sanitize the question."""
        # Strip whitespace
        v = v.strip()
        
        # Check minimum length after stripping
        if len(v) < MIN_QUESTION_LENGTH:
            raise ValueError(f"Question must be at least {MIN_QUESTION_LENGTH} characters")
        
        # Check for invalid characters
        if re.search(INVALID_CHARS_PATTERN, v):
            raise ValueError("Question contains invalid characters")
        
        # Check for potential prompt injection patterns
        v_lower = v.lower()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, v_lower):
                raise ValueError("Question contains blocked content")
        
        # Check for excessive special characters (potential attack)
        special_char_count = len(re.findall(r'[^a-zA-Z0-9\s.,?!\'-]', v))
        if special_char_count > len(v) * 0.3:  # More than 30% special chars
            raise ValueError("Question contains too many special characters")
        
        return v
    
    @field_validator('company')
    @classmethod
    def validate_company(cls, v: Optional[str]) -> Optional[str]:
        """Validate company ticker."""
        if v is None:
            return v
        
        v = v.strip().upper()
        
        # Ticker should be alphanumeric
        if not re.match(r'^[A-Z0-9]{1,10}$', v):
            raise ValueError("Invalid company ticker format")
        
        return v


# Response models

class Finding(BaseModel):
    """A single finding from the research."""
    topic: str
    content: str
    source_item: str


class Citation(BaseModel):
    """Citation to a source filing."""
    source: str
    url: str
    item: str
    excerpt: str


class ResearchReport(BaseModel):
    """Final research report."""
    question: str
    company: str
    company_name: str
    summary: str
    findings: list[Finding]
    filing_date: str
    filing_url: str


class JobCreated(BaseModel):
    """Response when a job is created."""
    job_id: str
    status: str = "queued"


class JobStatus(BaseModel):
    """Response for job status check."""
    job_id: str
    status: str  # queued | running | done | failed
    result: Optional[ResearchReport] = None
    citations: Optional[list[Citation]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "0.1.0"


class CacheStats(BaseModel):
    """Cache statistics response."""
    hits: int
    misses: int
    hit_rate: str
    size: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
