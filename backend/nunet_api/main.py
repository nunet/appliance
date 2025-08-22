# nunet_api/app/main.py
from fastapi import FastAPI
from .routers import dms, sysinfo, ensemble, stream, proc, organizations
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="NuNet Local API", version="1.0.0")

# CORS for Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dms.router, prefix="/dms", tags=["dms"])
app.include_router(sysinfo.router, prefix="/sys", tags=["system"])
app.include_router(ensemble.router, prefix="/ensemble", tags=["ensemble"])
app.include_router(stream.router, tags=["stream"])
app.include_router(proc.router, prefix="/proc", tags=["proc"])
app.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
@app.get("/health")
def health():
    return {"ok": True}
