"""FastAPI application factory."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from . import __version__, db, llm, ratelimit
from .config import FRONTEND_DIR, get_settings
from .security import CSRF_HEADER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("startpunch.api")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="StartPunch API", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json",
                  redoc_url=None)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type", "X-StartPunch-Client"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        path = request.url.path
        if path.startswith("/api/"):
            # CSRF: browsers cannot attach this custom header cross-site without a CORS preflight we don't allow.
            if request.method in UNSAFE and request.headers.get(CSRF_HEADER) != "web":
                return JSONResponse({"detail": "Missing client header."}, status_code=403)
            try:
                ratelimit.hit("default", ratelimit.client_ip(request))
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        if path.startswith("/api/"):
            logger.info("%s %s %s %sms rid=%s", request.method, path, response.status_code,
                        int((time.perf_counter() - started) * 1000), request_id)
        return response

    @app.exception_handler(db.DatabaseNotConfigured)
    async def _db_missing(_request: Request, exc: db.DatabaseNotConfigured):
        return JSONResponse({"detail": str(exc), "code": "database_not_configured"}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
        first = errors[0] if errors else {"field": "", "message": "Invalid input"}
        return JSONResponse({"detail": f"{first['field'] or 'input'}: {first['message']}", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)

    @app.get("/api/health")
    def health():
        status = {"status": "ok", "version": __version__, "environment": settings.env,
                  "ai_configured": settings.ai_configured, "database_configured": settings.database_configured,
                  "auth_configured": settings.session_secret_configured}
        try:
            db.init_db()
            status["database"] = "ok"
        except Exception as exc:  # report, don't crash
            status["database"] = f"error: {type(exc).__name__}"
            status["status"] = "degraded"
        if not (settings.ai_configured and settings.session_secret_configured):
            status["status"] = "degraded"
        exhausted = llm.model_status()
        if exhausted:
            status["ai_models"] = exhausted
        return status

    from .routes import auth, intelligence, reports, social

    app.include_router(auth.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(intelligence.router, prefix="/api")
    app.include_router(social.router, prefix="/api")

    if settings.serve_frontend and FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app


app = create_app()
