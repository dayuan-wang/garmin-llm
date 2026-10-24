import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from garmin_mcp import garmin
from garmin_mcp.__main__ import save_key


class GarminTests(unittest.TestCase):
    def test_project_dotenv_loads_quoted_literal_without_changing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text('GARMIN_PERSONAL_API_KEY="test-${UNSET}-key"\n')
            with patch.dict(os.environ, {}, clear=True), patch.object(garmin, "ENV_FILE", path):
                self.assertEqual(garmin.load_key(), "test-${UNSET}-key")
                self.assertNotIn("GARMIN_PERSONAL_API_KEY", os.environ)

    def test_environment_overrides_project_file(self):
        with patch.dict(os.environ, {"GARMIN_PERSONAL_API_KEY": "environment-key"}):
            with patch.object(Path, "open") as read:
                self.assertEqual(garmin.load_key(), "environment-key")
                read.assert_not_called()

    def test_invalid_project_config_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            for content in ("OTHER=value\n", "GARMIN_PERSONAL_API_KEY=\n", "GARMIN_PERSONAL_API_KEY\n"):
                path.write_text(content)
                with patch.dict(os.environ, {}, clear=True), patch.object(garmin, "ENV_FILE", path):
                    with patch.object(Path, "read_text") as legacy:
                        with self.assertRaises(garmin.GarminError):
                            garmin.load_key()
                        legacy.assert_not_called()

    def test_legacy_file_is_used_only_without_project_or_environment_key(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key"
            key.write_text("legacy-test-key")
            with patch.dict(os.environ, {}, clear=True), patch.object(garmin, "ENV_FILE", Path(directory)/"missing"), patch.object(garmin, "KEY_FILE", key):
                self.assertEqual(garmin.load_key(), "legacy-test-key")

    def test_invalid_date_rejected_before_credentials_or_network(self):
        with patch.object(garmin, "load_key") as key, patch.object(garmin, "request_text") as request:
            for value in ("2026-02-30", "20261022", "../secret", "2026-1-1"):
                with self.assertRaises(ValueError):
                    garmin.fetch_steps(value)
            key.assert_not_called()
            request.assert_not_called()

    def test_live_adapter_exchanges_key_then_fetches_exact_day(self):
        data = [{"calendarDate": "2026-10-22", "totalSteps": 0}]
        with patch.object(garmin, "load_key", return_value="test-key"), patch.object(
            garmin, "request_text", side_effect=["test-token\n", json.dumps(data)]
        ) as request:
            self.assertEqual(garmin.fetch_steps("2026-10-22"), data)
        self.assertEqual(request.call_args_list[0].args, (garmin.TOKEN_PATH, "ApiKey test-key", "POST"))
        self.assertEqual(request.call_args_list[1].args, (
            "/usersummary-service/stats/steps/daily/2026-10-22/2026-10-22", "Bearer test-token"))

    def test_empty_or_bad_response_never_becomes_zero(self):
        with patch.object(garmin, "load_key", return_value="test-key"):
            for body in ("", "null"):
                with patch.object(garmin, "request_text", side_effect=["token", body]):
                    self.assertIsNone(garmin.fetch_steps("2026-10-22"))
            for body in ("not-json", "42"):
                with patch.object(garmin, "request_text", side_effect=["token", body]):
                    with self.assertRaises(garmin.GarminError):
                        garmin.fetch_steps("2026-10-22")

    def test_blank_key_does_not_fall_back_to_real_key_file(self):
        with patch.dict(os.environ, {"GARMIN_PERSONAL_API_KEY": ""}):
            with patch.object(Path, "read_text") as read:
                with self.assertRaises(garmin.GarminError):
                    garmin.load_key()
                read.assert_not_called()

    def test_fixed_origin_authorization_and_timeout(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b"[]"
        with patch.object(garmin, "build_opener", return_value=opener):
            self.assertEqual(garmin.request_text("/test", "Bearer test-token"), "[]")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, garmin.BASE_URL + "/test")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)

    def test_network_errors_do_not_leak_http_body_or_credentials(self):
        for status in (401, 403, 429, 500):
            error = HTTPError("https://example.invalid/secret", status, "private-message", {}, io.BytesIO(b"secret"))
            with patch.object(garmin, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(garmin.GarminError) as caught:
                    garmin.request_text("/test", "ApiKey secret")
                self.assertNotIn("secret", str(caught.exception))
                self.assertNotIn("private-message", str(caught.exception))
        with patch.object(garmin, "build_opener") as opener:
            opener.return_value.open.side_effect = URLError("secret")
            with self.assertRaisesRegex(garmin.GarminError, "connection"):
                garmin.request_text("/test", "ApiKey secret")

    def test_redirects_are_not_followed(self):
        handler = garmin.NoRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_auth_saves_private_file_without_echoing_key_or_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "api-key"
            with patch("garmin_mcp.__main__.KEY_FILE", path), patch(
                "garmin_mcp.__main__.getpass.getpass", return_value="test-key"
            ), patch("sys.stdout", new_callable=io.StringIO) as output:
                save_key()
                self.assertEqual(path.read_text(), "test-key")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("test-key", output.getvalue())
                with self.assertRaises(SystemExit):
                    save_key()
