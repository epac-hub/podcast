import contextlib
import importlib.util
import io
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "youtube_upload.py"
requests_stub = types.ModuleType("requests")
requests_stub.Response = object
requests_stub.post = None
requests_stub.put = None
requests_stub.request = None
sys.modules["requests"] = requests_stub
SPEC = importlib.util.spec_from_file_location("youtube_upload", SCRIPT)
youtube_upload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(youtube_upload)


class Response:
    def __init__(self, payload, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class YouTubeOAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.token_file = Path(self.temp_dir.name) / "youtube_token.json"
        self.token_file_patch = mock.patch.object(
            youtube_upload, "TOKEN_FILE", self.token_file
        )
        self.token_file_patch.start()
        self.addCleanup(self.token_file_patch.stop)

    def test_auth_saves_refresh_token_without_printing_it(self):
        refresh_token = "refresh-token-must-not-appear"
        device_response = Response(
            {
                "verification_url": "https://example.test/device",
                "user_code": "USER-CODE",
                "device_code": "DEVICE-CODE",
                "expires_in": 600,
                "interval": 1,
            }
        )
        token_response = Response(
            {
                "access_token": "access-token",
                "refresh_token": refresh_token,
                "expires_in": 3600,
            }
        )

        output = io.StringIO()
        with (
            mock.patch.object(
                youtube_upload, "client_credentials", return_value=("client", "secret")
            ),
            mock.patch.object(
                youtube_upload.requests,
                "post",
                side_effect=[device_response, token_response],
            ),
            mock.patch.object(youtube_upload.time, "sleep"),
            mock.patch.object(youtube_upload.time, "time", return_value=1000),
            contextlib.redirect_stdout(output),
        ):
            youtube_upload.cmd_auth(None)

        self.assertNotIn(refresh_token, output.getvalue())
        self.assertIn(refresh_token, self.token_file.read_text())
        self.assertEqual(
            stat.S_IMODE(self.token_file.stat().st_mode),
            stat.S_IRUSR | stat.S_IWUSR,
        )

    def test_environment_refresh_token_is_not_written_to_disk(self):
        refresh_token = "environment-refresh-token"
        response = Response({"access_token": "new-access-token", "expires_in": 3600})

        with (
            mock.patch.dict(
                os.environ,
                {
                    "THP_YT_CLIENT_ID": "client",
                    "THP_YT_CLIENT_SECRET": "secret",
                    "THP_YT_REFRESH_TOKEN": refresh_token,
                },
                clear=False,
            ),
            mock.patch.object(youtube_upload.requests, "post", return_value=response),
        ):
            self.assertEqual(youtube_upload.access_token(), "new-access-token")

        self.assertFalse(self.token_file.exists())

    def test_refresh_failure_does_not_echo_response_body(self):
        secret_response = "server accidentally echoed environment-refresh-token"
        response = Response({}, status_code=400, text=secret_response)

        with (
            mock.patch.dict(
                os.environ,
                {
                    "THP_YT_CLIENT_ID": "client",
                    "THP_YT_CLIENT_SECRET": "secret",
                    "THP_YT_REFRESH_TOKEN": "environment-refresh-token",
                },
                clear=False,
            ),
            mock.patch.object(youtube_upload.requests, "post", return_value=response),
            self.assertRaises(SystemExit) as raised,
        ):
            youtube_upload.access_token()

        self.assertNotIn(secret_response, str(raised.exception))
        self.assertIn("HTTP 400", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
