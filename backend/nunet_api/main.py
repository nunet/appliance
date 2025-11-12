# backend/nunet_api/main.py
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from pathlib import Path
import os

from .security import require_auth
from .routers import auth, contracts, dms, ensemble, ensemble_schema, organizations, payments, sysinfo, upnp


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
    allow_origins=["*"],        # we can tighten later if same-origin
    allow_credentials=True,
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
# Priority 1 (production): use env var (e.g., /usr/share/nunet-dms/frontend/dist or /home/ubuntu/package/frontend/dist)
# Priority 2 (dev only): try repo layout (../frontend/dist from backend/)
ENV_KEY = "NUNET_STATIC_DIR"
env_dir = os.environ.get(ENV_KEY)

if env_dir:
    static_path = Path(env_dir).resolve()
else:
    # dev fallback – likely *not* valid inside a PEX unless you bundled the dist into the package
    static_path = (Path(__file__).resolve().parents[2] / "frontend" / "dist")

if not static_path.exists():
    raise RuntimeError(
        f"Static directory not found: {static_path}\n"
        f"Set {ENV_KEY} to your built SPA dir (e.g., /home/ubuntu/package/frontend/dist)."
    )

app.mount("/", SPAStaticFiles(directory=str(static_path), html=True), name="spa")
