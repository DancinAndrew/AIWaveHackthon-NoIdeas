from __future__ import annotations


class ApplicationError(Exception):
    """Expected boundary error that is safe to return to an API client."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class NotFoundError(ApplicationError):
    def __init__(self, message: str = "找不到指定資源") -> None:
        super().__init__(404, "not_found", message)


class ForbiddenError(ApplicationError):
    def __init__(self, message: str = "你沒有權限操作這個資源") -> None:
        super().__init__(403, "forbidden", message)


class ConflictError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(409, "conflict", message)


class ValidationError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(422, "validation_error", message)
