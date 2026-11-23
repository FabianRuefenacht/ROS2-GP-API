# GP API endpoint coverage

This ROS 2 wrapper implements **selected** Screening Eagle / Proceq GP API operations; it is **not** a complete GP API client. The HTTP server is hosted by the iPad GP application (default port `9000`), while the probe is addressed separately.

| HTTP request | Wrapper operation | Notes |
|---|---|---|
| `GET /screen` | `get_screen()` | App state |
| `GET /probe` | `get_probe()` | Connectivity, device metadata and contract; may return `NOT_CONNECTED_TO_PROBE` when disconnected |
| `POST /probe/connect` | `connect_probe()` | JSON includes `serialNumber` **and** `ip`; both required in observed deployment |
| `POST /measurement/start` | `start_measurement()` | `LINE_SCAN` validated |
| `GET /measurement/info` | `get_measurement_info()` | Measurement name and presets |
| `POST /measurement/presets` | `set_presets()` | `TIMED` uses `scanFrequency`; `FIXED_STEP` uses `repetitionRate` |
| `POST /measurement/line/start` | `start_line()` | Returns `clientStartTimestamp` in Unix milliseconds when available |
| `GET /measurement/line` | `get_line_status()` | `started`, `finished`, `scans`, `index`, `length` |
| `POST /measurement/line/stop` | `stop_line()` | Stops line recording |
| `POST /measurement/export/raw` | `stream_raw_export()` | Binary ZIP download; export while measurement still exists |
| `POST /measurement/stop` | `stop_measurement()` | Finish current measurement |

## Known boundaries

- **Tested device:** GP8000 (firmware 5.7.12). GP8100/GP8800 untested.
- **End-to-end validated mode:** `TIMED`, `MAX_SPEED`, `METRIC`, 1 Hz.
- `FIXED_STEP` preset configuration was tested through the API; no full ROS 2 acquisition validation.
- `EXTERNAL` trigger mode, pause/resume, live A-scan streaming, probe-disconnect and other vendor endpoints are not exposed.
- A GP API contract permitting the selected acquisition mode is required.
- The API start timestamp is supplied by the GP API; ROS message stamps reflect the ROS host clock. Do not assume clocks are synchronized.
- If the GP app is suspended or iPad locked, requests may time out. A response with HTTP 403 still demonstrates that an HTTP server responded, but does not establish probe connectivity.

Only the functionality above is implemented; consult the vendor's official API documentation separately for other features.
