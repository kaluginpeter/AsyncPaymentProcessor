import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("starting %s (env=%s)", settings.app_name, settings.environment)
    yield
    logger.info("shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Asynchronous payment processing service: accepts payments, "
    "processes them via an emulated gateway over RabbitMQ, and notifies "
    "clients through webhooks.",
    version="1.0.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"},
    )


@app.get("/health", tags=["ops"], include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router)
