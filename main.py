from ahp.api import app
from rul.api import router as rul_router

app.include_router(rul_router)
