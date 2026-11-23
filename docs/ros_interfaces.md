# ROS 2 interfaces

The package exposes **six services, four topics and one action**. All interfaces are in the global `/gpr` namespace.

## Services

| Name | Interface | Request | Result |
|---|---|---|---|
| `/gpr/connect` | `gpr_interfaces/srv/Connect` | `serial_number`, `ip_address` (or empty to use YAML) | Success, confirmed serial, error/message |
| `/gpr/start_measurement` | `gpr_interfaces/srv/StartMeasurement` | `measurement_name`, `measurement_type=LINE_SCAN` | Confirmed name/type |
| `/gpr/set_presets` | `gpr_interfaces/srv/SetPresets` | `trigger_mode`, `resolution`, `unit`, `scan_frequency_hz` or `repetition_rate` | Confirmed presets |
| `/gpr/start_line` | `gpr_interfaces/srv/StartLine` | Empty | Line index, API start timestamp in Unix milliseconds |
| `/gpr/stop_line` | `std_srvs/srv/Trigger` | Empty | Success/message |
| `/gpr/stop_measurement` | `std_srvs/srv/Trigger` | Empty | Success/message |

For `TIMED`, supply `scan_frequency_hz > 0` and ignore `repetition_rate`; for `FIXED_STEP`, supply `repetition_rate > 0` instead.

## Action

| Name | Interface | Goal | Feedback | Result |
|---|---|---|---|---|
| `/gpr/export_raw` | `gpr_interfaces/action/ExportRaw` | `output_directory`, `extract_archive`, `overwrite` | Stage and bytes downloaded | Archive path, extraction path, size, success/error |

An empty `output_directory` selects `export_directory` in the YAML config. The action downloads a ZIP with a temporary `.part` file, validates it and optionally extracts it.

## Topics

| Name | Interface | Important fields |
|---|---|---|
| `/gpr/status` | `gpr_interfaces/msg/GprStatus` | `api_reachable`, `probe_connected`, identity, battery, contract, `last_error` |
| `/gpr/measurement_info` | `gpr_interfaces/msg/GprMeasurementInfo` | Name/type, trigger mode, resolution, scan frequency |
| `/gpr/line_status` | `gpr_interfaces/msg/GprLineStatus` | `line_index`, `scan_count`, `started`, `finished`, `recording`, `reported_length_m` |
| `/gpr/measurement_events` | `gpr_interfaces/msg/GprEvent` | `event_type`, `request_start`, `response_received`, `api_timestamp_ms` |

Status topics are published by `gpr_api_node` during polling where the GP app state allows it. `reported_length_m` is the API value, **not** the robot's traveled distance; `recording` is a derived state.

## Recommended order

`connect` → `start_measurement` → `set_presets` → `start_line` → `stop_line` → **`export_raw`** → `stop_measurement`.

See [the runnable example](../scripts/example.py) and [the main README](../README.md).
