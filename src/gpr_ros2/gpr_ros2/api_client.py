"""HTTP client for the Screening Eagle GP API.

The API server runs in the GP application on the iPad, not on the probe.
This module deliberately does not depend on ROS 2.
"""

from contextlib import contextmanager
import math
from typing import Any, Iterator

import httpx

from .exceptions import (
    GprConnectionError,
    GprHttpError,
    GprProtocolError,
    GprTimeoutError,
    GprValidationError,
)


class GprApiClient:
    """Synchronous client for the GP application REST API."""

    def __init__(
        self,
        host: str,
        port: int = 9000,
        timeout: float = 10.0,
        export_timeout: float = 300.0,
    ) -> None:
        if not isinstance(host, str) or not host.strip():
            raise GprValidationError("A non-empty iPad host is required.")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise GprValidationError("Port must be between 1 and 65535.")
        for label, value in (("timeout", timeout), ("export_timeout", export_timeout)):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise GprValidationError(f"{label} must be a positive finite number.")

        host = host.strip().rstrip("/")
        if host.startswith("http://") or host.startswith("https://"):
            raise GprValidationError("Pass only the iPad host, without http:// or a port.")
        self.base_url = f"http://{host}:{port}"
        self.export_timeout = float(export_timeout)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(float(timeout)),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "GprApiClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        """Convert HTTP errors and API error objects to typed exceptions."""
        if response.is_error:
            response.read()  # Also required for streaming HTTP error responses.
            error_code = None
            message = response.text[:500] or response.reason_phrase
            try:
                body = response.json()
                if isinstance(body, dict):
                    error = body.get("error")
                    if isinstance(error, dict):
                        error_code = error.get("code")
                        message = error.get("message") or message
            except ValueError:
                pass
            suffix = f" [{error_code}]" if error_code else ""
            raise GprHttpError(
                f"GP API HTTP {response.status_code}{suffix}: {message}",
                status_code=response.status_code,
            )

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        """Parse a JSON response, allowing an empty successful response."""
        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError as exc:
            raise GprProtocolError("GP API returned invalid JSON.") from exc
        if not isinstance(body, dict):
            raise GprProtocolError("GP API JSON response must be an object.")
        error = body.get("error")
        if isinstance(error, dict):
            raise GprProtocolError(
                f"GP API error [{error.get('code', 'UNKNOWN')}]: "
                f"{error.get('message', 'Unknown error')}"
            )
        return body

    @staticmethod
    def _unwrap_data(body: dict[str, Any]) -> dict[str, Any]:
        """Unwrap the API's optional top-level 'data' object."""
        if "data" not in body:
            return body
        data = body["data"]
        if not isinstance(data, dict):
            raise GprProtocolError("GP API field 'data' is not an object.")
        return data

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, endpoint, json=payload)
        except httpx.TimeoutException as exc:
            raise GprTimeoutError(f"Timed out: {method} {endpoint}") from exc
        except httpx.RequestError as exc:
            raise GprConnectionError(f"Cannot reach GP API: {exc}") from exc
        self._check_response(response)
        return self._unwrap_data(self._parse_json(response))

    def get_screen(self) -> dict[str, Any]:
        """Query the current screen of the GP application."""
        return self._request("GET", "/screen")

    def get_probe(self) -> dict[str, Any]:
        """Query probe connection, device metadata and contract details."""
        return self._request("GET", "/probe")

    def connect_probe(self, serial_number: str, ip_address: str) -> dict[str, Any]:
        """Connect the GP application to a probe on the local network."""
        if not serial_number.strip() or not ip_address.strip():
            raise GprValidationError("Probe serial number and IP address are required.")
        return self._request(
            "POST",
            "/probe/connect",
            {"serialNumber": serial_number.strip(), "ip": ip_address.strip()},
        )

    def start_measurement(
        self, name: str, measurement_type: str = "LINE_SCAN"
    ) -> dict[str, Any]:
        """Start a measurement in the GP application."""
        if not name.strip():
            raise GprValidationError("Measurement name cannot be empty.")
        if measurement_type != "LINE_SCAN":
            raise GprValidationError("Only LINE_SCAN has been validated on GP8000.")
        return self._request(
            "POST", "/measurement/start", {"type": measurement_type, "name": name}
        )

    def get_measurement_info(self) -> dict[str, Any]:
        """Read measurement metadata and current acquisition presets."""
        return self._request("GET", "/measurement/info")

    def set_presets(
        self,
        mode: str,
        resolution: str = "MAX_SPEED",
        unit: str = "METRIC",
        scan_frequency_hz: float | None = None,
        repetition_rate: float | None = None,
    ) -> dict[str, Any]:
        """Configure TIMED or FIXED_STEP acquisition.

        TIMED uses scanFrequency; FIXED_STEP uses repetitionRate.
        The EXTERNAL mode is intentionally not enabled until validated.
        """
        if mode not in ("TIMED", "FIXED_STEP"):
            raise GprValidationError("Supported modes: TIMED, FIXED_STEP.")
        if resolution not in ("MAX_SPEED", "MAX_DEPTH"):
            raise GprValidationError("Unsupported resolution.")
        if unit != "METRIC":
            raise GprValidationError("Only METRIC has been validated.")

        payload: dict[str, Any] = {
            "mode": mode,
            "resolution": resolution,
            "unit": unit,
        }
        if mode == "TIMED":
            if repetition_rate is not None:
                raise GprValidationError("TIMED does not accept repetition_rate.")
            self._validate_positive(scan_frequency_hz, "scan_frequency_hz")
            payload["scanFrequency"] = scan_frequency_hz
        else:
            if scan_frequency_hz is not None:
                raise GprValidationError("FIXED_STEP does not accept scan_frequency_hz.")
            self._validate_positive(repetition_rate, "repetition_rate")
            payload["repetitionRate"] = repetition_rate

        return self._request("POST", "/measurement/presets", payload)

    @staticmethod
    def _validate_positive(value: float | None, name: str) -> None:
        if (
            value is None
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise GprValidationError(f"{name} must be a positive finite number.")

    def start_line(self) -> dict[str, Any]:
        """Start a line; response may include clientStartTimestamp in Unix ms."""
        return self._request("POST", "/measurement/line/start")

    def get_line_status(self) -> dict[str, Any]:
        """Read line index, scans, reported length and completion state."""
        return self._request("GET", "/measurement/line")

    def stop_line(self) -> dict[str, Any]:
        """Stop acquisition of the current line."""
        return self._request("POST", "/measurement/line/stop")

    def stop_measurement(self) -> dict[str, Any]:
        """Finish the current measurement."""
        return self._request("POST", "/measurement/stop")

    @contextmanager
    def stream_raw_export(self) -> Iterator[httpx.Response]:
        """Open a streaming response for the raw ZIP export.

        Callers must consume the stream inside the with block. The export
        node will be responsible for writing, validating and renaming files.
        """
        try:
            with self._client.stream(
                "POST",
                "/measurement/export/raw",
                timeout=httpx.Timeout(self.export_timeout),
            ) as response:
                self._check_response(response)
                yield response
        except httpx.TimeoutException as exc:
            raise GprTimeoutError("Raw export timed out.") from exc
        except httpx.RequestError as exc:
            raise GprConnectionError(f"Raw export failed: {exc}") from exc
