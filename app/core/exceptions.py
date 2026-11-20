from fastapi import HTTPException
from typing import Any, Dict, Optional


class AppException(HTTPException):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def unauthorized_error(message: str = "Authentication required", details: Optional[Dict[str, Any]] = None) -> AppException:
    return AppException(code="unauthorized", message=message, status_code=401, details=details)


def not_found_error(message: str = "Resource not found", details: Optional[Dict[str, Any]] = None) -> AppException:
    return AppException(code="not_found", message=message, status_code=404, details=details)


def validation_error(message: str = "Validation error", details: Optional[Dict[str, Any]] = None) -> AppException:
    return AppException(code="validation_error", message=message, status_code=422, details=details)


def gate_incomplete_error(missing_fields: list[str]) -> AppException:
    return AppException(
        code="gate_incomplete",
        message="Gate is incomplete",
        status_code=422,
        details={"missing_fields": missing_fields},
    )


def server_error(message: str = "Internal server error", details: Optional[Dict[str, Any]] = None) -> AppException:
    return AppException(code="server_error", message=message, status_code=500, details=details)
