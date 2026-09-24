import asyncio
import io
import os
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

os.environ.setdefault("DATABASE_URL", "sqlite://")
import backend.app.main as api


def image_upload(width=1536, height=1872, content_type="image/png"):
    # The API only needs the PNG signature and IHDR; decoding is done by Codex.
    header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)
    return UploadFile(file=io.BytesIO(header), filename="pet.png", headers=Headers({"content-type": content_type}))


class CodexSpriteTest(unittest.TestCase):
    def test_uploaded_link_is_private_and_expires(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)):
            result = asyncio.run(api.publish_codex_sprite(None, image_upload()))
            token = result["path"].rsplit("/", 1)[-1]
            response = api.get_codex_sprite(token)
            self.assertEqual(response.media_type, "image/png")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
            path = api.Path(directory) / "codex-sprites" / f"{token}.png"
            self.assertTrue(path.is_file())
            old = time.time() - api.CODEX_SPRITE_TTL_SECONDS - 1
            os.utime(path, (old, old))
            with self.assertRaises(HTTPException) as expired:
                api.get_codex_sprite(token)
            self.assertEqual(expired.exception.status_code, 404)
            with self.assertRaises(HTTPException):
                api.get_codex_sprite("../invalid")

    def test_rejects_other_sizes_and_types(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)):
            for upload in (image_upload(width=192), image_upload(content_type="image/jpeg")):
                with self.assertRaises(HTTPException) as invalid:
                    asyncio.run(api.publish_codex_sprite(None, upload))
                self.assertEqual(invalid.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
