"""Content-free errors exposed at import and CLI boundaries."""

from __future__ import annotations


class XFIError(Exception):
    code = "XFI_ERROR"

    def __init__(self, code: str | None = None):
        self.code = code or self.code
        super().__init__(self.code)


class ValidationError(XFIError):
    code = "REJECTED_SCHEMA"


class StoreError(XFIError):
    code = "STORE_ERROR"
