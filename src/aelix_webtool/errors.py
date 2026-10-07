"""Errors safe to expose to the model and CLI; never include upstream bodies."""

from __future__ import annotations


class WebToolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        attempts: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.attempts = attempts

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            result["retry_after_seconds"] = self.retry_after_seconds
        if self.attempts is not None:
            result["attempts"] = self.attempts
        return result
