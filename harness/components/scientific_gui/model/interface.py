from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Reply:
    actions: list[dict]
    text: str = ""
    usage: dict = field(default_factory=dict)
    native_message: dict | None = None


class Model(Protocol):
    def generate(self, messages: list[dict], tools: list[dict], timeout: float) -> Reply: ...


class ProtocolError(ValueError):
    """A model response cannot be executed; usage still counts toward the run."""
    def __init__(self, message, usage=None):
        super().__init__(message)
        self.usage = usage or {}


class ModelHTTPError(RuntimeError):
    """HTTP failure with diagnostics sanitized by the provider adapter."""
    def __init__(self, status, code="unspecified", message="", request_id=""):
        self.status = status
        self.code = code
        self.provider_message = message
        self.request_id = request_id
        detail = f"Model HTTP error {status}: {code}"
        if request_id:
            detail += f"; request_id={request_id}"
        super().__init__(detail)
