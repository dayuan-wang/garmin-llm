"""Garmin HTTP adapter. No MCP or AI code belongs in this module."""

import json
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dotenv import dotenv_values

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
KEY_FILE = Path.home() / ".config" / "garmin-mcp" / "api-key"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env.local"


class GarminError(Exception):
    """An error safe to show to the MCP client (no secrets or raw HTTP body)."""

    def __init__(self, message, code="request_failed"):
        super().__init__(message)
        self.code = code


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credential headers to a redirect destination.
        return None


def validate_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("date must be a valid YYYY-MM-DD calendar date") from None
    return value


def load_key() -> str:
    # Explicit environment > project .env.local > legacy key file.
    # Read on demand (not at import), so demo never reads credentials.
    key = os.environ.get("GARMIN_PERSONAL_API_KEY")
    if key is None and ENV_FILE.exists():
        try:
            with ENV_FILE.open(encoding="utf-8") as source:
                key = dotenv_values(stream=source, interpolate=False).get("GARMIN_PERSONAL_API_KEY")
        except (OSError, UnicodeError):
            raise GarminError("Cannot read project .env.local") from None
        if key is None:
            raise GarminError("Project .env.local must define GARMIN_PERSONAL_API_KEY")
    if key is None:
        try:
            key = KEY_FILE.read_text(encoding="utf-8")
        except OSError:
            raise GarminError("Set GARMIN_PERSONAL_API_KEY in project .env.local or run: python -m garmin_mcp auth") from None
    key = key.strip()
    if not key or "\n" in key or "\r" in key:
        raise GarminError("API key is empty or invalid; run local authentication setup again")
    return key


def request_bytes(path: str, authorization: str, method: str = "GET", max_bytes: int = 8_000_000) -> bytes:
    request = Request(BASE_URL + path, method=method,
                      headers={"Authorization": authorization, "Accept": "*/*"})
    try:
        with build_opener(NoRedirects()).open(request, timeout=15) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise GarminError("Response too large; use a shorter date range or smaller page", "response_too_large")
            return body
    except HTTPError as error:
        code = error.code
        error.close()
        if code in (401, 403):
            raise GarminError("Garmin denied access; check key expiry and endpoint permissions", "access_denied") from None
        if code == 429:
            raise GarminError("Garmin rate limit reached; wait before retrying", "rate_limited") from None
        raise GarminError(f"Garmin request failed (HTTP {code})", f"http_{code}") from None
    except (URLError, OSError, UnicodeError, ValueError):
        raise GarminError("Could not read Garmin response; check your connection and retry", "connection_error") from None


def request_text(path: str, authorization: str, method: str = "GET") -> str:
    try:
        return request_bytes(path, authorization, method).decode("utf-8")
    except UnicodeError:
        raise GarminError("Garmin returned invalid text", "invalid_response") from None


class GarminClient:
    """Reuse a token within one MCP operation; never persist credentials or health data."""
    def __init__(self):
        self._token = None

    def authorization(self):
        if self._token is None:
            token = request_text(TOKEN_PATH, "ApiKey " + load_key(), "POST").strip()
            if not token or "\n" in token or "\r" in token:
                raise GarminError("Garmin returned an invalid access token")
            self._token = token
        return "Bearer " + self._token

    def get(self, path):
        body = request_text(path, self.authorization())
        if not body.strip():
            return None
        try:
            data = json.loads(body)
        except ValueError:
            raise GarminError("Garmin returned invalid JSON", "invalid_response") from None
        if data is not None and not isinstance(data, (dict, list)):
            raise GarminError("Garmin returned an unexpected data shape", "invalid_response")
        return data

    def download(self, path):
        return request_bytes(path, self.authorization(), max_bytes=32_000_000)


def fetch_steps(day: str):
    day = validate_date(day)
    return GarminClient().get(f"/usersummary-service/stats/steps/daily/{day}/{day}")
