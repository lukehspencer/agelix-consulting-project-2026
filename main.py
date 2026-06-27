from ahp.api import app
from rul.api import router as rul_router
from upload.api import router as upload_router

app.include_router(rul_router)
app.include_router(upload_router)
