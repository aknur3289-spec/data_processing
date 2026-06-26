from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


class TemporaryUploadStorage:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def cleanup(self) -> None:
        self._tmp.cleanup()

    async def save_upload(self, upload: UploadFile) -> Path:
        filename = Path(upload.filename or f"upload-{uuid4().hex}").name
        target = self.root / filename

        with target.open("wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        await upload.seek(0)
        return target

    def copy_to_temp(self, source: Path) -> Path:
        filename = Path(source.name).name
        target = self.root / filename
        shutil.copy2(source, target)
        return target
