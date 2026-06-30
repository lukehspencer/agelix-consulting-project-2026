from fastapi.middleware.cors import CORSMiddleware

from ahp.api import app
from rul.api import router as rul_router
from upload.api import router as upload_router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rul_router)
app.include_router(upload_router)
