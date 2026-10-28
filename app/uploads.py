"""Bound application memory while reading multipart upload spool files."""
from fastapi import HTTPException, UploadFile


async def read_bounded_upload(file: UploadFile, limit: int) -> bytes:
    """Read at most limit + 1 bytes, rejecting overflow before ingestion."""
    contents = bytearray()
    while True:
        chunk = await file.read(min(1024 * 1024, limit - len(contents) + 1))
        if not chunk:
            return bytes(contents)
        contents.extend(chunk)
        if len(contents) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {limit // (1024 * 1024)} MB.",
            )
