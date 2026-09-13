import re

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_SECRET = re.compile(r"(?i)(postgres(?:ql)?|redis)://\S+|(?:password|api[_-]?key)\s*[=:]\s*\S+")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def safe_message(value: object) -> str:
    return _SECRET.sub("[REDACTED]", str(value))[:500]


async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": safe_message(exc.message),
                 "request_id": request.state.request_id, "retryable": exc.retryable},
    )


async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"code": "internal_error",
        "message": "服务内部错误", "request_id": request.state.request_id, "retryable": False})


async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "validation_error",
        "message": "请求参数不合法", "request_id": request.state.request_id, "retryable": False,
        "details": [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]})
