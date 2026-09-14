from io import BytesIO
from pathlib import Path

import pytest
from app.ingestion.uploads import (
    UploadValidationError,
    save_upload_file,
    validate_upload_filename,
)
from fastapi import UploadFile


def test_upload_validation_accepts_pdf_and_rejects_unknown_extension() -> None:
    allowed = frozenset({".pdf", ".md", ".markdown"})

    assert validate_upload_filename("manual.PDF", allowed_extensions=allowed) == (
        "manual.PDF",
        "pdf",
    )
    with pytest.raises(UploadValidationError, match="unsupported file type"):
        validate_upload_filename("malware.exe", allowed_extensions=allowed)
    with pytest.raises(UploadValidationError, match="must not contain a path"):
        validate_upload_filename("../manual.pdf", allowed_extensions=allowed)


@pytest.mark.asyncio
async def test_upload_streaming_removes_file_over_20mb_limit(tmp_path: Path) -> None:
    upload = UploadFile(
        file=BytesIO(b"x" * 11),
        filename="large.pdf",
    )
    destination = tmp_path / "large.pdf"

    with pytest.raises(UploadValidationError, match="exceeds"):
        await save_upload_file(upload, destination, max_size_bytes=10)

    assert not destination.exists()
