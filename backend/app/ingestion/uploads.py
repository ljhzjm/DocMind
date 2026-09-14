import asyncio
from pathlib import Path

from fastapi import UploadFile

_CHUNK_READ_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    """上传文件不满足扩展名或大小限制。"""


def validate_upload_filename(
    filename: str | None,
    *,
    allowed_extensions: frozenset[str],
) -> tuple[str, str]:
    """校验并返回安全文件名与不带点的小写文件类型。"""
    if not filename:
        raise UploadValidationError("filename is required")

    safe_name = Path(filename).name
    if safe_name != filename:
        raise UploadValidationError("filename must not contain a path")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise UploadValidationError(f"unsupported file type; allowed: {allowed}")

    return safe_name, suffix.removeprefix(".")


async def save_upload_file(
    upload: UploadFile,
    destination: Path,
    *,
    max_size_bytes: int,
) -> int:
    """分块写盘并强制大小上限，超限时删除未完成文件。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_handle = await asyncio.to_thread(destination.open, "wb")
    size = 0
    success = False

    try:
        while chunk := await upload.read(_CHUNK_READ_SIZE):
            size += len(chunk)
            if size > max_size_bytes:
                raise UploadValidationError(f"file exceeds the {max_size_bytes} byte limit")
            await asyncio.to_thread(file_handle.write, chunk)
        success = True
    finally:
        await asyncio.to_thread(file_handle.close)
        if not success:
            destination.unlink(missing_ok=True)

    return size
