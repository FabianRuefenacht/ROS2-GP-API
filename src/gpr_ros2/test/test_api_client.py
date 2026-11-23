
"""Minimal tests for the GP API HTTP client."""

import httpx
import pytest

from gpr_ros2.api_client import GprApiClient
from gpr_ros2.exceptions import GprHttpError


def make_client(handler):
    """Create a GP API client with a mocked HTTP transport."""
    client = GprApiClient(host="192.168.1.100")
    client._client.close()
    client._client = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_get_probe():
    """Verify GET /probe and response parsing."""

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/probe"

        return httpx.Response(
            200,
            json={
                "data": {
                    "connected": True,
                    "probe": {
                        "serialNumber": "PM08-004-0087",
                        "firmware": "5.7.12",
                    },
                }
            },
        )

    with make_client(handler) as client:
        result = client.get_probe()

    assert result["connected"] is True
    assert result["probe"]["serialNumber"] == "PM08-004-0087"


def test_timed_presets():
    """Verify the TIMED acquisition request."""

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/measurement/presets"

        import json
        payload = json.loads(request.content)

        assert payload == {
            "mode": "TIMED",
            "resolution": "MAX_SPEED",
            "unit": "METRIC",
            "scanFrequency": 1.0,
        }

        return httpx.Response(200, json={})

    with make_client(handler) as client:
        client.set_presets(
            mode="TIMED",
            scan_frequency_hz=1.0,
        )


def test_start_line_timestamp():
    """Verify that the API start timestamp is preserved."""

    expected_timestamp = 1795419061532

    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/measurement/line/start"

        return httpx.Response(
            200,
            json={
                "clientStartTimestamp": expected_timestamp,
            },
        )

    with make_client(handler) as client:
        result = client.start_line()

    assert result["clientStartTimestamp"] == expected_timestamp


def test_http_error():
    """Verify that API errors become typed exceptions."""

    def handler(request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "INCORRECT_SCREEN",
                    "message": "App must be on the Measurement screen",
                }
            },
        )

    with make_client(handler) as client:
        with pytest.raises(GprHttpError) as exc_info:
            client.get_line_status()

    assert exc_info.value.status_code == 400
    assert "INCORRECT_SCREEN" in str(exc_info.value)
