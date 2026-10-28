import asyncio

import pytest
from fastapi import HTTPException

from app.uploads import read_bounded_upload


class RecordingUpload:
    def __init__(self, content):
        self.content = content
        self.offset = 0

    async def read(self, size):
        assert 0 < size <= 1024 * 1024
        chunk = self.content[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


@pytest.mark.parametrize('size', [0, 9, 10])
def test_accepts_up_to_exact_limit(size):
    assert asyncio.run(read_bounded_upload(RecordingUpload(b'x' * size), 10)) == b'x' * size


def test_overflow_stops_reading_before_consuming_entire_file():
    upload = RecordingUpload(b'x' * 1000)
    with pytest.raises(HTTPException) as error:
        asyncio.run(read_bounded_upload(upload, 10))
    assert error.value.status_code == 413
    assert upload.offset == 11
