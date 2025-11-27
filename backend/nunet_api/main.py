# backend/nunet_api/main.py
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from modules.path_constants import FRONTEND_DIR
from .security import require_auth
from .routers import auth, contracts, dms, ensemble, ensemble_schema, organizations, payments, sysinfo, upnp

logger = logging.getLogger(__name__)

NUNET_STATIC_DIR = os.getenv("NUNET_STATIC_DIR")
if NUNET_STATIC_DIR:
    NUNET_STATIC_DIR = Path(NUNET_STATIC_DIR)
else:
    NUNET_STATIC_DIR = FRONTEND_DIR / "dist"

cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    allow_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    if not allow_origins:
        allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
else:
    allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
cors_allow_credentials = True
if allow_origins == ["*"]:
    cors_allow_credentials = False


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and path != "index.html":
                return await super().get_response("index.html", scope)
            raise


app = FastAPI(title="NuNet Local API", version="1.0.0")

app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(require_auth)]

# --- API routers ---
app.include_router(auth.router)
app.include_router(dms.router, prefix="/dms", tags=["dms"], dependencies=protected)
app.include_router(sysinfo.router, prefix="/sys", tags=["system"], dependencies=protected)
app.include_router(ensemble.router, prefix="/ensemble", tags=["ensemble"], dependencies=protected)
app.include_router(organizations.router, prefix="/organizations", tags=["organizations"], dependencies=protected)
app.include_router(payments.router, prefix="/payments", tags=["payments"], dependencies=protected)
app.include_router(ensemble_schema.router, prefix="/ensemble", tags=["ensemble"], dependencies=protected)
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"], dependencies=protected)
app.include_router(contracts.router, prefix="/contracts", tags=["contracts"], dependencies=protected)
app.include_router(upnp.router, prefix="/upnp", tags=["upnp"], dependencies=protected)


@app.get("/health")
def health():
    return {"ok": True}


# --- Static: frontend/dist ---
if NUNET_STATIC_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(NUNET_STATIC_DIR), html=True), name="spa")
else:
    logger.warning("Static directory not found at %s; skipping SPA mount.", NUNET_STATIC_DIR)
