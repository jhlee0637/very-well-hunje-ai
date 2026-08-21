"""Sanitized application errors exposed through the API boundary."""

from __future__ import annotations


class HarnessError(Exception):
    status_code = 500
    error_type = "server_error"
    code = "harness_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def as_openai_error(self) -> dict:
        return {
            "error": {
                "message": self.message,
                "type": self.error_type,
                "code": self.code,
            }
        }


class InvalidRequestError(HarnessError):
    status_code = 400
    error_type = "invalid_request_error"
    code = "invalid_request"


class ConfigurationError(HarnessError):
    status_code = 503
    error_type = "server_error"
    code = "configuration_error"


class ModelUpstreamError(HarnessError):
    status_code = 502
    error_type = "upstream_error"
    code = "model_upstream_error"


class ModelTimeoutError(HarnessError):
    status_code = 504
    error_type = "upstream_timeout"
    code = "model_timeout"


class ModelProtocolError(HarnessError):
    status_code = 502
    error_type = "upstream_error"
    code = "model_protocol_error"


class RequestDeadlineError(HarnessError):
    status_code = 504
    error_type = "timeout_error"
    code = "request_deadline_exceeded"


class MCPError(Exception):
    """Internal retrieval error that should normally degrade, not become API 5xx."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
