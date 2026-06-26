from __future__ import annotations

import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from parser.docx_parser import parse_docx
from parser.parser_pdf_ocr import (
    FileJob,
    detect_file_format,
    effective_date_from_filename,
    partner_from_filename,
    process_pdf_job,
    safe_extract_zip,
)
from parser.xlsx_parser import parse_xlsx


SUPPORTED_FILE_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".docx", ".pdf"}
SUPPORTED_ARCHIVE_EXTENSION = ".zip"


def parse_file(
    file_path: str | Path,
    *,
    enable_ocr: bool = True,
    ocr_max_pages: int | None = None,
) -> dict[str, Any]:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_FILE_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {suffix or 'unknown'}")

    job = _new_job(path)

    try:
        if suffix in {".xlsx", ".xls", ".xlsm"}:
            raw_items = parse_xlsx(str(path))
            items = [_normalize_narrow_item(item, path, suffix.lstrip("."), "excel") for item in raw_items]
            _finish_adapter_job(job, items)
        elif suffix == ".docx":
            raw_items = parse_docx(str(path))
            items = [_normalize_narrow_item(item, path, "docx", "docx_table") for item in raw_items]
            _finish_adapter_job(job, items)
        else:
            job.file_format = detect_file_format(path)
            items = process_pdf_job(job, enable_ocr=enable_ocr, ocr_max_pages=ocr_max_pages)
            items = [_normalize_pdf_item(item, path) for item in items]

    except Exception as exc:
        job.status = "error"
        job.log(str(exc))
        items = []

    return _build_response([job], items)


def parse_archive(
    zip_path: str | Path,
    *,
    enable_ocr: bool = True,
    ocr_max_pages: int | None = None,
) -> dict[str, Any]:
    zip_path = Path(zip_path)
    if zip_path.suffix.lower() != SUPPORTED_ARCHIVE_EXTENSION:
        raise ValueError("Archive upload must be a .zip file")
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    jobs: list[FileJob] = []
    all_items: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        safe_extract_zip(zip_path, tmp_dir)
        inner_files = sorted(
            p for p in tmp_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
        )

        for inner_path in inner_files:
            result = parse_file(
                inner_path,
                enable_ocr=enable_ocr,
                ocr_max_pages=ocr_max_pages,
            )
            jobs.extend(_jobs_to_file_jobs(result["jobs"]))
            all_items.extend(result["items"])

    for idx, job in enumerate(jobs, start=1):
        job.job_id = idx

    summary = _summary(jobs, all_items)
    summary["archive_name"] = zip_path.name
    return {
        "items": all_items,
        "jobs": [asdict(job) for job in jobs],
        "summary": summary,
    }


def validate_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ValueError("Uploaded archive is not a valid ZIP file")


def _new_job(path: Path) -> FileJob:
    return FileJob(
        job_id=1,
        file_name=path.name,
        file_path=str(path),
        file_format=path.suffix.lower().lstrip(".") or "unknown",
        parser_owner="backend_adapter",
    )


def _finish_adapter_job(job: FileJob, items: list[dict[str, Any]]) -> None:
    job.items_count = len(items)
    job.status = "done" if items else "needs_review"
    if not items:
        job.log("No price rows extracted")


def _normalize_narrow_item(
    item: dict[str, Any],
    path: Path,
    file_format: str,
    extraction_method: str,
) -> dict[str, Any]:
    resident = item.get("price_resident_kzt")
    sng = item.get("price_sng_kzt")
    nonresident = item.get("price_nonresident_kzt")

    return {
        "partner_name": partner_from_filename(path),
        "source_file": item.get("source_file") or path.name,
        "file_format": file_format,
        "source_sheet": item.get("source_sheet"),
        "source_page": None,
        "effective_date": effective_date_from_filename(path),
        "service_code_source": item.get("service_code_source"),
        "service_name_raw": item.get("service_name_raw") or "",
        "service_id": None,
        "price_resident_kzt": resident,
        "price_sng_kzt": sng,
        "price_nonresident_kzt": nonresident,
        "price_original": resident,
        "currency_original": "KZT",
        "is_verified": False,
        "verification_note": None,
        "is_active": True,
        "parse_status": "done",
        "parse_log": None,
        "extraction_method": extraction_method,
    }


def _normalize_pdf_item(item: dict[str, Any], path: Path) -> dict[str, Any]:
    normalized = dict(item)
    resident = normalized.get("price_resident_kzt")
    nonresident = normalized.get("price_nonresident_kzt")

    normalized.setdefault("partner_name", partner_from_filename(path))
    normalized.setdefault("source_file", path.name)
    normalized.setdefault("file_format", "pdf")
    normalized.setdefault("source_sheet", None)
    normalized.setdefault("source_page", None)
    normalized.setdefault("effective_date", effective_date_from_filename(path))
    normalized.setdefault("service_code_source", None)
    normalized.setdefault("service_id", None)
    normalized.setdefault("price_sng_kzt", resident)
    normalized.setdefault("price_nonresident_kzt", nonresident)
    normalized.setdefault("price_original", resident)
    normalized.setdefault("currency_original", "KZT")
    normalized.setdefault("is_verified", False)
    normalized.setdefault("verification_note", None)
    normalized.setdefault("is_active", True)
    normalized.setdefault("parse_status", "done")
    normalized.setdefault("parse_log", None)
    normalized.setdefault("extraction_method", None)

    if normalized.get("price_sng_kzt") is None:
        normalized["price_sng_kzt"] = resident
    if normalized.get("price_nonresident_kzt") is None:
        normalized["price_nonresident_kzt"] = resident
    if normalized.get("price_original") is None:
        normalized["price_original"] = resident

    return normalized


def _build_response(jobs: list[FileJob], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "jobs": [asdict(job) for job in jobs],
        "summary": _summary(jobs, items),
    }


def _summary(jobs: list[FileJob], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_files": len(jobs),
        "done": sum(1 for job in jobs if job.status == "done"),
        "needs_review": sum(1 for job in jobs if job.status == "needs_review"),
        "error": sum(1 for job in jobs if job.status == "error"),
        "skipped": sum(1 for job in jobs if job.status == "skipped"),
        "items_count": len(items),
    }


def _jobs_to_file_jobs(job_dicts: list[dict[str, Any]]) -> list[FileJob]:
    jobs: list[FileJob] = []
    for idx, job_data in enumerate(job_dicts, start=1):
        jobs.append(
            FileJob(
                job_id=idx,
                file_name=job_data.get("file_name", ""),
                file_path=job_data.get("file_path", ""),
                file_format=job_data.get("file_format", "unknown"),
                parser_owner=job_data.get("parser_owner", "backend_adapter"),
                status=job_data.get("status", "skipped"),
                started_at=job_data.get("started_at"),
                finished_at=job_data.get("finished_at"),
                items_count=job_data.get("items_count", 0),
                pages_count=job_data.get("pages_count"),
                parse_log=job_data.get("parse_log") or [],
            )
        )
    return jobs
