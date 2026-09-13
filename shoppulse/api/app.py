from contextlib import asynccontextmanager

from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.exceptions import RequestValidationError
from shoppulse.api.errors import APIError, api_error_handler, unhandled_error_handler, validation_error_handler
from shoppulse.api.middleware import RequestContextMiddleware
from shoppulse.api.routers import evaluations, events, health, runs, sessions
from shoppulse.observability.logging import configure_logging
from shoppulse.settings import get_settings


def create_app(redis=None) -> FastAPI:
    cfg = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if redis is None:
            app.state.redis = await create_pool(
                RedisSettings.from_dsn(cfg.redis_url),
                default_queue_name=f"{cfg.redis_key_prefix}queue",
            )
        yield
        if redis is None: await app.state.redis.close()

    app = FastAPI(title="ShopPulse API", version="3.0.0", lifespan=lifespan)
    if redis is not None: app.state.redis = redis
    app.add_middleware(RequestContextMiddleware, max_body_bytes=cfg.max_request_body_bytes)
    # Local development often remaps the frontend port (for example 3000 ->
    # 13000). Allow loopback origins on any port in development while keeping
    # production restricted to the explicitly configured origins.
    local_origin_regex = None if cfg.is_production else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins,
        allow_origin_regex=local_origin_regex, allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Idempotency-Key", "X-Client-ID", "Last-Event-ID"])
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    for router in (health.router, sessions.router, runs.router, events.router, evaluations.router): app.include_router(router)
    return app


app = create_app()


def main():
    import uvicorn
    cfg = get_settings(); configure_logging(cfg.log_level, "api")
    uvicorn.run("shoppulse.api.app:app", host=cfg.api_host, port=cfg.api_port)
