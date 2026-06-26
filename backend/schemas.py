from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PriceItem(BaseModel):
    partner_name: str | None = None
    source_file: str
    file_format: str
    source_sheet: str | None = None
    source_page: int | None = None
    effective_date: str | None = None
    service_code_source: str | None = None
    service_name_raw: str
    service_id: str | None = None
    price_resident_kzt: float | None = None
    price_sng_kzt: float | None = None
    price_nonresident_kzt: float | None = None
    price_original: float | None = None
    currency_original: str = "KZT"
    is_verified: bool = False
    verification_note: str | None = None
    is_active: bool = True
    parse_status: str = "done"
    parse_log: list[str] | str | None = None
    extraction_method: str | None = None


class ParseJob(BaseModel):
    file_name: str
    file_format: str
    status: Literal["done", "needs_review", "error", "skipped"]
    items_count: int = 0
    parse_log: list[str] = Field(default_factory=list)


class ParseSummary(BaseModel):
    total_files: int
    done: int
    needs_review: int
    error: int
    skipped: int
    items_count: int


class ParseResponse(BaseModel):
    items: list[PriceItem]
    jobs: list[dict[str, Any]]
    summary: dict[str, Any]
