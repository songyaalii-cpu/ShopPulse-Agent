from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id", str(uuid4()))[:64]
        length = int(request.headers.get("content-length", "0") or 0)
        if length > self.max_body_bytes:
            return JSONResponse(status_code=413, content={"code": "body_too_large",
                "message": "请求体过大", "request_id": request.state.request_id, "retryable": False})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
