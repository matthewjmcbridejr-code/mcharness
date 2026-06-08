from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import legacy_router, router as marius_router
from .branding import CATEGORY, LEGACY_CODENAME, PRODUCT_NAME, REPO_NAME, TAGLINE

_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIR = _ROOT / "web"


def create_app() -> FastAPI:
    app = FastAPI(
        title=PRODUCT_NAME,
        version="0.1.0",
        description=TAGLINE,
    )
    app.state.branding = {
        "product_name": PRODUCT_NAME,
        "repo_name": REPO_NAME,
        "tagline": TAGLINE,
        "category": CATEGORY,
        "legacy_codename": LEGACY_CODENAME,
    }
    app.include_router(marius_router)
    app.include_router(legacy_router)
    if _WEB_DIR.exists():
        app.mount("/web", StaticFiles(directory=str(_WEB_DIR), html=False), name="web")
    return app


app = create_app()
