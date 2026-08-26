"""Shared contracts for HiAgent OpenAPI tool modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


OPENAPI_VERSION = "2023-08-01"
OPENAPI_SERVICE = "app"


class OpenAPIClient(Protocol):
    """OpenAPI call boundary used by tool modules."""

    def call(
        self,
        *,
        action: str,
        body: Mapping[str, object] | None = None,
        version: str = OPENAPI_VERSION,
        service: str | None = None,
        timeout_seconds: float = 30,
    ) -> dict[str, object]: ...


def validate_pagination(page_number: int, page_size: int) -> None:
    """Validate the common HiAgent list pagination contract."""

    if page_number < 1:
        raise ValueError("page_number must be at least 1")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")
