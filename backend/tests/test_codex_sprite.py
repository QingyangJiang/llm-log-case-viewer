import asyncio
import io
import os
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

os.environ.setdefault("DATABASE_URL", "sqlite://")
import backend.app.main as api

R2_ENV = {
    "CODEX_SPRITE_R2_ACCOUNT_ID": "a" * 32,
    "CODEX_SPRITE_R2_BUCKET": "case-lens-pets",
    "CODEX_SPRITE_R2_ACCESS_KEY_ID": "test-access-key",
    "CODEX_SPRITE_R2_SECRET_ACCESS_KEY": "test-secret-key",
}


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

    def test_http_page_can_receive_dedicated_https_install_url(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)), patch.dict(
            os.environ, {"CODEX_SPRITE_PUBLIC_URL_PREFIX": "https://pets.example.com/codex-pets/"}
        ):
            result = asyncio.run(api.publish_codex_sprite(None, image_upload()))
            token = result["path"].rsplit("/", 1)[-1]
            self.assertEqual(result["image_url"], f"https://pets.example.com/codex-pets/{token}.png")
            self.assertEqual(api.get_codex_sprite(token).media_type, "image/png")

    def test_rejects_http_public_gateway_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)), patch.dict(
            os.environ, {"CODEX_SPRITE_PUBLIC_URL_PREFIX": "http://pets.example.com/codex-pets"}
        ):
            with self.assertRaises(HTTPException) as invalid:
                asyncio.run(api.publish_codex_sprite(None, image_upload()))
            self.assertEqual(invalid.exception.status_code, 503)
            self.assertFalse((api.Path(directory) / "codex-sprites").exists())

    def test_private_r2_upload_returns_signed_link_without_local_copy(self):
        s3 = MagicMock()
        s3.generate_presigned_url.return_value = "https://r2.cloudflarestorage.com/pet.png?X-Amz-Signature=example"
        boto3 = types.SimpleNamespace(client=MagicMock(return_value=s3))
        botocore_config = types.SimpleNamespace(Config=MagicMock(return_value="short-timeouts"))
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)), patch.dict(
            os.environ, {**R2_ENV, "CODEX_SPRITE_PUBLIC_URL_PREFIX": "http://ignored.invalid"}
        ), patch.dict(sys.modules, {"boto3": boto3, "botocore": types.ModuleType("botocore"), "botocore.config": botocore_config}):
            result = asyncio.run(api.publish_codex_sprite(None, image_upload()))
            self.assertEqual(result["path"], "")
            self.assertEqual(result["image_url"], s3.generate_presigned_url.return_value)
            self.assertEqual(result["expires_in_seconds"], "1800")
            self.assertFalse((api.Path(directory) / "codex-sprites").exists())
            boto3.client.assert_called_once_with(
                "s3", endpoint_url=f"https://{'a' * 32}.r2.cloudflarestorage.com",
                aws_access_key_id="test-access-key", aws_secret_access_key="test-secret-key", region_name="auto",
                config="short-timeouts",
            )
            botocore_config.Config.assert_called_once_with(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1})
            kwargs = s3.put_object.call_args.kwargs
            self.assertEqual(kwargs["Bucket"], "case-lens-pets")
            self.assertTrue(kwargs["Key"].startswith("case-lens-pets/"))
            self.assertTrue(kwargs["Key"].endswith(".png"))
            self.assertEqual(kwargs["ContentType"], "image/png")
            s3.generate_presigned_url.assert_called_once_with(
                "get_object", Params={"Bucket": kwargs["Bucket"], "Key": kwargs["Key"]}, ExpiresIn=1800
            )

    def test_r2_configuration_requires_all_credentials_and_supports_jurisdictions(self):
        with patch.dict(os.environ, {"CODEX_SPRITE_R2_BUCKET": "case-lens-pets"}):
            with self.assertRaises(HTTPException) as invalid:
                asyncio.run(api.publish_codex_sprite(None, image_upload()))
            self.assertEqual(invalid.exception.status_code, 503)
        with patch.dict(os.environ, {**R2_ENV, "CODEX_SPRITE_R2_JURISDICTION": "eu"}):
            self.assertEqual(api.codex_sprite_r2_config()[0], f"https://{'a' * 32}.eu.r2.cloudflarestorage.com")

    def test_r2_failure_does_not_expose_credentials_or_write_local_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api, "DATA_DIR", api.Path(directory)), patch.dict(
            os.environ, R2_ENV
        ), patch.object(api, "upload_codex_sprite_to_r2", side_effect=RuntimeError("test-secret-key")):
            with self.assertRaises(HTTPException) as failed:
                asyncio.run(api.publish_codex_sprite(None, image_upload()))
            self.assertEqual(failed.exception.status_code, 502)
            self.assertNotIn("test-secret-key", failed.exception.detail)
            self.assertFalse((api.Path(directory) / "codex-sprites").exists())


if __name__ == "__main__":
    unittest.main()
