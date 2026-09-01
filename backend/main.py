"""AuraMed — AI-Powered Medical Assistant.

FastAPI application wiring the 26-node architecture. Run with:

    uvicorn backend.main:app --host 0.0.0.0 --port 8000

Safety contract (Implementation Directive #2): the mandatory physician-review
disclaimer is enforced in THREE places —
  1. every response body carries ``disclaimer`` (AuraMedResponse),
  2. every API response carries the ``X-AuraMed-Disclaimer`` header (middleware),
  3. TTS output prepends the spoken disclaimer (Node 06).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import __version__
from backend.api import core_pipeline, diagnostics, edge_feedback, input_processing, security_infra
from backend.config import settings
from backend.core.cache import cache
from backend.core.disclaimer import DISCLAIMER_EN
from backend.nodes import registry_snapshot
from backend.nodes import registry as _registry  # noqa: F401  (registers all 26 nodes)

logger = logging.getLogger("auramed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for warning in settings.validate():
        logger.warning("CONFIG: %s", warning)
    warmed = cache.warm_knowledge_bases()
    logger.info("AuraMed v%s started — knowledge cache: %s", __version__, warmed)
    logger.info("Nodes registered: %d", len(registry_snapshot()))
    yield


app = FastAPI(
    title="AuraMed — AI-Powered Medical Assistant",
    version=__version__,
    description=(
        "26-point integrated medical AI architecture (Bengali + English) for localized "
        "and edge deployment. **Every output is decision-support only and requires "
        "licensed physician review before clinical action.**"
    ),
    contact={"name": "AuraMed", "url": "https://github.com/BFH-HAMID/AuraMed-Ai-Powered-Medical-Assistant"},
    lifespan=lifespan,
)

# CORS — clinics serve the UI from a different origin. Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mandatory disclaimer response header (safety directive #2)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def disclaimer_header(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - global guard
        logger.exception("Unhandled error: %s", exc)
        response = JSONResponse(
            status_code=500,
            content={
                "success": False,
                "node": 0,
                "node_name": "gateway",
                "data": {"error": "Internal error; safe fallback — refer to physician.",
                         "detail": str(exc)},
                "disclaimer": DISCLAIMER_EN,
            },
        )
    response.headers["X-AuraMed-Disclaimer"] = DISCLAIMER_EN
    return response


# ---------------------------------------------------------------------------
# Routers (the 5 architecture layers)
# ---------------------------------------------------------------------------
app.include_router(input_processing.router)
app.include_router(core_pipeline.router)
app.include_router(diagnostics.router)
app.include_router(security_infra.router)
app.include_router(edge_feedback.router)


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------
@app.get("/", tags=["meta"])
async def root():
    return {
        "service": "AuraMed — AI-Powered Medical Assistant",
        "version": __version__,
        "language_support": ["en", "bn"],
        "nodes": registry_snapshot(),
        "docs": "/docs",
        "openapi": "/openapi.json",
        "disclaimer": DISCLAIMER_EN,
    }


@app.get("/health", tags=["meta"])
async def health():
    return {
        "status": "ok",
        "version": __version__,
        "offline_mode": settings.offline_mode,
        "environment": settings.env,
        "knowledge_cache": cache.warm_knowledge_bases(),
        # Safety directive #2 applies to meta endpoints too, not only node routes.
        "disclaimer": DISCLAIMER_EN,
    }



