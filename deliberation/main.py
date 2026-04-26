# -*- coding: utf-8 -*-
"""
aimastering-deliberation: 3-Vendor Deliberation Engine

Two responsibilities:
  1. /internal/deliberate — 3-vendor parallel AI deliberation (httpx)
  2. /internal/validate-formplan — Rule-based arbiter merge (weighted median + veto)

Stateless. No audio. No file storage. AI calls only.
"""

import time
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from deliberation.services.deliberation import run_triadic_deliberation
from deliberation.services.merge_rule import arbitrate

# ──────────────────────────────────────────
# Logging
# ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("deliberation")


# ──────────────────────────────────────────
# Application Lifecycle
# ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("DELIBERATION: 3-Vendor Deliberation Engine is online.")
    yield
    logger.info("DELIBERATION shutting down.")


# ──────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────
app = FastAPI(
    title="deliberation",
    description="3-Vendor Deliberation Engine — parallel AI calls + weighted median arbiter",
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────
# Middleware: Request Tracking
# ──────────────────────────────────────────
@app.middleware("http")
async def request_tracking_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()
    logger.info(f"[{request_id}] {request.method} {request.url.path}")
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(f"[{request_id}] Completed in {duration_ms}ms → {response.status_code}")
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Duration-Ms"] = str(duration_ms)
    return response


# ──────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────
class DeliberateRequest(BaseModel):
    """Request for 3-vendor parallel deliberation."""
    analysis_data: dict = Field(..., description="Audio analysis result from audition")
    target_platform: str = Field(default="streaming", description="Target platform")
    target_lufs: float = Field(default=-14.0)
    target_true_peak: float = Field(default=-1.0)
    sage_config: Optional[dict] = Field(default=None, description="Premium deliberation archetype config")


class ArbitrateRequest(BaseModel):
    """Request for formplan arbiter merge."""
    opinions: list = Field(..., description="List of vendor opinions")
    raw_analysis: dict = Field(..., description="Raw audio analysis (ground truth)")


# ══════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════
@app.get("/")
async def index() -> JSONResponse:
    """Root endpoint providing service identity."""
    return JSONResponse(content={
        "status": "online",
        "service": "deliberation",
        "engine": "3-Vendor Deliberation Engine",
        "message": "AI-driven parallel deliberation microservice is ready.",
        "documentation": "/docs"
    })


@app.get("/health")
async def health() -> JSONResponse:
    """Health check for Cloud Run."""
    return JSONResponse(content={
        "status": "ready",
        "service": "deliberation",
        "version": "1.0.0",
        "stores_audio": False,
    })


@app.post("/internal/deliberate")
async def deliberate(req: DeliberateRequest) -> JSONResponse:
    """
    3-vendor parallel deliberation.
    OpenAI + Anthropic + Gemini → independent opinions via httpx.
    Integration is NOT done here. That is merge_rule's job.
    """
    try:
        result = await run_triadic_deliberation(
            analysis_data=req.analysis_data,
            target_platform=req.target_platform,
            target_lufs=req.target_lufs,
            target_true_peak=req.target_true_peak,
            sage_config=req.sage_config,
        )
    except Exception as e:
        import traceback
        logger.error(f"Deliberation failed: {type(e).__name__}: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Deliberation failed: {type(e).__name__}: {e}",
        )

    return JSONResponse(content=result)


@app.post("/internal/validate-formplan")
async def validate_formplan(req: ArbitrateRequest) -> JSONResponse:
    """
    Rule-based arbiter merge of multi-vendor opinions.
    Weighted median + union + veto logic + contradiction detection.
    """
    try:
        result = arbitrate(
            opinions=req.opinions,
            raw_analysis=req.raw_analysis,
        )
    except Exception as e:
        logger.error(f"Arbitration failed: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Arbitration failed. Check server logs for details.",
        )

    return JSONResponse(content=result)

