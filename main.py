import os

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ahp.api import app
from rul.api import router as rul_router
from upload.api import router as upload_router
from rag.api import router as rag_router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rul_router)
app.include_router(upload_router)
app.include_router(rag_router)

# Serve React frontend static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
frontend_dist = os.path.join(BASE_DIR, "frontend", "dist")

print(f"Frontend dist path: {frontend_dist}")
print(f"Frontend dist exists: {os.path.exists(frontend_dist)}")
print(f"Frontend dist contents: {os.listdir(frontend_dist) if os.path.exists(frontend_dist) else 'NOT FOUND'}")

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dist, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith(("ahp/", "rul/", "upload/", "rag/", "docs/")):
            raise HTTPException(status_code=404)
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not built")
