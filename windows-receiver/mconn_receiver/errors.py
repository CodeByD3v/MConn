"""Protocol errors. Serialised as {"error", "message", "retryable", ...extra} (DESIGN.md 5.6)."""
from __future__ import annotations


class MConnError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        retryable: bool = False,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.extra = extra or {}

    def body(self) -> dict:
        return {"error": self.code, "message": self.message, "retryable": self.retryable, **self.extra}
