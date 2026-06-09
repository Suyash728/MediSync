"""
MediSync FastAPI application entry point.

Security notes:
- CORS is restricted to the frontend origin (set via ALLOWED_ORIGINS env var).
- All Groq/Gemini API calls happen here — never in the frontend.
- JWT verification happens in routers via the get_current_patient dependency.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import upload, process, records, conflicts, share, abha
from utils.config import settings

app = FastAPI(
    title="MediSync API",
    description="Patient-controlled health records backend",
    version="0.1.0",
    # Disable the default /docs in production; enable for development
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow only the frontend origin. Never use allow_origins=["*"] for a medical app.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(upload,    prefix="/upload",    tags=["upload"])
app.include_router(process,   prefix="/process",   tags=["process"])
app.include_router(records,   prefix="/records",   tags=["records"])
app.include_router(conflicts, prefix="/conflicts", tags=["conflicts"])
app.include_router(share,     prefix="/share",     tags=["share"])
app.include_router(abha,      prefix="/abha",      tags=["abha"])


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health_check() -> dict[str, str]:
    """Simple liveness probe — used by the root npm dev script to confirm the
    backend is running before the frontend starts making API calls."""
    return {"status": "ok", "service": "medisync-api"}
