"""
Binance Futures Testnet REST client.
Handles authentication (HMAC-SHA256), request signing, retries, and timeouts.
"""

import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .logging_config import get_logger

logger = get_logger(__name__)

BASE_URL = "https://testnet.binancefuture.com"

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5   # seconds (multiplied each retry)
REQUEST_TIMEOUT = 10  # seconds


class BinanceAPIError(Exception):
    """Raised when Binance returns a non-200 response or error payload."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API error {code}: {message}")


class NetworkError(Exception):
    """Raised on connection / timeout issues."""


class BinanceFuturesClient:
    """
    Thin wrapper around the Binance USDT-M Futures Testnet REST API.

    Responsibilities:
    - Sign requests with HMAC-SHA256
    - Attach API-key header
    - Retry on transient network failures
    - Log every request and response
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"X-MBX-APIKEY": self.api_key},
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get(self, endpoint: str, params: dict | None = None, signed: bool = False) -> Any:
        return self._request("GET", endpoint, params=params, signed=signed)

    def post(self, endpoint: str, params: dict | None = None) -> Any:
        return self._request("POST", endpoint, params=params, signed=True)

    def get_exchange_info(self) -> dict:
        return self.get("/fapi/v1/exchangeInfo")

    def get_account(self) -> dict:
        return self.get("/fapi/v2/account", signed=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        signed: bool = False,
    ) -> Any:
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{self.base_url}{endpoint}"
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(
                    "→ %s %s | attempt=%d | params=%s",
                    method,
                    endpoint,
                    attempt,
                    {k: v for k, v in params.items() if k != "signature"},
                )

                if method == "GET":
                    response = self._client.get(url, params=params)
                elif method == "POST":
                    response = self._client.post(url, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                logger.debug(
                    "← %s %s | status=%d | body=%s",
                    method,
                    endpoint,
                    response.status_code,
                    response.text[:500],
                )

                data = response.json()

                if response.status_code != 200:
                    code = data.get("code", response.status_code)
                    msg = data.get("msg", response.text)
                    raise BinanceAPIError(code, msg)

                return data

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = NetworkError(str(exc))
                logger.warning(
                    "Network error on attempt %d/%d for %s: %s",
                    attempt,
                    MAX_RETRIES,
                    endpoint,
                    exc,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)

            except BinanceAPIError:
                raise  # Don't retry client errors

        raise last_exc or NetworkError("Unknown network failure")

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
