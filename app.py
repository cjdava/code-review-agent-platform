from fastapi import FastAPI

from api.routes import router
from infrastructure.logging_config import configure_logging

configure_logging()

app = FastAPI(title="Code Review Agent Platform", version="0.1.0")
app.include_router(router)
