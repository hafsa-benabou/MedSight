from __future__ import annotations


class AppError(Exception):
    """Erreur métier renvoyée au client sous forme JSON {error: {code, message, details}}."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status_code, self.details = code, message, status_code, details or {}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}
