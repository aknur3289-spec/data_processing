from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from backend.parser_service import parse_archive, parse_file, validate_zip
from backend.schemas import ParseResponse
from backend.storage import TemporaryUploadStorage


app = FastAPI(title="Medical Price Parser Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse", response_model=ParseResponse)
async def parse_upload(
    file: UploadFile = File(...),
    enable_ocr: bool = Query(True),
    ocr_max_pages: int | None = Query(None, ge=1),
) -> dict:
    storage = TemporaryUploadStorage()
    try:
        path = await storage.save_upload(file)
        return parse_file(path, enable_ocr=enable_ocr, ocr_max_pages=ocr_max_pages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        storage.cleanup()


@app.post("/parse/archive", response_model=ParseResponse)
async def parse_archive_upload(
    file: UploadFile = File(...),
    enable_ocr: bool = Query(True),
    ocr_max_pages: int | None = Query(None, ge=1),
) -> dict:
    storage = TemporaryUploadStorage()
    try:
        path = await storage.save_upload(file)
        validate_zip(path)
        return parse_archive(path, enable_ocr=enable_ocr, ocr_max_pages=ocr_max_pages)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        storage.cleanup()
